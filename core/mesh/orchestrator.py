"""Compute Mesh orchestrator — routes jobs across free-tier GPU platforms.

Endpoints (Colab/Kaggle/HF Spaces/Lightning/Modal) are modelled as a state
machine. The actual network dispatch is stubbed behind `_dispatch_to_endpoint`
so unit tests and local runs can validate the state transitions without
touching real cloud APIs.
"""
from __future__ import annotations

import asyncio
import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class EndpointState(enum.Enum):
    IDLE = "idle"
    PROBING = "probing"
    READY = "ready"
    ASSIGNED = "assigned"
    COOLDOWN = "cooldown"
    FAILED = "failed"


class EndpointName(enum.Enum):
    COLAB = "colab"
    KAGGLE = "kaggle"
    HUGGINGFACE_SPACES = "hf_spaces"
    LIGHTNING = "lightning"
    MODAL = "modal"


@dataclass
class Endpoint:
    name: EndpointName
    state: EndpointState = EndpointState.IDLE
    last_probe_ms: float = float("inf")
    cooldown_until: float = 0.0
    success_rate: float = 1.0  # EWMA, 0..1


@dataclass
class MeshJob:
    job_id: str
    workload_name: str
    payload_size_mb: float
    submitted_at: float
    status: str = "queued"  # queued | assigned | completed | failed
    assigned_endpoint: Optional[EndpointName] = None
    result: Optional[dict] = None
    attempts: int = 0


class ComputeMeshOrchestrator:
    PROBE_INTERVAL_SECONDS = 300
    COOLDOWN_BASE_SECONDS = 60
    MAX_ATTEMPTS = 3

    def __init__(self) -> None:
        self._endpoints: Dict[EndpointName, Endpoint] = {
            name: Endpoint(name=name) for name in EndpointName
        }
        self._jobs: Dict[str, MeshJob] = {}
        self._queue: List[str] = []  # job_ids in FIFO order
        self._rr_index: int = 0
        self._running: bool = False
        self._tasks: List[asyncio.Task] = []

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tasks.append(asyncio.create_task(self._probe_loop()))
        self._tasks.append(asyncio.create_task(self._dispatch_loop()))

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

    # ──────────────────────────────────────────────────────────────────
    # Public API

    def submit_job(self, workload_name: str, payload_size_mb: float = 0.0) -> str:
        job_id = uuid.uuid4().hex[:12]
        self._jobs[job_id] = MeshJob(
            job_id=job_id,
            workload_name=workload_name,
            payload_size_mb=payload_size_mb,
            submitted_at=time.time(),
        )
        self._queue.append(job_id)
        return job_id

    def get_job_status(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if job is None:
            return {"error": "job_not_found"}
        return {
            "job_id": job.job_id,
            "workload": job.workload_name,
            "status": job.status,
            "endpoint": job.assigned_endpoint.value if job.assigned_endpoint else None,
            "attempts": job.attempts,
            "result": job.result,
        }

    def get_mesh_health(self) -> dict:
        return {
            "endpoints": {
                e.name.value: {
                    "state": e.state.value,
                    "last_probe_ms": e.last_probe_ms,
                    "cooldown_until": e.cooldown_until,
                    "success_rate": round(e.success_rate, 3),
                }
                for e in self._endpoints.values()
            },
            "queued": len([j for j in self._jobs.values() if j.status == "queued"]),
            "assigned": len([j for j in self._jobs.values() if j.status == "assigned"]),
            "completed": len([j for j in self._jobs.values() if j.status == "completed"]),
            "failed": len([j for j in self._jobs.values() if j.status == "failed"]),
        }

    # ──────────────────────────────────────────────────────────────────
    # Internal loops

    async def _probe_loop(self) -> None:
        while self._running:
            for endpoint in self._endpoints.values():
                if endpoint.state in (EndpointState.ASSIGNED, EndpointState.COOLDOWN):
                    continue
                await self._probe_endpoint(endpoint)
            await asyncio.sleep(self.PROBE_INTERVAL_SECONDS)

    async def _probe_endpoint(self, endpoint: Endpoint) -> None:
        endpoint.state = EndpointState.PROBING
        # Stub: real impl pings endpoint. Simulate 50-500ms.
        start = time.time()
        await asyncio.sleep(0.05)
        endpoint.last_probe_ms = (time.time() - start) * 1000
        endpoint.state = EndpointState.READY

    async def _dispatch_loop(self) -> None:
        while self._running:
            if self._queue:
                job_id = self._queue[0]
                job = self._jobs[job_id]
                endpoint = self._pick_endpoint()
                now = time.time()
                if endpoint is None:
                    # No ready endpoint — backoff before trying again
                    await asyncio.sleep(2.0)
                    continue
                self._queue.pop(0)
                job.assigned_endpoint = endpoint.name
                job.status = "assigned"
                job.attempts += 1
                endpoint.state = EndpointState.ASSIGNED
                asyncio.create_task(self._run_job(endpoint, job))
            await asyncio.sleep(0.1)

    def _pick_endpoint(self) -> Optional[Endpoint]:
        """Round-robin over READY endpoints, biased by success_rate."""
        now = time.time()
        candidates = [
            e for e in self._endpoints.values()
            if e.state == EndpointState.READY and e.cooldown_until <= now
        ]
        if not candidates:
            return None
        # Rotate so successive calls pick different endpoints
        self._rr_index = (self._rr_index + 1) % len(candidates)
        # Prefer higher success-rate when there is a strong winner
        candidates.sort(key=lambda e: (-e.success_rate, e.last_probe_ms))
        return candidates[self._rr_index % len(candidates)]

    async def _run_job(self, endpoint: Endpoint, job: MeshJob) -> None:
        try:
            result = await self._dispatch_to_endpoint(endpoint, job)
            job.result = result
            job.status = "completed"
            endpoint.state = EndpointState.READY
            endpoint.success_rate = 0.9 * endpoint.success_rate + 0.1 * 1.0
        except Exception as exc:  # noqa: BLE001
            job.status = "failed" if job.attempts >= self.MAX_ATTEMPTS else "queued"
            if job.status == "queued":
                self._queue.append(job.job_id)
            endpoint.state = EndpointState.COOLDOWN
            endpoint.cooldown_until = time.time() + self.COOLDOWN_BASE_SECONDS * job.attempts
            endpoint.success_rate = 0.9 * endpoint.success_rate + 0.1 * 0.0
            job.result = {"error": str(exc)}

    async def _dispatch_to_endpoint(self, endpoint: Endpoint, job: MeshJob) -> dict:
        """Dispatch a job to the chosen endpoint.

        Only HuggingFace Spaces has a real implementation today (public
        HTTP API, no OAuth). The other endpoints fall back to the local
        1-second stub until their auth flow is wired.

        Colab/Kaggle/Lightning/Modal need: live OAuth session, notebook
        upload, session polling — see docs/ARCHITECTURE.md "Known limits".
        """
        if endpoint.name == EndpointName.HUGGINGFACE_SPACES:
            try:
                from .hf_dispatcher import HuggingFaceDispatcher
                hf = HuggingFaceDispatcher()
                if hf.is_available():
                    payload = {"payload_mb": job.payload_size_mb, "job_id": job.job_id}
                    return await hf.dispatch(job.workload_name, payload)
            except Exception as exc:  # noqa: BLE001
                return {
                    "status": "error",
                    "endpoint": endpoint.name.value,
                    "error": f"hf_dispatch_failed: {exc}",
                }
        if endpoint.name == EndpointName.MODAL:
            try:
                from .modal_dispatcher import ModalDispatcher
                md = ModalDispatcher()
                if md.is_available():
                    payload = {"payload_mb": job.payload_size_mb, "job_id": job.job_id}
                    return await md.dispatch(job.workload_name, payload)
            except Exception as exc:  # noqa: BLE001
                return {
                    "status": "error",
                    "endpoint": endpoint.name.value,
                    "error": f"modal_dispatch_failed: {exc}",
                }
        # Fallback stub for endpoints without a live impl yet.
        await asyncio.sleep(1.0)
        return {
            "status": "ok",
            "endpoint": endpoint.name.value,
            "workload": job.workload_name,
            "payload_mb": job.payload_size_mb,
            "note": "stub — real dispatch not wired for this endpoint",
        }

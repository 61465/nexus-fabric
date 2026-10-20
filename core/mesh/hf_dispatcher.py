"""HuggingFace Spaces dispatcher.

Replaces the stubbed `_dispatch_to_endpoint` for the HF endpoint with a
real HTTP call to a user-provided HuggingFace Space running ZeroGPU.

Why HF Spaces, not Colab:
  Colab requires live Google OAuth + a session, which is not scriptable
  from a background process. HF Spaces exposes a plain HTTP endpoint for
  any Gradio or FastAPI app — zero auth needed for public Spaces, API-token
  auth for private ones. We can submit payload, poll, retrieve result.

Expected Space contract:
  POST  https://<space>.hf.space/run/predict         (Gradio v3)
     or https://<space>.hf.space/api/predict         (Gradio v4)
  Body: {"data": [workload_name, payload_json]}
  Response: {"data": [result_json]}
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, Optional

try:
    import httpx  # type: ignore
    _HTTPX_AVAILABLE = True
except ImportError:
    httpx = None  # type: ignore
    _HTTPX_AVAILABLE = False


class HuggingFaceDispatcher:
    """One real backend for the ComputeMeshOrchestrator.

    Usage:
        hf = HuggingFaceDispatcher(space_url=os.getenv("NEXUS_HF_SPACE"))
        result = await hf.dispatch(workload="shader_compile", payload={"hash": "abc"})
    """

    def __init__(
        self,
        space_url: Optional[str] = None,
        hf_token: Optional[str] = None,
        request_timeout_s: float = 60.0,
    ) -> None:
        self.space_url = space_url or os.getenv("NEXUS_HF_SPACE", "")
        self.hf_token = hf_token or os.getenv("HF_TOKEN", "")
        self.request_timeout_s = request_timeout_s

    def is_available(self) -> bool:
        return _HTTPX_AVAILABLE and bool(self.space_url)

    async def dispatch(self, workload: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send workload to the configured HF Space, return the Space's response.

        Raises RuntimeError if httpx is missing, Space URL is empty, or the
        Space returns a non-200.
        """
        if not _HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed; cannot reach HF Space")
        if not self.space_url:
            raise RuntimeError("NEXUS_HF_SPACE not configured")

        url = self._predict_url()
        headers = {"Content-Type": "application/json"}
        if self.hf_token:
            headers["Authorization"] = f"Bearer {self.hf_token}"

        body = {"data": [workload, json.dumps(payload)]}
        started = time.time()

        async with httpx.AsyncClient(timeout=self.request_timeout_s) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()

        elapsed = time.time() - started
        return {
            "status": "ok",
            "endpoint": "hf_spaces",
            "workload": workload,
            "elapsed_s": round(elapsed, 3),
            "space_response": data,
        }

    def _predict_url(self) -> str:
        base = self.space_url.rstrip("/")
        # Gradio v4 lives under /api/predict ; v3 lives under /run/predict.
        # We default to v4 and let the caller override via env.
        suffix = os.getenv("NEXUS_HF_PREDICT_PATH", "/api/predict")
        if base.endswith(suffix):
            return base
        return f"{base}{suffix}"


async def dispatch_via_hf(workload: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience top-level API for the orchestrator wire-in."""
    return await HuggingFaceDispatcher().dispatch(workload, payload)

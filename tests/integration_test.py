"""End-to-end integration test for Nexus Fabric.

Spawns nexus_engine.py in a subprocess, connects via WebSocket, exercises
every dashboard command, collects a live hardware/cycle sample window,
asserts invariants, writes a JSON report. Designed to run unattended so
the main chat can save tokens.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import websockets


ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "core" / "nexus_engine.py"
TOKEN_FILE = Path(os.environ.get("LOCALAPPDATA", "")) / "NexusFabric" / "session.key"
REPORT = ROOT / "tests" / "integration_report.json"

WS_URL = "ws://localhost:9001"
STARTUP_WAIT_S = 10.0
SAMPLE_WINDOW_S = 20.0
SHUTDOWN_WAIT_S = 3.0


class WsClient:
    """Tiny async WS client with request/response correlation."""

    def __init__(self, ws, token: str) -> None:
        self.ws = ws
        self.token = token
        self._broadcasts: List[Dict[str, Any]] = []
        self._command_results: List[Dict[str, Any]] = []

    @classmethod
    async def open(cls, url: str, token: str) -> "WsClient":
        ws = await websockets.connect(url, open_timeout=5)
        await ws.send(json.dumps({"auth": token}))
        # Server sends 3 initial frames (hardware, agents, system_state) right
        # after a successful auth. Reading them here confirms auth landed and
        # avoids a race where the first user command arrives mid-handshake.
        inst = cls(ws, token)
        try:
            for _ in range(3):
                raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                inst._broadcasts.append(json.loads(raw))
        except asyncio.TimeoutError:
            pass
        return inst

    async def send_command(self, cmd: str, data: Dict[str, Any] | None = None) -> None:
        payload = {"type": cmd}
        if data:
            payload["data"] = data
        await self.ws.send(json.dumps(payload))

    async def collect(self, duration_s: float) -> Dict[str, Any]:
        """Receive broadcasts + command results for duration_s."""
        deadline = time.time() + duration_s
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            self._broadcasts.append(msg)
        return self._summarize()

    def _summarize(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        samples: Dict[str, List[Any]] = {"fps": [], "cpu": [], "gpu": [], "ram": []}
        for m in self._broadcasts:
            t = m.get("type", "?")
            by_type[t] = by_type.get(t, 0) + 1
            if t == "hardware":
                d = m.get("data", {})
                samples["fps"].append(d.get("fps", 0))
                cpu = d.get("cpu", {})
                samples["cpu"].append(cpu.get("load_pct", 0) if isinstance(cpu, dict) else 0)
                dgpu = d.get("dgpu", {})
                samples["gpu"].append(dgpu.get("load_pct", 0) if isinstance(dgpu, dict) else 0)
                ram = d.get("ram", {})
                samples["ram"].append(ram.get("used_gb", 0) if isinstance(ram, dict) else 0)
        def _mean(xs):
            xs = [x for x in xs if isinstance(x, (int, float))]
            return round(sum(xs) / len(xs), 2) if xs else None
        return {
            "frame_counts": by_type,
            "samples_mean": {k: _mean(v) for k, v in samples.items()},
            "sample_counts": {k: len(v) for k, v in samples.items()},
        }


async def run_test() -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "engine": {"started": False, "pid": None},
        "auth": {"accepted": None, "rejected_bad_token": None},
        "window": {},
    }

    # Launch engine as subprocess
    engine_proc = subprocess.Popen(
        [sys.executable, str(ENGINE)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        cwd=str(ROOT), text=True,
    )
    report["engine"]["pid"] = engine_proc.pid
    try:
        # Wait for startup
        await asyncio.sleep(STARTUP_WAIT_S)
        if engine_proc.poll() is not None:
            report["engine"]["started"] = False
            out = engine_proc.stdout.read() if engine_proc.stdout else ""
            report["engine"]["crash_tail"] = out[-500:]
            return report
        report["engine"]["started"] = True

        # Read token
        if not TOKEN_FILE.exists():
            report["auth"]["accepted"] = False
            report["error"] = f"token file missing: {TOKEN_FILE}"
            return report
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()

        # Test 1: auth with correct token
        try:
            good = await WsClient.open(WS_URL, token)
            report["auth"]["accepted"] = True
        except Exception as exc:
            report["auth"]["accepted"] = False
            report["auth"]["error"] = str(exc)
            return report

        # Test 2: auth rejection with bad token
        try:
            async with websockets.connect(WS_URL, open_timeout=5) as bad_ws:
                await bad_ws.send(json.dumps({"auth": "WRONG"}))
                try:
                    await asyncio.wait_for(bad_ws.recv(), timeout=3)
                    report["auth"]["rejected_bad_token"] = False
                except websockets.exceptions.ConnectionClosed as e:
                    report["auth"]["rejected_bad_token"] = (e.code == 4403)
                    report["auth"]["reject_code"] = e.code
        except Exception as exc:
            report["auth"]["rejected_bad_token"] = False
            report["auth"]["reject_error"] = str(exc)

        # Test 3: dashboard commands
        cmd_results: Dict[str, Any] = {}

        for cmd, data in [
            ("mesh_health", None),
            ("etw_status", None),
            ("agent_errors", None),
            ("mesh_submit", {"workload": "shader_compile", "payload_mb": 5.0}),
            ("predict_next", {"top_k": 5}),
        ]:
            try:
                await good.send_command(cmd, data)
                # Give engine a moment to answer; next broadcast or ack may arrive
                await asyncio.sleep(0.5)
                cmd_results[cmd] = "sent"
            except Exception as exc:
                cmd_results[cmd] = f"error: {exc}"
        report["commands"] = cmd_results

        # Test 4: sample window — collect broadcasts for SAMPLE_WINDOW_S
        report["window"] = await good.collect(SAMPLE_WINDOW_S)

        await good.ws.close()
    finally:
        # Shutdown
        engine_proc.terminate()
        try:
            engine_proc.wait(timeout=SHUTDOWN_WAIT_S)
        except subprocess.TimeoutExpired:
            engine_proc.kill()
        report["engine"]["exit_code"] = engine_proc.returncode

    report["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    # Invariants / pass-fail
    checks = []
    checks.append(("engine_started", report["engine"]["started"] is True))
    checks.append(("auth_accepted", report["auth"]["accepted"] is True))
    checks.append(("bad_token_rejected", report["auth"].get("rejected_bad_token") is True))
    checks.append(("received_hardware_frames",
                   report.get("window", {}).get("frame_counts", {}).get("hardware", 0) > 0))
    checks.append(("received_agents_frames",
                   report.get("window", {}).get("frame_counts", {}).get("agents", 0) > 0))
    report["checks"] = {name: ok for name, ok in checks}
    report["passed"] = all(ok for _, ok in checks)
    return report


def main() -> int:
    report = asyncio.run(run_test())
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report.get("passed"),
                      "checks": report.get("checks"),
                      "window": report.get("window", {}).get("frame_counts"),
                      "report_file": str(REPORT)}, indent=2))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())

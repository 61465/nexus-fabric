"""Live ETW capture — rolling buffer that replaces PerformanceSimulator.

Design:
  xperf runs continuously with a small ring buffer (not writing to disk).
  Every N seconds we flush a snapshot to a temp ETL, parse it with
  ETWReader, and expose the latest FrameStats via `get_latest()`.

This is a thin background runner. The engine's hardware callback keeps
calling PerformanceSimulator as a safety fallback — when live ETW stats
are available, we overlay them on the perf dict.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from .etw_reader import ETWReader, FrameStats


_log = logging.getLogger("nexus.hardware.live_etw")

_BUNDLED_XPERF = Path(
    "D:/project/cyber_pro/Windows Performance Toolkit/xperf.exe"
)


def _resolve_xperf() -> Optional[Path]:
    found = shutil.which("xperf.exe")
    if found:
        return Path(found)
    if _BUNDLED_XPERF.is_file():
        return _BUNDLED_XPERF
    return None


class LiveETW:
    """Rolling ETW capture + periodic FrameStats refresh.

    Not a hard-realtime path: we accept 2-5 s stale readings because the
    kernel ETW ring buffer is cheaper to flush periodically than to tail
    live. For a council that cycles every 8 s, 2-5 s stale is fine.
    """

    SESSION_NAME = "NexusFabricLive"
    REFRESH_INTERVAL_S = 5.0
    PROVIDERS = "PROC_THREAD+LOADER+DISK_IO+DPC+INTERRUPT"

    def __init__(self) -> None:
        self._xperf = _resolve_xperf()
        self._reader: Optional[ETWReader] = None
        try:
            self._reader = ETWReader()
        except FileNotFoundError:
            self._reader = None
        self._latest: Optional[FrameStats] = None
        self._latest_at: float = 0.0
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._tmp_dir: Optional[Path] = None

    @property
    def available(self) -> bool:
        return self._xperf is not None and self._reader is not None

    def status(self) -> dict:
        return {
            "available": self.available,
            "running": self._running,
            "xperf": str(self._xperf) if self._xperf else None,
            "last_refresh_s_ago": round(time.time() - self._latest_at, 2) if self._latest_at else None,
            "latest_sample_count": self._latest.sample_count if self._latest else 0,
        }

    def get_latest(self) -> Optional[FrameStats]:
        return self._latest

    def latest_perf_overlay(self) -> dict:
        """Dict suitable to merge INTO perf_sim.compute() output."""
        if self._latest is None or self._latest.sample_count == 0:
            return {}
        return {
            "fps": self._latest.fps_mean,
            "frametime_ms": self._latest.frametime_mean_ms,
            "fps_1pct": self._latest.fps_1pct_low,
            "ft_stddev": self._latest.frametime_stddev_ms,
            "frametime_p99_ms": self._latest.frametime_p99_ms,
            "source": "etw_live",
        }

    async def start(self) -> None:
        if self._running or not self.available:
            if not self.available:
                _log.info("LiveETW not available (xperf missing); skipping")
            return
        self._running = True
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="nexus_live_etw_"))
        self._task = asyncio.create_task(self._refresh_loop())
        _log.info("LiveETW started, tmp=%s", self._tmp_dir)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await asyncio.get_event_loop().run_in_executor(None, self._stop_session)
        if self._tmp_dir and self._tmp_dir.exists():
            shutil.rmtree(self._tmp_dir, ignore_errors=True)

    # ─────────────────────────────────────────────────────────────────
    # Internals

    def _stop_session(self) -> None:
        try:
            subprocess.run(
                [str(self._xperf), "-stop", self.SESSION_NAME],
                capture_output=True, text=True, timeout=10,
            )
        except Exception:
            pass

    async def _refresh_loop(self) -> None:
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                stats = await loop.run_in_executor(None, self._capture_and_read)
                if stats is not None:
                    self._latest = stats
                    self._latest_at = time.time()
            except Exception as exc:  # noqa: BLE001
                _log.warning("live ETW refresh failed: %s", exc)
            await asyncio.sleep(self.REFRESH_INTERVAL_S)

    def _capture_and_read(self) -> Optional[FrameStats]:
        if not self._xperf or not self._reader or not self._tmp_dir:
            return None
        etl_path = self._tmp_dir / f"snapshot_{int(time.time())}.etl"

        # Session may not exist on first call; start it.
        start_res = subprocess.run(
            [str(self._xperf), "-on", self.PROVIDERS, "-f", str(etl_path),
             "-SessionName", self.SESSION_NAME],
            capture_output=True, text=True, timeout=15,
        )
        # If session already running, xperf returns non-zero. Try to stop & restart
        # on error; swallow quietly to avoid noisy logs during start transitions.
        if start_res.returncode != 0:
            self._stop_session()
            return None

        # Collect briefly then stop the session into our ETL file.
        time.sleep(2.0)
        stop_res = subprocess.run(
            [str(self._xperf), "-stop", self.SESSION_NAME, "-d", str(etl_path)],
            capture_output=True, text=True, timeout=15,
        )
        if stop_res.returncode != 0 or not etl_path.exists():
            return None
        try:
            return self._reader.read(str(etl_path))
        finally:
            try:
                etl_path.unlink(missing_ok=True)
            except Exception:
                pass

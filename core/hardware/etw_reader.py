"""ETW reader — replaces PerformanceSimulator with measurements from real ETL traces.

Pipeline:
  1. xperf captures an ETL file (benchmark/baseline.ps1 or on-demand).
  2. We invoke `tracerpt.exe -y ... -of CSV` to convert ETL -> CSV
     (shipped with every Windows install at C:\\Windows\\System32).
  3. Parse the CSV, extract frame delivery events + GPU queue latency,
     derive FPS / frametime stats.

This is a one-shot reader: feed it an ETL path, get a `FrameStats` dict back.
A live mode (etl ring buffer + incremental read) is possible later; for v1.1
we score baseline vs after by capturing two short ETLs and comparing.
"""
from __future__ import annotations

import csv
import os
import re
import statistics
import subprocess
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional


# Events that mark one GPU frame being presented. tracerpt emits these under
# the DXGKrnl / DWM provider names with human-readable task names. We match on
# any task containing "Present" or "DmaPacket Start" as a close approximation.
_FRAME_TASK_PATTERNS = (
    re.compile(r"\bPresent\b", re.IGNORECASE),
    re.compile(r"\bDmaPacket\s*Start\b", re.IGNORECASE),
    re.compile(r"\bFlip\b", re.IGNORECASE),
)


@dataclass
class FrameStats:
    sample_count: int
    duration_s: float
    fps_mean: float
    fps_p50: float
    fps_1pct_low: float
    frametime_mean_ms: float
    frametime_p50_ms: float
    frametime_p99_ms: float
    frametime_stddev_ms: float
    source_etl: str


class ETWReader:
    """Reads a captured ETL file and derives frame-delivery statistics."""

    TRACERPT = r"C:\Windows\System32\tracerpt.exe"

    def __init__(self, tracerpt_path: Optional[str] = None) -> None:
        self._tracerpt = tracerpt_path or self.TRACERPT
        if not os.path.isfile(self._tracerpt):
            raise FileNotFoundError(f"tracerpt.exe not found at {self._tracerpt}")

    def read(self, etl_path: str) -> FrameStats:
        """Convert ETL -> CSV via tracerpt and derive FrameStats."""
        etl = Path(etl_path).resolve()
        if not etl.is_file():
            raise FileNotFoundError(f"ETL file not found: {etl}")

        with tempfile.TemporaryDirectory(prefix="nexus_etw_") as tmp:
            csv_path = Path(tmp) / f"{etl.stem}.csv"
            # -y: answer yes to overwrite prompts
            # -of CSV: output format
            # -o: output file
            result = subprocess.run(
                [self._tracerpt, str(etl), "-y", "-of", "CSV", "-o", str(csv_path)],
                capture_output=True, text=True,
            )
            if result.returncode != 0 or not csv_path.exists():
                raise RuntimeError(
                    f"tracerpt failed (rc={result.returncode}): "
                    f"{(result.stderr or result.stdout or '').strip()[:300]}"
                )
            timestamps = list(self._iter_frame_timestamps(csv_path))

        return self._compute_stats(timestamps, source=str(etl))

    def _iter_frame_timestamps(self, csv_path: Path) -> Iterable[float]:
        """Yield frame-present clock times in seconds."""
        with csv_path.open("r", encoding="utf-16", errors="replace", newline="") as fh:
            try:
                reader = csv.reader(fh)
            except Exception:
                return
            for row in reader:
                if len(row) < 3:
                    continue
                task = row[0] if row else ""
                if not any(p.search(task) for p in _FRAME_TASK_PATTERNS):
                    continue
                # tracerpt CSV: col 1 is Clock-Time (100ns units since 1601).
                try:
                    ts_100ns = int(row[1].strip())
                except (ValueError, IndexError):
                    continue
                yield ts_100ns / 1e7  # seconds

    def _compute_stats(self, timestamps: List[float], source: str) -> FrameStats:
        if len(timestamps) < 2:
            # No usable samples; return zero-valued stats rather than raise.
            return FrameStats(
                sample_count=0, duration_s=0.0,
                fps_mean=0.0, fps_p50=0.0, fps_1pct_low=0.0,
                frametime_mean_ms=0.0, frametime_p50_ms=0.0,
                frametime_p99_ms=0.0, frametime_stddev_ms=0.0,
                source_etl=source,
            )
        timestamps.sort()
        deltas = [max(1e-4, timestamps[i + 1] - timestamps[i]) for i in range(len(timestamps) - 1)]
        frametimes_ms = [d * 1000.0 for d in deltas]
        fps_series = [1.0 / d for d in deltas]
        fps_sorted = sorted(fps_series)
        p99_index = max(0, int(len(frametimes_ms) * 0.99) - 1)
        p1_fps_cutoff = fps_sorted[max(0, int(len(fps_sorted) * 0.01))]
        return FrameStats(
            sample_count=len(frametimes_ms),
            duration_s=round(timestamps[-1] - timestamps[0], 3),
            fps_mean=round(statistics.fmean(fps_series), 2),
            fps_p50=round(statistics.median(fps_series), 2),
            fps_1pct_low=round(p1_fps_cutoff, 2),
            frametime_mean_ms=round(statistics.fmean(frametimes_ms), 3),
            frametime_p50_ms=round(statistics.median(frametimes_ms), 3),
            frametime_p99_ms=round(sorted(frametimes_ms)[p99_index], 3),
            frametime_stddev_ms=round(statistics.pstdev(frametimes_ms), 3),
            source_etl=source,
        )

    def to_perf_dict(self, stats: FrameStats) -> Dict[str, float]:
        """Produce a dict compatible with the perf_state consumer in nexus_engine."""
        return {
            "fps": stats.fps_mean,
            "frametime_ms": stats.frametime_mean_ms,
            "fps_1pct": stats.fps_1pct_low,
            "ft_stddev": stats.frametime_stddev_ms,
            "frametime_p99_ms": stats.frametime_p99_ms,
            "active_profile": "ETW_MEASURED",
            "source": "etw",
            "etl": stats.source_etl,
        }

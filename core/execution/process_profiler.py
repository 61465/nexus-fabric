"""Observe a running process briefly, classify its workload type, pick the
best optimization recipe. Replaces the one-size-fits-all pinning with a
decision made from live telemetry.

Signals read via psutil (no admin needed, no hooks):
  - thread count (and whether it grew during the sample window)
  - CPU-% averaged across cores (how parallel it actually runs)
  - I/O counters delta (bytes/sec read+write)
  - RSS stability

Classes:
  parallel_compute    numpy/BLAS/ML training/video encode — >8 threads active
  single_hot_thread   game main loop / Python asyncio — 1-4 threads, high per-thread CPU
  io_bound            file/network heavy — low CPU per thread, high I/O
  interactive         UI / low activity — avoid interfering
  unknown             nothing clear in the window

Each class maps to a recipe in ADAPTIVE_RECIPES below.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import psutil


# Recipe keys match what the executor applies.
ADAPTIVE_RECIPES: dict[str, dict] = {
    "tensor_heavy": {
        # GPU offload candidate: parallel BLAS-style workload that would
        # benefit far more from moving to Arc iGPU via DirectML than from
        # any CPU scheduling change. Fabric suggests offload via GPURouter
        # (actual routing requires the workload to use the fabric wrapper).
        "pin_cores": False,
        "priority": "ABOVE_NORMAL",
        "gpu_offload_suggested": True,
        "reason": "BLAS-shape workload; offer GPU routing for 10x speedup",
    },
    "parallel_compute": {
        # Do NOT pin — we'd lose cores. Keep priority bump for scheduling.
        "pin_cores": False,
        "priority": "ABOVE_NORMAL",
        "reason": "BLAS-style workload wants every core; pinning hurts throughput",
    },
    "single_hot_thread": {
        # Classic game-main-thread case: pin to P-cores + HIGH priority.
        "pin_cores": True,
        "priority": "HIGH",
        "reason": "hot thread benefits from dedicated P-cores and high priority",
    },
    "io_bound": {
        "pin_cores": False,
        "priority": "ABOVE_NORMAL",
        "reason": "I/O-bound; CPU scheduling matters less than disk/network",
    },
    "interactive": {
        "pin_cores": False,
        "priority": "NORMAL",
        "reason": "interactive process; do not touch to preserve responsiveness",
    },
    "unknown": {
        "pin_cores": False,
        "priority": "NORMAL",
        "reason": "insufficient signal to classify; leave the process alone",
    },
}


@dataclass
class ProcessProfile:
    pid: int
    name: str
    workload_class: str
    threads: int
    threads_grew: bool
    cpu_mean_pct: float
    cpu_peak_pct: float
    io_bytes_per_s: float
    recipe: dict


def profile_process(pid: int, duration_s: float = 2.0, interval_s: float = 0.25) -> Optional[ProcessProfile]:
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return None
    try:
        proc.cpu_percent(interval=None)  # prime
        thread_counts: list[int] = []
        cpu_series: list[float] = []
        io_start = _safe_io_bytes(proc)
        t0 = time.time()
        while time.time() - t0 < duration_s:
            try:
                thread_counts.append(proc.num_threads())
                cpu_series.append(proc.cpu_percent(interval=None))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            time.sleep(interval_s)
        io_end = _safe_io_bytes(proc)
        duration = max(0.1, time.time() - t0)
        io_bps = (io_end - io_start) / duration if io_end > 0 and io_start >= 0 else 0.0
        name = _safe_name(proc)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None

    if not thread_counts or not cpu_series:
        return None

    threads = thread_counts[-1]
    threads_grew = thread_counts[-1] > thread_counts[0]
    cpu_mean = sum(cpu_series) / len(cpu_series)
    cpu_peak = max(cpu_series)

    workload = _classify(threads, cpu_mean, cpu_peak, io_bps, pid)
    recipe = dict(ADAPTIVE_RECIPES[workload])
    return ProcessProfile(
        pid=pid, name=name, workload_class=workload,
        threads=threads, threads_grew=threads_grew,
        cpu_mean_pct=round(cpu_mean, 1),
        cpu_peak_pct=round(cpu_peak, 1),
        io_bytes_per_s=round(io_bps, 1),
        recipe=recipe,
    )


_TENSOR_MODULES = (
    "numpy", "torch", "tensorflow", "jax",
    "cv2", "scipy", "sklearn", "transformers",
)


def _process_imports_tensor_libs(pid: int) -> bool:
    """Heuristic: list the process's loaded DLLs/modules and look for
    tensor-library signatures. Only works for Python processes we can
    read; fail-closed to False otherwise."""
    try:
        import psutil as _ps
        p = _ps.Process(pid)
        try:
            mem_maps = p.memory_maps()
        except (psutil.AccessDenied, OSError):
            return False
        joined = " ".join(m.path.lower() for m in mem_maps if m.path)
        return any(sig in joined for sig in _TENSOR_MODULES)
    except Exception:
        return False


def _classify(threads: int, cpu_mean: float, cpu_peak: float, io_bps: float, pid: int = 0) -> str:
    # Order matters: tensor-heavy first (can be offloaded to GPU), then
    # parallel, then I/O, then hot thread, then interactive.
    cpu_per_thread = cpu_mean / max(1, threads)

    # Tensor-heavy: parallel compute AND uses a tensor lib (numpy/torch/…).
    # These are the top candidates for GPU offload.
    if threads >= 8 and cpu_peak >= 400 and pid and _process_imports_tensor_libs(pid):
        return "tensor_heavy"

    # Parallel compute: many threads AND the whole workload is CPU-heavy.
    if threads >= 8 and cpu_peak >= 400:
        return "parallel_compute"
    # I/O bound: high disk/network throughput, modest CPU use.
    if io_bps > 10 * 1024 * 1024 and cpu_mean < 100:  # >10 MB/s I/O
        return "io_bound"
    # Single hot thread: few threads, each burning CPU.
    if threads <= 4 and cpu_per_thread > 50:
        return "single_hot_thread"
    # Interactive: low utilisation, few threads.
    if cpu_mean < 20 and threads <= 10:
        return "interactive"
    return "unknown"


def _safe_io_bytes(proc: psutil.Process) -> int:
    try:
        c = proc.io_counters()
        return (c.read_bytes or 0) + (c.write_bytes or 0)
    except (psutil.AccessDenied, AttributeError, OSError):
        return -1


def _safe_name(proc: psutil.Process) -> str:
    try:
        return proc.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return "?"

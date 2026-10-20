"""A/B benchmark — Nexus Fabric executor optimizations on heavy workload.

Phase 1 — baseline: run heavy_workload.py as a plain subprocess.
Phase 2 — fabric:   same subprocess, then immediately apply the executor's
                    CPU affinity (P-cores only) + HIGH priority.

Both runs produce identical workload JSON summaries. We compare them.

The point: measure the real effect of just the deterministic hand (L5)
on a reproducible CPU-bound workload. No cloud, no LLM, no game required.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

from execution.executor import NexusExecutor  # noqa: E402

REPORTS = Path(__file__).resolve().parent / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)
WORKLOAD = Path(__file__).resolve().parent / "heavy_workload.py"


def _sample_proc(proc: psutil.Process, duration_s: float, interval_s: float = 0.5) -> list[dict]:
    """Sample per-process CPU% + RSS until duration elapses or proc exits."""
    out: list[dict] = []
    end = time.time() + duration_s
    try:
        proc.cpu_percent(interval=None)  # prime
    except psutil.NoSuchProcess:
        return out
    while time.time() < end:
        try:
            if not proc.is_running():
                break
            cpu = proc.cpu_percent(interval=None)
            rss_mb = proc.memory_info().rss / 1024 / 1024
            out.append({"t": round(time.time(), 2), "cpu": cpu,
                        "rss_mb": round(rss_mb, 1)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break
        time.sleep(interval_s)
    return out


def _run_phase(label: str, apply_fabric: bool, rounds: int, dim: int, batches: int) -> dict:
    out_json = REPORTS / f"workload_{label}.json"
    cmd = [
        sys.executable, "-u", str(WORKLOAD),
        "--rounds", str(rounds),
        "--dim", str(dim),
        "--batches", str(batches),
        "--label", label,
        "--out", str(out_json),
    ]
    print(f"\n[benchmark] starting phase={label} apply_fabric={apply_fabric}", flush=True)
    t_start = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    ps = psutil.Process(proc.pid)

    fabric_applied: dict | None = None
    if apply_fabric:
        # Give the child a moment to import numpy etc, then apply fabric ops.
        time.sleep(2.0)
        try:
            executor = NexusExecutor()
            # Adaptive path: profile the live process, pick the right recipe.
            r = executor.optimize_adaptive(str(proc.pid))
            fabric_applied = r
            print(f"[benchmark] adaptive fabric: class={r.get('workload_class')} "
                  f"recipe={r.get('recipe', {}).get('reason')}", flush=True)
        except Exception as exc:  # noqa: BLE001
            fabric_applied = {"error": str(exc)}
            print(f"[benchmark] fabric failed: {exc}", flush=True)

    # Sample until the workload finishes
    samples = _sample_proc(ps, duration_s=600)
    proc.wait()
    t_end = time.time()
    stdout = proc.stdout.read() if proc.stdout else ""

    workload_result: dict = {}
    if out_json.exists():
        try:
            workload_result = json.loads(out_json.read_text(encoding="utf-8"))
        except Exception:
            pass

    cpu_series = [s["cpu"] for s in samples if "cpu" in s]
    rss_series = [s["rss_mb"] for s in samples if "rss_mb" in s]
    return {
        "label": label,
        "apply_fabric": apply_fabric,
        "fabric_applied": fabric_applied,
        "wall_s": round(t_end - t_start, 3),
        "returncode": proc.returncode,
        "samples": len(samples),
        "cpu_mean_pct": round(sum(cpu_series) / len(cpu_series), 2) if cpu_series else None,
        "cpu_peak_pct": round(max(cpu_series), 2) if cpu_series else None,
        "rss_peak_mb": round(max(rss_series), 1) if rss_series else None,
        "workload": workload_result,
        "stdout_tail": stdout[-500:] if stdout else "",
    }


def _run_gpu_phase(label: str, rounds: int, dim: int, batches: int) -> dict:
    """Phase 3: workload runs on Arc iGPU via DirectML."""
    out_json = REPORTS / f"workload_{label}.json"
    gpu_script = Path(__file__).resolve().parent / "heavy_workload_gpu.py"
    cmd = [sys.executable, "-u", str(gpu_script),
           "--rounds", str(rounds), "--dim", str(dim),
           "--batches", str(batches), "--out", str(out_json)]
    print(f"\n[benchmark] starting phase={label} (Arc iGPU via DirectML)", flush=True)
    t_start = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    ps = psutil.Process(proc.pid)
    samples = _sample_proc(ps, duration_s=600)
    proc.wait()
    t_end = time.time()
    stdout = proc.stdout.read() if proc.stdout else ""
    workload_result: dict = {}
    if out_json.exists():
        try:
            workload_result = json.loads(out_json.read_text(encoding="utf-8"))
        except Exception:
            pass
    cpu_series = [s["cpu"] for s in samples if "cpu" in s]
    rss_series = [s["rss_mb"] for s in samples if "rss_mb" in s]
    return {
        "label": label,
        "device": "arc_igpu_directml",
        "wall_s": round(t_end - t_start, 3),
        "returncode": proc.returncode,
        "samples": len(samples),
        "cpu_mean_pct": round(sum(cpu_series) / len(cpu_series), 2) if cpu_series else None,
        "cpu_peak_pct": round(max(cpu_series), 2) if cpu_series else None,
        "rss_peak_mb": round(max(rss_series), 1) if rss_series else None,
        "workload": workload_result,
        "stdout_tail": stdout[-500:] if stdout else "",
    }


def main() -> int:
    rounds = int(os.environ.get("NEXUS_BENCH_ROUNDS", "15"))
    dim = int(os.environ.get("NEXUS_BENCH_DIM", "512"))
    batches = int(os.environ.get("NEXUS_BENCH_BATCHES", "32"))

    print(f"[benchmark] rounds={rounds} dim={dim} batches={batches} "
          f"cpu_count={os.cpu_count()}")

    # Phase 1: baseline (no fabric)
    phase1 = _run_phase("baseline", False, rounds, dim, batches)
    time.sleep(2.0)
    # Phase 2: fabric-optimized (CPU scheduling)
    phase2 = _run_phase("fabric_cpu", True, rounds, dim, batches)
    time.sleep(2.0)
    # Phase 3: fabric GPU-routed (Arc iGPU via DirectML)
    phase3 = _run_gpu_phase("fabric_gpu", rounds, dim, batches)

    report = {
        "config": {"rounds": rounds, "dim": dim, "batches": batches,
                   "cpu_count": os.cpu_count()},
        "baseline": phase1,
        "fabric_cpu": phase2,
        "fabric_gpu": phase3,
    }

    def _pct(before, after, invert=False):
        if before is None or after is None or before == 0:
            return None
        delta = (after - before) / abs(before) * 100
        return round(-delta if invert else delta, 2)

    def _speedup(before, after):
        if before is None or after is None or after == 0:
            return None
        return round(before / after, 2)

    report["delta"] = {
        "fabric_cpu_vs_baseline_pct": _pct(phase1["wall_s"], phase2["wall_s"], invert=True),
        "fabric_gpu_vs_baseline_pct": _pct(phase1["wall_s"], phase3["wall_s"], invert=True),
        "fabric_gpu_speedup": _speedup(phase1["wall_s"], phase3["wall_s"]),
    }

    out = REPORTS / f"benchmark_fabric_{int(time.time())}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== BENCHMARK SUMMARY ===")
    print(f"baseline (CPU numpy):        {phase1['wall_s']:.2f}s  CPU_mean={phase1['cpu_mean_pct']}%")
    print(f"fabric_cpu (scheduling):     {phase2['wall_s']:.2f}s  CPU_mean={phase2['cpu_mean_pct']}%")
    print(f"fabric_gpu (Arc iGPU DML):   {phase3['wall_s']:.2f}s  CPU_mean={phase3['cpu_mean_pct']}%")
    print(f"")
    print(f"delta fabric_cpu vs baseline: {report['delta']['fabric_cpu_vs_baseline_pct']}%")
    print(f"delta fabric_gpu vs baseline: {report['delta']['fabric_gpu_vs_baseline_pct']}%")
    print(f"GPU speedup: {report['delta']['fabric_gpu_speedup']}x")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

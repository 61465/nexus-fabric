"""Same shape as heavy_workload.py but routes compute to Arc iGPU.

Used for the GPU A/B against the CPU baseline. Deterministic seeds so
numerical results are comparable round-to-round.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

from execution.gpu_router import GPURouter  # noqa: E402


def heavy_round_gpu(router: GPURouter, dim: int, batches: int) -> float:
    rng = np.random.default_rng(42)
    a = rng.standard_normal((batches, dim, dim), dtype=np.float32)
    b = rng.standard_normal((batches, dim, dim), dtype=np.float32)
    t0 = time.perf_counter()
    router.attention_block(a, b)
    return time.perf_counter() - t0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=15)
    parser.add_argument("--dim", type=int, default=512)
    parser.add_argument("--batches", type=int, default=32)
    parser.add_argument("--out", type=str, default="")
    args = parser.parse_args()

    router = GPURouter()
    if not router.available:
        print(json.dumps({"error": "GPU not available", "status": router.status()}))
        return 1

    warm = router.warmup(dim=args.dim)
    print(f"[gpu_workload pid={os.getpid()}] device={router.status()['name']} "
          f"warmup_ms={warm.get('warmup_ms')}", flush=True)

    start = time.time()
    round_times: list[float] = []
    for i in range(args.rounds):
        dt = heavy_round_gpu(router, args.dim, args.batches)
        round_times.append(dt)
        if (i + 1) % max(1, args.rounds // 5) == 0:
            print(f"[gpu_workload] round {i+1}/{args.rounds} dt={dt:.3f}s", flush=True)
    total = time.time() - start

    result = {
        "device": "arc_igpu_directml",
        "rounds": args.rounds,
        "dim": args.dim,
        "batches": args.batches,
        "total_s": round(total, 3),
        "mean_round_s": round(sum(round_times) / len(round_times), 3),
        "min_round_s": round(min(round_times), 3),
        "max_round_s": round(max(round_times), 3),
        "warmup_ms": warm.get("warmup_ms"),
    }
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

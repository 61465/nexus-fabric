"""Realistic CPU-heavy ML-adjacent workload for A/B testing Nexus Fabric.

Mimics the hot loop of transformer training:
  - multi-threaded matmul (what torch does during forward/backward)
  - softmax + reduction
  - cross-batch mean/std normalization

Deterministic (seeded), repeatable, ~90-120 s on a modern laptop CPU.
No GPU dependency so results are comparable even without Arc/CUDA.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np


def heavy_matmul_round(dim: int, batches: int) -> float:
    """One round of a transformer-ish batched matmul + softmax."""
    rng = np.random.default_rng(42)
    a = rng.standard_normal((batches, dim, dim), dtype=np.float32)
    b = rng.standard_normal((batches, dim, dim), dtype=np.float32)
    t0 = time.perf_counter()
    # QK^T attention-shape operation
    attn = np.matmul(a, np.transpose(b, (0, 2, 1)))
    # Softmax along last axis
    attn -= attn.max(axis=-1, keepdims=True)
    np.exp(attn, out=attn)
    attn /= attn.sum(axis=-1, keepdims=True)
    # Attention @ V-like
    out = np.matmul(attn, b)
    # Layer-norm-ish reduction
    mean = out.mean(axis=-1, keepdims=True)
    std = out.std(axis=-1, keepdims=True) + 1e-5
    (out - mean) / std
    return time.perf_counter() - t0


def run_workload(rounds: int, dim: int, batches: int) -> dict:
    pid = os.getpid()
    start = time.time()
    round_times: list[float] = []
    for i in range(rounds):
        dt = heavy_matmul_round(dim, batches)
        round_times.append(dt)
        if (i + 1) % max(1, rounds // 5) == 0:
            print(f"[workload pid={pid}] round {i+1}/{rounds} dt={dt:.3f}s", flush=True)
    total = time.time() - start
    return {
        "pid": pid,
        "rounds": rounds,
        "dim": dim,
        "batches": batches,
        "total_s": round(total, 3),
        "mean_round_s": round(sum(round_times) / len(round_times), 3),
        "min_round_s": round(min(round_times), 3),
        "max_round_s": round(max(round_times), 3),
        "numpy_threads": int(os.environ.get("OMP_NUM_THREADS", "0") or 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Nexus Fabric A/B heavy workload")
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--dim", type=int, default=512)
    parser.add_argument("--batches", type=int, default=32)
    parser.add_argument("--out", type=str, default="")
    parser.add_argument("--label", type=str, default="baseline")
    args = parser.parse_args()

    print(f"[workload pid={os.getpid()}] label={args.label} rounds={args.rounds} "
          f"dim={args.dim} batches={args.batches}", flush=True)

    result = run_workload(args.rounds, args.dim, args.batches)
    result["label"] = args.label
    result["cpu_count"] = os.cpu_count()

    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

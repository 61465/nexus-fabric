"""Workload classifier — decides LOCAL vs CLOUD_MESH per task.

Rules verified in Wave 2 NEXUS dispatch 2026-10-20:
  R1  LatencyBudget<16ms + ComputeIntensity>=7 -> LOCAL (realtime)
  R2  LatencyBudget>100ms + DataSize>50MB + Parallelism=true -> CLOUD_MESH
  R3  Determinism required + LatencyBudget<=16ms -> LOCAL (anti-cheat / timing)
  R4  default -> CLOUD_MESH
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict


LOCAL = "LOCAL"
CLOUD_MESH = "CLOUD_MESH"


@dataclass(frozen=True)
class WorkloadFeatures:
    latency_budget_ms: int      # max acceptable latency
    compute_intensity: int      # 0..10
    data_size_mb: float         # transfer / processing size
    determinism: bool           # must be reproducible (anti-cheat, physics)
    parallelism: bool           # workload is embarrassingly parallel


@dataclass(frozen=True)
class WorkloadDecision:
    destination: str
    confidence: float
    rationale: str


class WorkloadClassifier:
    """Rule-based classifier. Order of rules matters."""

    def classify(self, f: WorkloadFeatures) -> WorkloadDecision:
        # R1: realtime + heavy -> LOCAL
        if f.latency_budget_ms < 16 and f.compute_intensity >= 7:
            return WorkloadDecision(
                destination=LOCAL,
                confidence=0.95,
                rationale="R1 realtime+heavy: <16ms budget and intensity>=7",
            )
        # R3: anti-cheat / determinism takes priority over R2
        if f.determinism and f.latency_budget_ms <= 16:
            return WorkloadDecision(
                destination=LOCAL,
                confidence=0.95,
                rationale="R3 determinism required with tight budget",
            )
        # R2: lax latency + bulk + parallel -> CLOUD
        if f.latency_budget_ms > 100 and f.data_size_mb > 50 and f.parallelism:
            return WorkloadDecision(
                destination=CLOUD_MESH,
                confidence=0.90,
                rationale="R2 bulk parallel work with lax latency",
            )
        # R4: default push to mesh so local hardware stays free
        return WorkloadDecision(
            destination=CLOUD_MESH,
            confidence=0.60,
            rationale="R4 default: no rule locked LOCAL",
        )


# Known workload profiles. Values are informed defaults; real workloads
# can override by constructing WorkloadFeatures directly.
WORKLOAD_PROFILES: Dict[str, WorkloadFeatures] = {
    "shader_compile": WorkloadFeatures(
        latency_budget_ms=5000, compute_intensity=8,
        data_size_mb=5.0, determinism=True, parallelism=True,
    ),
    "texture_decompress": WorkloadFeatures(
        latency_budget_ms=200, compute_intensity=5,
        data_size_mb=120.0, determinism=True, parallelism=True,
    ),
    "frame_render": WorkloadFeatures(
        latency_budget_ms=8, compute_intensity=10,
        data_size_mb=0.5, determinism=False, parallelism=False,
    ),
    "ml_upscale": WorkloadFeatures(
        latency_budget_ms=4, compute_intensity=9,
        data_size_mb=8.0, determinism=False, parallelism=False,
    ),
    "ml_upscale_training": WorkloadFeatures(
        # Per-game model fine-tune — one-time, can run on cloud.
        latency_budget_ms=3_600_000, compute_intensity=10,
        data_size_mb=2000.0, determinism=True, parallelism=True,
    ),
    "save_load": WorkloadFeatures(
        latency_budget_ms=500, compute_intensity=3,
        data_size_mb=200.0, determinism=False, parallelism=True,
    ),
    "audio_dsp": WorkloadFeatures(
        latency_budget_ms=20, compute_intensity=4,
        data_size_mb=1.0, determinism=False, parallelism=True,
    ),
    "anticheat_heartbeat": WorkloadFeatures(
        latency_budget_ms=8, compute_intensity=1,
        data_size_mb=0.01, determinism=True, parallelism=False,
    ),
}


def classify_by_name(workload_name: str) -> WorkloadDecision:
    """Classify by known profile. Raises KeyError if unknown."""
    features = WORKLOAD_PROFILES[workload_name]
    return WorkloadClassifier().classify(features)

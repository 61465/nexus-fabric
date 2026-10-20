"""Policy layer that routes council proposals into the mesh automatically.

The AgentCouncil produces proposals every 8 s. Some of those proposals are
pure dispatch instructions (e.g. "precompile shaders for next level"). We
classify each proposal with the WorkloadClassifier; those that come back
CLOUD_MESH are submitted to the ComputeMeshOrchestrator without blocking
the council cycle.

Design goals:
  - zero changes to BaseAgent / council.py
  - fail-open: a classifier mistake never crashes the engine
  - visibility: dispatch events become WS log entries
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from .classifier import WorkloadClassifier, WorkloadFeatures, WORKLOAD_PROFILES
from .orchestrator import ComputeMeshOrchestrator


# Action strings produced by the 31 agents that are candidates for mesh
# offload. The council's own executor already handles the local actions
# (SET_QUALITY_PROFILE, PROCESS_PRIORITY, CONFIG_INJECT, …) — we only
# intercept the ones that match a known cloud-safe workload.
_MESH_ACTIONS: Dict[str, str] = {
    "PRECOMPILE_SHADERS":      "shader_compile",
    "COMPILE_SHADER_CACHE":    "shader_compile",
    "DECOMPRESS_TEXTURES":     "texture_decompress",
    "TRAIN_UPSCALE_MODEL":     "ml_upscale_training",
    "PREFETCH_ASSETS":         "save_load",
}


@dataclass
class DispatchDecision:
    workload_name: str
    destination: str
    rationale: str
    job_id: Optional[str] = None


class MeshAutoDispatcher:
    """Translates council proposals into mesh job submissions."""

    def __init__(self, mesh: ComputeMeshOrchestrator) -> None:
        self._mesh = mesh
        self._classifier = WorkloadClassifier()

    def route_proposals(self, proposals: Iterable[Dict[str, Any]]) -> List[DispatchDecision]:
        """Walk a batch of council proposals, dispatch matching ones."""
        decisions: List[DispatchDecision] = []
        for p in proposals:
            action = str(p.get("action", "")).upper()
            workload_name = _MESH_ACTIONS.get(action)
            if not workload_name:
                continue
            features = WORKLOAD_PROFILES.get(workload_name)
            if features is None:
                continue
            decision_obj = self._classifier.classify(features)
            if decision_obj.destination != "CLOUD_MESH":
                decisions.append(DispatchDecision(
                    workload_name=workload_name,
                    destination=decision_obj.destination,
                    rationale=decision_obj.rationale,
                ))
                continue
            payload_mb = float(p.get("payload_mb", features.data_size_mb))
            job_id = self._mesh.submit_job(workload_name, payload_mb)
            decisions.append(DispatchDecision(
                workload_name=workload_name,
                destination="CLOUD_MESH",
                rationale=decision_obj.rationale,
                job_id=job_id,
            ))
        return decisions

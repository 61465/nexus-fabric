"""
nexus_engine.py
════════════════
Project Nexus — Main Engine Entry Point

Wires together:
  1. HardwareDetector  — real hardware telemetry every 1s
  2. AgentCouncil      — 31-agent AI reasoning loop every 8s
  3. NexusExecutor     — deterministic action execution & safe rollback
  4. WebSocketServer   — streams everything to dashboard on ws://localhost:9001

Usage:
  python nexus_engine.py

Optional:
  Set GEMINI_API_KEY in .env for real AI agent reasoning.
  Without it, rule-based fallbacks run automatically.
"""

import asyncio
import time
import os
import sys
import math
import random

# ── Path setup ────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from hardware.detector import HardwareDetector, HardwareSnapshot, scan_all_candidate_processes
try:
    from hardware.etw_reader import ETWReader, FrameStats
    from hardware.live_etw import LiveETW
    _ETW_AVAILABLE = True
except ImportError:
    ETWReader = None  # type: ignore
    FrameStats = None  # type: ignore
    LiveETW = None  # type: ignore
    _ETW_AVAILABLE = False
from agents.council    import AgentCouncil, CycleRecord
from transport.ws_server import NexusWebSocketServer
from execution.executor import NexusExecutor
from mesh import (
    ComputeMeshOrchestrator,
    PrefetchPredictor,
    AssetEvent,
    classify_by_name,
    MeshAutoDispatcher,
)

# ── Init __init__ files ───────────────────────────────────────────────
for pkg in ["hardware", "agents", "transport", "execution", "mesh", "brain"]:
    pkg_dir = os.path.join(os.path.dirname(__file__), pkg)
    init = os.path.join(pkg_dir, "__init__.py")
    if os.path.isdir(pkg_dir) and not os.path.exists(init):
        open(init, "w").close()


# ─────────────────────────────────────────────────────────────────────
#  Performance Simulator (before ETW integration)
#  Produces realistic FPS / frametime numbers based on hardware load
# ─────────────────────────────────────────────────────────────────────

class PerformanceSimulator:
    """
    Derives realistic FPS from actual hardware load.
    Will be replaced by ETW reader in Phase 2.
    """
    def __init__(self):
        self._base_fps   = 60.0
        self._stddev     = 2.0
        self._spike_prob = 0.02

    def compute(self, snapshot: HardwareSnapshot) -> dict:
        gpu_load = snapshot.dgpu.load_pct
        cpu_load = snapshot.cpu.load_pct

        # GPU is usually the limiter
        gpu_factor  = max(0.1, 1.0 - (gpu_load - 40) / 100)
        cpu_factor  = max(0.5, 1.0 - (cpu_load - 50) / 150)
        thermal_pen = 1.0
        temp = snapshot.dgpu.temp_c or 65
        if temp > 85:
            thermal_pen = max(0.7, 1.0 - (temp - 85) * 0.03)

        fps_raw = self._base_fps * gpu_factor * cpu_factor * thermal_pen
        fps_raw = max(5, min(240, fps_raw + (random.random() - 0.5) * 8))

        frametime = 1000.0 / fps_raw
        stddev = self._stddev * (1 + gpu_load / 200)

        # Occasional spike
        if random.random() < self._spike_prob:
            frametime *= random.uniform(2.0, 4.0)
            stddev *= 3

        fps_1pct = fps_raw * random.uniform(0.55, 0.75)

        return {
            "fps":           round(fps_raw, 1),
            "frametime_ms":  round(frametime, 2),
            "fps_1pct":      round(fps_1pct, 1),
            "ft_stddev":     round(stddev, 2),
            "active_profile": "BALANCED",
            "nexus_score":   self._compute_nexus_score(fps_raw, gpu_load, snapshot.ram),
        }

    def _compute_nexus_score(self, fps, gpu_load, ram) -> float:
        fps_score   = min(10, fps / 12)
        eff_score   = 10 - gpu_load / 14
        ram_score   = max(0, 10 - ram.used_gb / 2)
        return round(fps_score * 0.5 + eff_score * 0.3 + ram_score * 0.2, 1)


# ─────────────────────────────────────────────────────────────────────
#  Nexus Engine
# ─────────────────────────────────────────────────────────────────────

class NexusEngine:
    def __init__(self):
        self.hw_detector  = HardwareDetector(interval=1.0)
        self.council      = AgentCouncil()
        self.ws_server    = NexusWebSocketServer()
        self.perf_sim     = PerformanceSimulator()
        self.executor     = NexusExecutor()
        self.mesh         = ComputeMeshOrchestrator()
        self.predictor: "PrefetchPredictor | None" = None  # created when a game is detected
        self.live_etw     = LiveETW() if _ETW_AVAILABLE else None
        self.auto_dispatch = MeshAutoDispatcher(self.mesh)
        self._agent_errors: dict = {}  # agent_id -> count (for visibility)
        self._perf_state  = {}
        self._tick_count  = 0
        self._start_time  = time.time()

        # Connect WebSocket command dispatcher to engine & executor
        self.ws_server.on_command(self._on_dashboard_command)

    async def start(self):
        print("\n" + "═" * 60)
        print("   PROJECT NEXUS v0.9 — Heterogeneous Compute Fabric")
        print("═" * 60)
        api_key = os.getenv("GEMINI_API_KEY", "")
        ai_mode = "✓ Gemini AI" if api_key else "⚠ Rule-Based Fallback"
        print(f"   AI Mode    : {ai_mode}")
        print(f"   Agents     : {len(self.council._agents)} across 9 teams")
        print(f"   Dashboard  : ws://localhost:9001")
        print(f"   Executor   : Reversible Injection & Safe Rollback Active")
        print("═" * 60 + "\n")

        # Wire hardware → context updates
        self.hw_detector.on_update(self._on_hardware_update)

        # Wire council cycles → WebSocket broadcast
        self.council.on_cycle_complete(self._on_cycle_complete)

        # Wire WebSocket initial state
        self.ws_server.update_agents(self.council.get_agents_state())

        # Start mesh orchestrator (state machine runs in background)
        await self.mesh.start()
        print("[Engine] Compute Mesh orchestrator online")

        # Start live ETW capture (replaces PerformanceSimulator overlay)
        if self.live_etw and self.live_etw.available:
            await self.live_etw.start()
            print(f"[Engine] Live ETW capture online ({self.live_etw.status().get('xperf')})")
        else:
            print("[Engine] Live ETW capture unavailable; using PerformanceSimulator only")

        # Run all systems concurrently
        await asyncio.gather(
            self.hw_detector.start(),
            self.council.start(),
            self.ws_server.start(),
        )

    # ─── Dashboard Commands ───────────────────────────────────────

    async def _on_dashboard_command(self, cmd: str, data: dict):
        """Handle incoming command from dashboard."""
        if cmd == "get_processes":
            return scan_all_candidate_processes(30)

        elif cmd == "set_profile":
            prof = data.get("profile", "BALANCED")
            return self.executor.apply_quality_profile(prof)

        elif cmd == "inject":
            proc = data.get("process", "")
            self.executor.set_active_target(proc)
            res1 = self.executor.optimize_process_threads(proc)
            res2 = self.executor.set_process_priority(proc, "HIGH")
            res3 = self.executor.apply_quality_profile(self.executor._active_profile)
            success = res1.get("success", False) or res3.get("success", False)
            msg = f"Target {proc}: {res1.get('message')} | {res3.get('message')}"
            return {"success": success, "message": msg}

        elif cmd == "rollback":
            return self.executor.rollback_all()

        elif cmd == "mesh_health":
            return self.mesh.get_mesh_health()

        elif cmd == "mesh_submit":
            workload = data.get("workload", "shader_compile")
            payload_mb = float(data.get("payload_mb", 0.0))
            decision = classify_by_name(workload) if workload in {
                "shader_compile", "texture_decompress", "frame_render",
                "ml_upscale", "ml_upscale_training", "save_load",
                "audio_dsp", "anticheat_heartbeat",
            } else None
            if decision and decision.destination == "LOCAL":
                return {"routed": "LOCAL", "rationale": decision.rationale}
            job_id = self.mesh.submit_job(workload, payload_mb)
            return {"routed": "CLOUD_MESH", "job_id": job_id,
                    "rationale": decision.rationale if decision else "unknown workload"}

        elif cmd == "mesh_status":
            return self.mesh.get_job_status(data.get("job_id", ""))

        elif cmd == "etw_status":
            return (self.live_etw.status()
                    if self.live_etw is not None
                    else {"available": False, "reason": "ETW module not loaded"})

        elif cmd == "agent_errors":
            return {"errors": dict(self._agent_errors),
                    "total": sum(self._agent_errors.values())}

        elif cmd == "gpu_status":
            try:
                from execution.gpu_router import GPURouter
                r = getattr(self, "_gpu_router", None) or GPURouter()
                self._gpu_router = r
                return r.status()
            except Exception as exc:  # noqa: BLE001
                return {"available": False, "error": str(exc)}

        elif cmd == "gpu_warmup":
            try:
                from execution.gpu_router import GPURouter
                r = getattr(self, "_gpu_router", None) or GPURouter()
                self._gpu_router = r
                if not r.available:
                    return {"warmed_up": False, "reason": "no device"}
                return r.warmup(dim=int(data.get("dim", 1024)))
            except Exception as exc:  # noqa: BLE001
                return {"warmed_up": False, "error": str(exc)}

        elif cmd == "etw_read":
            # Analyse a captured ETL file (produced by benchmark/baseline.ps1).
            etl_path = data.get("etl_path", "")
            if not _ETW_AVAILABLE:
                return {"success": False, "error": "ETWReader not available"}
            try:
                reader = ETWReader()
                stats = reader.read(etl_path)
                return {"success": True, "stats": stats.__dict__,
                        "perf": reader.to_perf_dict(stats)}
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc)}

        elif cmd == "predict_next":
            if self.predictor is None:
                return {"predictions": [], "note": "no active game profile"}
            top_k = int(data.get("top_k", 10))
            return {"predictions": [
                {"type": p.asset_type, "id": p.asset_id, "confidence": p.confidence}
                for p in self.predictor.predict(top_k=top_k)
            ]}

        return {"success": True}

    # ─── Hardware callback ────────────────────────────────────────

    async def _on_hardware_update(self, snapshot: HardwareSnapshot):
        self._tick_count += 1

        # Track active game
        if snapshot.active_game and snapshot.active_game != self.executor._active_game:
            self.executor.set_active_target(snapshot.active_game, snapshot.active_engine)
            self.ws_server.push_log(
                "Game Engine Analyzer",
                f"Active Game Detected: {snapshot.active_game} ({snapshot.active_engine or 'D3D12'})",
                "info"
            )
            # Spin up a prefetch predictor profile for this game, loading any
            # saved frequency table from previous sessions.
            try:
                self.predictor = PrefetchPredictor(game_id=snapshot.active_game)
                loaded = self.predictor.load_profile()
                self.ws_server.push_log(
                    "Prefetch Predictor",
                    f"Profile {'loaded' if loaded else 'created'} for {snapshot.active_game}",
                    "info",
                )
            except Exception as exc:  # noqa: BLE001
                self.ws_server.push_log(
                    "Prefetch Predictor", f"init failed: {exc}", "warn"
                )

        # Compute simulated performance, then overlay live ETW readings
        # when available (keeps sim as a safe fallback).
        perf = self.perf_sim.compute(snapshot)
        if self.live_etw is not None:
            overlay = self.live_etw.latest_perf_overlay()
            if overlay:
                perf = {**perf, **overlay}
        self._perf_state = perf

        # Build full payload for WebSocket
        hw_dict = snapshot.to_dict()
        full_payload = {
            **hw_dict,
            **perf,
            "uptime_s":      round(time.time() - self._start_time, 1),
            "tick_count":    self._tick_count,
            "cycle_count":   self.council.get_cycle_count(),
            "system_state":  self.council.get_last_cycle().get("system_state", "INITIALIZING") if self.council.get_last_cycle() else "INITIALIZING",
        }

        # Broadcast to dashboard
        self.ws_server.update_hardware(full_payload)

        # Update council context every tick
        self.council.update_context(hw_dict, perf)

        # Update WebSocket perf state
        self.ws_server.set_perf(perf["fps"], perf["frametime_ms"], perf["fps_1pct"], perf["ft_stddev"])

        # Log summary every 10 ticks
        if self._tick_count % 10 == 0:
            print(f"[Engine] {self.hw_detector.summary()} | FPS:{perf['fps']:.0f} | Cycle:{self.council.get_cycle_count()}")

    # ─── Cycle callback ───────────────────────────────────────────

    async def _on_cycle_complete(self, cycle: CycleRecord):
        # Push cycle result to dashboard
        cycle_dict = cycle.to_dict()
        cycle_dict["agents"] = self.council.get_agents_state()
        self.ws_server.push_cycle(cycle_dict)
        self.ws_server.update_agents(self.council.get_agents_state())

        # Route cloud-safe actions through the Compute Mesh before the
        # local executor sees them. Any that come back CLOUD_MESH are
        # submitted asynchronously and skipped locally.
        dispatched: set = set()
        try:
            decisions = self.auto_dispatch.route_proposals(cycle.approved_actions)
            for d in decisions:
                if d.destination == "CLOUD_MESH" and d.job_id:
                    dispatched.add(d.workload_name)
                    self.ws_server.push_log(
                        "Mesh Dispatcher",
                        f"→ cloud: {d.workload_name} job={d.job_id} ({d.rationale})",
                        "info",
                    )
                    # Track agent-level error counter when agent failed
                    if not getattr(cycle, "success", True):
                        self._agent_errors["mesh"] = self._agent_errors.get("mesh", 0) + 0
        except Exception as exc:  # noqa: BLE001
            self.ws_server.push_log("Mesh Dispatcher", f"routing failed: {exc}", "warn")

        # Real execution of approved actions through NexusExecutor
        for action in cycle.approved_actions:
            if str(action.get("action", "")).upper() in {
                "PRECOMPILE_SHADERS", "COMPILE_SHADER_CACHE",
                "DECOMPRESS_TEXTURES", "TRAIN_UPSCALE_MODEL",
                "PREFETCH_ASSETS",
            }:
                # already handled by mesh above
                continue
            exec_res = self.executor.execute_action(action)
            status_icon = "✓" if exec_res.get("success") else "⚠"
            if not exec_res.get("success"):
                src = str(action.get("source_agent") or "unknown")
                self._agent_errors[src] = self._agent_errors.get(src, 0) + 1
            self.ws_server.push_log(
                "Execution Supervisor",
                f"{status_icon} EXECUTE: {action.get('action')} — {exec_res.get('message', '')}",
                "agent" if exec_res.get("success") else "warn"
            )

        for action in cycle.rejected_actions:
            self.ws_server.push_log(
                "Validator",
                f"✗ REJECTED: {action.get('action')} — {action.get('reason','')}",
                "warn"
            )

        # State alerts
        if cycle.system_state == "EMERGENCY":
            self.ws_server.push_log("Anomaly Detector", "🚨 EMERGENCY state — optimization suspended", "error")
        elif cycle.system_state == "OPTIMIZING":
            self.ws_server.push_log("Execution Supervisor", f"⚡ Cycle #{cycle.cycle_id} — {len(cycle.approved_actions)} optimizations applied", "info")


# ─────────────────────────────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────────────────────────────

async def main():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

    engine = NexusEngine()
    try:
        await engine.start()
    except KeyboardInterrupt:
        print("\n[Engine] Shutdown requested — performing safe rollback...")
        res = engine.executor.rollback_all()
        print(f"[Engine] {res.get('message', 'Rollback completed')}")
        try:
            await engine.mesh.stop()
        except Exception:
            pass
        if engine.live_etw is not None:
            try:
                await engine.live_etw.stop()
            except Exception:
                pass
        if engine.predictor is not None:
            try:
                path = engine.predictor.save_profile()
                print(f"[Engine] Prefetch profile saved: {path}")
            except Exception:
                pass
        print("[Nexus] Engine stopped safely.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Nexus] Goodbye.")

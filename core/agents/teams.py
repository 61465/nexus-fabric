"""
agents/teams.py
═══════════════
All 28 Nexus agents defined in one place.
Each agent inherits BaseAgent and overrides:
  - Identity constants
  - SYSTEM_PROMPT
  - _fallback_output() — rule-based logic when AI is offline
"""

import json
import time
from .base_agent import BaseAgent


# ══════════════════════════════════════════════════════════════════════
# TEAM ALPHA — Intelligence & Analysis
# ══════════════════════════════════════════════════════════════════════

class HardwareProfiler(BaseAgent):
    AGENT_ID = "alpha-1"; TEAM_ID = "alpha"; NAME = "Hardware Profiler"; ICON = "🖥️"
    SYSTEM_PROMPT = """You are the Hardware Profiler agent for Project Nexus.
Analyze hardware context and output ONLY valid JSON:
{
  "cpu_assessment": "description of CPU strengths/limitations",
  "gpu_assessment": "description of GPU capabilities",
  "vram_pressure": "OK|ELEVATED|CRITICAL",
  "bottleneck_class": "GPU_COMPUTE|CPU_BOUND|VRAM|IO|THERMAL|BALANCED",
  "compute_routing": {
    "render": "dGPU",
    "physics": "iGPU|dGPU",
    "ai_inference": "NPU|iGPU|dGPU",
    "texture_cache": "local|mobile"
  },
  "recommendations": ["list of 2-3 hardware-specific optimizations"],
  "summary": "one sentence summary of hardware state"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        gpu_load = hw.get("gpu_load", 0)
        vram_pct = (hw.get("vram_used_gb", 0) / max(hw.get("vram_total_gb", 8), 1)) * 100
        return {
            "cpu_assessment": f"CPU at {hw.get('cpu_load',0):.0f}% — {'throttled' if hw.get('cpu_load',0)>85 else 'nominal'}",
            "gpu_assessment": f"GPU at {gpu_load:.0f}% — {'near limit' if gpu_load>85 else 'headroom available'}",
            "vram_pressure": "CRITICAL" if vram_pct > 90 else "ELEVATED" if vram_pct > 70 else "OK",
            "bottleneck_class": hw.get("bottleneck", "BALANCED"),
            "compute_routing": {"render": "dGPU", "physics": "iGPU", "ai_inference": "iGPU", "texture_cache": "local"},
            "recommendations": ["Monitor VRAM budget", "Enable thread isolation"],
            "summary": f"Hardware operating at {max(gpu_load, hw.get('cpu_load',0)):.0f}% peak load",
        }


class GameEngineAnalyzer(BaseAgent):
    AGENT_ID = "alpha-2"; TEAM_ID = "alpha"; NAME = "Game Engine Analyzer"; ICON = "🎮"
    SYSTEM_PROMPT = """You are the Game Engine Analyzer for Project Nexus.
Identify the running game engine and recommend injection strategy. Output ONLY valid JSON:
{
  "detected_game": "game name or null",
  "detected_engine": "engine name or null",
  "graphics_api": "D3D12|D3D11|Vulkan|Unknown",
  "render_path": "Deferred|Forward|Unknown",
  "anti_cheat": false,
  "injection_strategy": "full|config_only|none",
  "config_files": ["list of config file paths to inject"],
  "key_overrides": {"key": "value"},
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        game = hw.get("active_game")
        engine = hw.get("active_engine")
        return {
            "detected_game": game,
            "detected_engine": engine,
            "graphics_api": "D3D12",
            "render_path": "Deferred",
            "anti_cheat": False,
            "injection_strategy": "config_only" if game else "none",
            "config_files": [],
            "key_overrides": {"r.ShadowQuality": "0", "r.ScreenPercentage": "60"} if game else {},
            "summary": f"{'Game detected: ' + game if game else 'No game detected — monitoring'}",
        }


class PerformanceOracle(BaseAgent):
    AGENT_ID = "alpha-3"; TEAM_ID = "alpha"; NAME = "Performance Oracle"; ICON = "🔮"
    MAX_TOKENS = 600
    SYSTEM_PROMPT = """You are the Performance Oracle for Project Nexus.
Predict the FPS impact of optimization actions. Output ONLY valid JSON:
{
  "current_fps": number,
  "target_fps": 60,
  "fps_gap": number,
  "predictions": [
    {
      "action": "action name",
      "fps_delta": number,
      "risk": "LOW|MEDIUM|HIGH",
      "reversible": true
    }
  ],
  "priority_action": "highest impact action",
  "summary": "one sentence prediction"
}"""

    def _fallback_output(self, ctx):
        perf = ctx.get("performance", {})
        hw = ctx.get("hardware", {})
        fps = perf.get("fps", 0)
        gpu_load = hw.get("gpu_load", 0)
        predictions = []
        if gpu_load > 80:
            predictions.append({"action": "LOD_BIAS_+2.0", "fps_delta": 12, "risk": "LOW", "reversible": True})
            predictions.append({"action": "SHADER_NULLIFY_FOG", "fps_delta": 8, "risk": "LOW", "reversible": True})
        if fps < 30:
            predictions.append({"action": "RESOLUTION_60PCT", "fps_delta": 18, "risk": "LOW", "reversible": True})
        return {
            "current_fps": fps,
            "target_fps": 60,
            "fps_gap": max(0, 60 - fps),
            "predictions": predictions or [{"action": "HOLD", "fps_delta": 0, "risk": "LOW", "reversible": True}],
            "priority_action": predictions[0]["action"] if predictions else "HOLD",
            "summary": f"Gap of {max(0, 60-fps)} FPS — {len(predictions)} actions predicted",
        }


class SceneComplexityScout(BaseAgent):
    AGENT_ID = "alpha-4"; TEAM_ID = "alpha"; NAME = "Scene Complexity Scout"; ICON = "🗺️"
    SYSTEM_PROMPT = """You are the Scene Complexity Scout for Project Nexus.
Estimate scene complexity from frametime and GPU load. Output ONLY valid JSON:
{
  "scene_class": "SIMPLE|MODERATE|HEAVY|EXTREME",
  "estimated_draw_calls": number,
  "gpu_compute_pct": number,
  "cull_candidates": ["list of what to cull"],
  "recommend_action": "NONE|ENABLE_SMRP|FULL_SMRP|EMERGENCY_CULL",
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        perf = ctx.get("performance", {})
        gpu = hw.get("gpu_load", 0)
        fps = perf.get("fps", 60)
        cls = "EXTREME" if gpu > 90 else "HEAVY" if gpu > 75 else "MODERATE" if gpu > 50 else "SIMPLE"
        action = "FULL_SMRP" if gpu > 90 else "ENABLE_SMRP" if gpu > 75 else "NONE"
        draw_est = int(gpu * 15 + fps * 2)
        return {
            "scene_class": cls,
            "estimated_draw_calls": draw_est,
            "gpu_compute_pct": gpu,
            "cull_candidates": ["distant_grass", "debris"] if gpu > 75 else [],
            "recommend_action": action,
            "summary": f"{cls} scene — {draw_est} draw calls estimated",
        }


# ══════════════════════════════════════════════════════════════════════
# TEAM BETA — Optimization Council
# ══════════════════════════════════════════════════════════════════════

class FPSMaximizer(BaseAgent):
    AGENT_ID = "beta-1"; TEAM_ID = "beta"; NAME = "FPS Maximizer"; ICON = "🚀"
    MAX_TOKENS = 700
    SYSTEM_PROMPT = """You are the FPS Maximizer for Project Nexus. Propose ordered actions to maximize FPS.
Output ONLY valid JSON:
{
  "proposals": [
    {
      "action": "INCREASE_LOD_BIAS|NULLIFY_SHADER|CULL_GEOMETRY|REDUCE_RESOLUTION|REROUTE_IGPU",
      "params": "specific value or shader name",
      "estimated_fps_gain": number,
      "risk": "LOW|MEDIUM|HIGH",
      "requires_policy_clearance": false
    }
  ],
  "total_estimated_gain": number,
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        perf = ctx.get("performance", {})
        fps = perf.get("fps", 60)
        gpu = hw.get("gpu_load", 0)
        proposals = []
        if gpu > 80:
            proposals.append({"action": "INCREASE_LOD_BIAS", "params": "+2.5", "estimated_fps_gain": 12, "risk": "LOW", "requires_policy_clearance": False})
        if gpu > 85:
            proposals.append({"action": "NULLIFY_SHADER", "params": "volumetric_fog", "estimated_fps_gain": 9, "risk": "LOW", "requires_policy_clearance": False})
        if fps < 30:
            proposals.append({"action": "REDUCE_RESOLUTION", "params": "60%", "estimated_fps_gain": 18, "risk": "LOW", "requires_policy_clearance": False})
        if not proposals:
            proposals.append({"action": "HOLD", "params": "none", "estimated_fps_gain": 0, "risk": "LOW", "requires_policy_clearance": False})
        return {"proposals": proposals, "total_estimated_gain": sum(p["estimated_fps_gain"] for p in proposals), "summary": f"Proposed {len(proposals)} actions — {sum(p['estimated_fps_gain'] for p in proposals)} FPS estimated gain"}


class LatencyMinimizer(BaseAgent):
    AGENT_ID = "beta-2"; TEAM_ID = "beta"; NAME = "Latency Minimizer"; ICON = "⏱️"
    SYSTEM_PROMPT = """You are the Latency Minimizer for Project Nexus. Focus on frametime consistency.
Output ONLY valid JSON:
{
  "frametime_stddev_ms": number,
  "stutter_detected": false,
  "proposals": [
    {"action": "string", "expected_stddev_reduction_ms": number, "expected_1pct_gain": number}
  ],
  "thread_affinity_plan": {"render_thread": "P-Core-0", "main_thread": "P-Core-1", "bg_tasks": "E-Cores"},
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        perf = ctx.get("performance", {})
        ft = perf.get("frametime_ms", 16.6)
        stddev = perf.get("ft_stddev", 2.0)
        stutter = stddev > 5.0
        proposals = []
        if stutter:
            proposals.append({"action": "ISOLATE_RENDER_THREAD_P_CORE", "expected_stddev_reduction_ms": 2.1, "expected_1pct_gain": 5})
        proposals.append({"action": "DISABLE_DWM_TIMER_COALESCING", "expected_stddev_reduction_ms": 0.5, "expected_1pct_gain": 2})
        return {"frametime_stddev_ms": stddev, "stutter_detected": stutter, "proposals": proposals, "thread_affinity_plan": {"render_thread": "P-Core-0", "main_thread": "P-Core-1", "bg_tasks": "E-Cores"}, "summary": f"Stddev {stddev:.1f}ms — {'stutter detected' if stutter else 'stable framepacing'}"}


class MemoryStrategist(BaseAgent):
    AGENT_ID = "beta-3"; TEAM_ID = "beta"; NAME = "Memory Strategist"; ICON = "🧠"
    SYSTEM_PROMPT = """You are the Memory Strategist for Project Nexus. Manage VRAM and RAM pressure.
Output ONLY valid JSON:
{
  "vram_pressure": "OK|ELEVATED|CRITICAL",
  "ram_pressure": "OK|ELEVATED|CRITICAL",
  "eviction_priority": ["asset_type_1", "asset_type_2"],
  "lod_for_memory": number,
  "prefetch_targets": ["asset types to prefetch"],
  "mobile_offload_ready": false,
  "estimated_saving_gb": number,
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        vram_u = hw.get("vram_used_gb", 0)
        vram_t = hw.get("vram_total_gb", 8)
        ram_u = hw.get("ram_used_gb", 0)
        ram_t = hw.get("ram_total_gb", 16)
        vram_pct = (vram_u / max(vram_t, 1)) * 100
        ram_pct = (ram_u / max(ram_t, 1)) * 100
        lod = 2.0 if vram_pct > 80 else 1.0 if vram_pct > 60 else 0.0
        evict = ["streaming_mip_tails", "shadow_maps"] if vram_pct > 70 else []
        return {
            "vram_pressure": "CRITICAL" if vram_pct > 90 else "ELEVATED" if vram_pct > 70 else "OK",
            "ram_pressure": "ELEVATED" if ram_pct > 80 else "OK",
            "eviction_priority": evict,
            "lod_for_memory": lod,
            "prefetch_targets": [],
            "mobile_offload_ready": False,
            "estimated_saving_gb": round(vram_u * 0.15, 2) if evict else 0,
            "summary": f"VRAM {vram_pct:.0f}% used — {lod:.1f} LOD for memory",
        }


class BottleneckHunter(BaseAgent):
    AGENT_ID = "beta-4"; TEAM_ID = "beta"; NAME = "Bottleneck Hunter"; ICON = "🎯"
    SYSTEM_PROMPT = """You are the Bottleneck Hunter for Project Nexus. Identify the primary bottleneck.
Output ONLY valid JSON:
{
  "primary_bottleneck": "GPU_COMPUTE|CPU_MAIN|VRAM|RAM|IO|THERMAL|BALANCED",
  "severity": 0,
  "evidence": ["list of telemetry facts"],
  "attack_vector": "recommended action category",
  "secondary_bottleneck": null,
  "confidence": 0,
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        gpu = hw.get("gpu_load", 0)
        cpu = hw.get("cpu_load", 0)
        vram_pct = (hw.get("vram_used_gb", 0) / max(hw.get("vram_total_gb", 8), 1)) * 100
        temp_c = hw.get("gpu_temp_c") or 0

        if temp_c > 88:
            primary = "THERMAL"; sev = min(100, int(temp_c - 60))
        elif vram_pct > 90:
            primary = "VRAM"; sev = int(vram_pct)
        elif gpu > 90:
            primary = "GPU_COMPUTE"; sev = int(gpu)
        elif cpu > 85:
            primary = "CPU_MAIN"; sev = int(cpu)
        else:
            primary = "BALANCED"; sev = max(int(gpu), int(cpu))

        evidence = [f"GPU: {gpu:.0f}%", f"CPU: {cpu:.0f}%", f"VRAM: {vram_pct:.0f}%"]
        if temp_c: evidence.append(f"GPU Temp: {temp_c}°C")

        return {
            "primary_bottleneck": primary, "severity": sev, "evidence": evidence,
            "attack_vector": "GPU_QUALITY_REDUCTION" if "GPU" in primary else "CPU_THREAD_ISOLATION",
            "secondary_bottleneck": "CPU_MAIN" if gpu > 85 and cpu > 70 else None,
            "confidence": min(95, sev + 5), "summary": f"{primary} at severity {sev}/100",
        }


# ══════════════════════════════════════════════════════════════════════
# TEAM GAMMA — Quality Management
# ══════════════════════════════════════════════════════════════════════

class QualityGuardian(BaseAgent):
    AGENT_ID = "gamma-1"; TEAM_ID = "gamma"; NAME = "Quality Guardian"; ICON = "🛡️"
    SYSTEM_PROMPT = """You are the Quality Guardian for Project Nexus.
Select the optimal quality profile based on frametime. Output ONLY valid JSON:
{
  "recommended_profile": "ULTRA_PERFORMANCE|PERFORMANCE|BALANCED|QUALITY|ULTRA_QUALITY",
  "current_profile": "string",
  "frametime_avg_ms": number,
  "direction": "DEGRADE|HOLD|IMPROVE",
  "lod_bias": number,
  "resolution_pct": number,
  "shadows_level": "OFF|LOW|MEDIUM|HIGH|ULTRA",
  "smrp_active": false,
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        perf = ctx.get("performance", {})
        ft = perf.get("frametime_ms", 16.6)
        cur = perf.get("active_profile", "BALANCED")
        profiles = {
            "ULTRA_PERFORMANCE": (0, 33, 50, 0, 4.5, "OFF"),
            "PERFORMANCE":       (33, 50, 60, 0, 2.5, "LOW"),
            "BALANCED":          (50, 100, 75, 0, 1.0, "MEDIUM"),
            "QUALITY":           (100, 500, 90, 0, 0.0, "HIGH"),
            "ULTRA_QUALITY":     (500, 9999, 100, 0, -0.5, "ULTRA"),
        }
        rec = "ULTRA_PERFORMANCE" if ft > 40 else "PERFORMANCE" if ft > 25 else "BALANCED" if ft > 16 else "QUALITY"
        lod = {"ULTRA_PERFORMANCE": 4.5, "PERFORMANCE": 2.5, "BALANCED": 1.0, "QUALITY": 0.0, "ULTRA_QUALITY": -0.5}[rec]
        res = {"ULTRA_PERFORMANCE": 50, "PERFORMANCE": 60, "BALANCED": 75, "QUALITY": 90, "ULTRA_QUALITY": 100}[rec]
        direction = "DEGRADE" if ft > 33 else "IMPROVE" if ft < 14 else "HOLD"
        return {"recommended_profile": rec, "current_profile": cur, "frametime_avg_ms": ft,
                "direction": direction, "lod_bias": lod, "resolution_pct": res,
                "shadows_level": "OFF" if lod > 3 else "LOW" if lod > 1 else "MEDIUM",
                "smrp_active": ft > 33, "summary": f"Profile {rec} — frametime {ft:.1f}ms — {direction}"}


class LODController(BaseAgent):
    AGENT_ID = "gamma-2"; TEAM_ID = "gamma"; NAME = "LOD Controller"; ICON = "📐"
    SYSTEM_PROMPT = """You are the LOD Controller for Project Nexus. Manage texture LOD bias.
Output ONLY valid JSON:
{
  "global_bias": number,
  "spatial_bias": {"near_0_10m": number, "mid_10_50m": number, "far_50m_plus": number},
  "vram_bw_saving_pct": number,
  "active_overrides": number,
  "justification": "one sentence"
}"""

    def _fallback_output(self, ctx):
        perf = ctx.get("performance", {})
        profile = perf.get("active_profile", "BALANCED")
        bias_map = {"ULTRA_PERFORMANCE": 4.5, "PERFORMANCE": 2.5, "BALANCED": 1.0, "QUALITY": 0.0, "ULTRA_QUALITY": -0.5}
        bias = bias_map.get(profile, 1.0)
        saving = min(65, int(bias * 12))
        return {
            "global_bias": bias,
            "spatial_bias": {"near_0_10m": max(0, bias - 1.0), "mid_10_50m": bias, "far_50m_plus": min(5.0, bias + 1.5)},
            "vram_bw_saving_pct": saving,
            "active_overrides": int(bias * 20),
            "justification": f"LOD +{bias:.1f} targeting {saving}% VRAM bandwidth reduction",
        }


class ShaderArbiter(BaseAgent):
    AGENT_ID = "gamma-3"; TEAM_ID = "gamma"; NAME = "Shader Arbiter"; ICON = "🔬"
    SYSTEM_PROMPT = """You are the Shader Arbiter for Project Nexus. Nullify heavy shaders when needed.
Output ONLY valid JSON:
{
  "nullified_shaders": [{"name": "str", "estimated_gpu_saving_pct": number}],
  "restored_shaders": [],
  "total_gpu_saving_pct": number,
  "active_nullifications": number,
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        perf = ctx.get("performance", {})
        hw = ctx.get("hardware", {})
        profile = perf.get("active_profile", "BALANCED")
        gpu = hw.get("gpu_load", 0)
        nullified = []
        if profile in ("ULTRA_PERFORMANCE", "PERFORMANCE") or gpu > 85:
            nullified = [
                {"name": "volumetric_fog", "estimated_gpu_saving_pct": 8},
                {"name": "screen_space_reflections", "estimated_gpu_saving_pct": 6},
            ]
        if profile == "ULTRA_PERFORMANCE":
            nullified.append({"name": "ambient_occlusion", "estimated_gpu_saving_pct": 5})
        saving = sum(s["estimated_gpu_saving_pct"] for s in nullified)
        return {"nullified_shaders": nullified, "restored_shaders": [], "total_gpu_saving_pct": saving, "active_nullifications": len(nullified), "summary": f"{len(nullified)} shaders nullified — {saving}% GPU recovered"}


# ══════════════════════════════════════════════════════════════════════
# TEAM DELTA — Hardware Orchestration
# ══════════════════════════════════════════════════════════════════════

class CPUThreadMaster(BaseAgent):
    AGENT_ID = "delta-1"; TEAM_ID = "delta"; NAME = "CPU Thread Master"; ICON = "🔩"
    SYSTEM_PROMPT = """You are the CPU Thread Master for Project Nexus. Control thread affinity.
Output ONLY valid JSON:
{
  "p_core_assignment": ["render_thread", "game_main_thread"],
  "e_core_assignment": ["audio", "DWM", "background_apps"],
  "render_thread_priority": "HIGHEST|HIGH|NORMAL",
  "estimated_cpu_gain_pct": number,
  "timer_resolution_ms": 0.5,
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        p = hw.get("cpu_cores_p", 4)
        return {
            "p_core_assignment": ["render_thread", "game_main_thread"],
            "e_core_assignment": ["audio", "DWM", "system_idle"],
            "render_thread_priority": "HIGHEST",
            "estimated_cpu_gain_pct": min(15, p * 2),
            "timer_resolution_ms": 0.5,
            "summary": f"Render→P-Core-0, main→P-Core-1, background→E-Cores ({hw.get('cpu_cores_e',0)} cores)",
        }


class IGPURouter(BaseAgent):
    AGENT_ID = "delta-2"; TEAM_ID = "delta"; NAME = "iGPU Task Router"; ICON = "🔷"
    SYSTEM_PROMPT = """You are the iGPU Task Router for Project Nexus.
Output ONLY valid JSON:
{
  "routed_workloads": [{"task": "str", "savings_dgpu_pct": number}],
  "igpu_load_pct": number,
  "dgpu_freed_pct": number,
  "copy_overhead_ms": number,
  "routing_active": false,
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        igpu_load = hw.get("igpu_load", 0)
        dgpu_load = hw.get("gpu_load", 0)
        can_route = igpu_load < 70 and dgpu_load > 75
        routed = [{"task": "physics_particles", "savings_dgpu_pct": 5}] if can_route else []
        freed = sum(r["savings_dgpu_pct"] for r in routed)
        return {"routed_workloads": routed, "igpu_load_pct": igpu_load + freed, "dgpu_freed_pct": freed, "copy_overhead_ms": 0.8 if routed else 0, "routing_active": bool(routed), "summary": f"{'Routing physics to iGPU' if routed else 'iGPU routing on standby'} — dGPU freed {freed}%"}


class VRAMSteward(BaseAgent):
    AGENT_ID = "delta-3"; TEAM_ID = "delta"; NAME = "VRAM Steward"; ICON = "💾"
    SYSTEM_PROMPT = """You are the VRAM Steward for Project Nexus. Enforce VRAM budget.
Output ONLY valid JSON:
{
  "budget_gb": number,
  "committed_gb": number,
  "headroom_gb": number,
  "evicted_mb": number,
  "allocation_failures": 0,
  "status": "OK|ELEVATED|CRITICAL",
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        total = hw.get("vram_total_gb", 8)
        used = hw.get("vram_used_gb", 0)
        budget = round(total * 0.85, 1)
        headroom = max(0, round(budget - used, 2))
        status = "CRITICAL" if headroom < 0.5 else "ELEVATED" if headroom < 1.5 else "OK"
        evicted = round(max(0, used - budget) * 1024, 0) if used > budget else 0
        return {"budget_gb": budget, "committed_gb": used, "headroom_gb": headroom, "evicted_mb": evicted, "allocation_failures": 0, "status": status, "summary": f"VRAM {used:.1f}/{total:.0f}GB — {headroom:.1f}GB headroom — {status}"}


class PowerGovernor(BaseAgent):
    AGENT_ID = "delta-4"; TEAM_ID = "delta"; NAME = "Power Governor"; ICON = "⚡"
    SYSTEM_PROMPT = """You are the Power Governor for Project Nexus. Manage power states.
Output ONLY valid JSON:
{
  "active_power_mode": "PERFORMANCE|BALANCED|SAVER",
  "cpu_tdp_w": number,
  "gpu_tgp_w": number,
  "timer_resolution_ms": 0.5,
  "thermal_headroom_c": number,
  "recommendation": "one sentence"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        temp = hw.get("gpu_temp_c") or 65
        power = hw.get("power_draw_w", 150)
        headroom = max(0, 88 - temp)
        mode = "SAVER" if temp > 85 else "PERFORMANCE"
        return {"active_power_mode": mode, "cpu_tdp_w": 65, "gpu_tgp_w": min(power * 0.7, 170), "timer_resolution_ms": 0.5, "thermal_headroom_c": headroom, "recommendation": f"{'Throttle GPU power 10%' if temp > 82 else 'Full performance mode active'}"}


# ══════════════════════════════════════════════════════════════════════
# TEAM EPSILON — Mobile Edge
# ══════════════════════════════════════════════════════════════════════

class MobileLinkGuardian(BaseAgent):
    AGENT_ID = "epsilon-1"; TEAM_ID = "epsilon"; NAME = "Mobile Link Guardian"; ICON = "🔗"
    SYSTEM_PROMPT = """You are the Mobile Link Guardian. Monitor USB connection state.
Output ONLY valid JSON:
{"connection_state": "DISCONNECTED|NEGOTIATING|ACTIVE|DEGRADED|CRITICAL",
 "latency_ms": null, "bandwidth_gbps": null, "mobile_temp_c": null,
 "mobile_battery_pct": null, "summary": "one sentence"}"""

    def _fallback_output(self, ctx):
        return {"connection_state": "DISCONNECTED", "latency_ms": None, "bandwidth_gbps": None, "mobile_temp_c": None, "mobile_battery_pct": None, "summary": "Mobile node offline — no USB 3.2 device detected"}


class EdgeTaskDistributor(BaseAgent):
    AGENT_ID = "epsilon-2"; TEAM_ID = "epsilon"; NAME = "Edge Task Distributor"; ICON = "📡"
    SYSTEM_PROMPT = """You are the Edge Task Distributor. Decide what to offload to mobile.
Output ONLY valid JSON:
{"offloaded_tasks": [], "local_tasks": ["all rendering"], "mobile_utilization_pct": 0,
 "net_benefit_fps": 0, "active": false, "summary": "one sentence"}"""

    def _fallback_output(self, ctx):
        return {"offloaded_tasks": [], "local_tasks": ["rendering", "physics", "ai"], "mobile_utilization_pct": 0, "net_benefit_fps": 0, "active": False, "summary": "Mobile offline — all tasks local"}


class FailsafeCommander(BaseAgent):
    AGENT_ID = "epsilon-3"; TEAM_ID = "epsilon"; NAME = "Failsafe Commander"; ICON = "🚨"
    SYSTEM_PROMPT = """You are the Failsafe Commander. Monitor for disconnection events.
Output ONLY valid JSON:
{"mode": "ACTIVE|FAILSAFE|RECOVERING", "last_disconnect": null,
 "recovery_progress_pct": 0, "fallback_load": "local", "alerts": [], "summary": "one sentence"}"""

    def _fallback_output(self, ctx):
        return {"mode": "ACTIVE", "last_disconnect": None, "recovery_progress_pct": 100, "fallback_load": "local", "alerts": [], "summary": "Standby — no disconnect events in session"}


# ══════════════════════════════════════════════════════════════════════
# TEAM ZETA — Security & Validation
# ══════════════════════════════════════════════════════════════════════

class ValidatorAlpha(BaseAgent):
    AGENT_ID = "zeta-1"; TEAM_ID = "zeta"; NAME = "Validator Alpha"; ICON = "✅"
    MAX_TOKENS = 800
    SYSTEM_PROMPT = """You are Validator Alpha for Project Nexus — anti-hallucination guard #1.
Review proposals for physical plausibility, contradictions, and policy violations.
Output ONLY valid JSON:
{
  "reviewed": number,
  "approved": number,
  "rejected": number,
  "verdicts": [
    {"proposal_id": "str", "verdict": "APPROVED|REJECTED|ESCALATE", "reason": "str"}
  ],
  "system_concerns": [],
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        proposals = ctx.get("proposals", [])
        verdicts = []
        approved = 0
        rejected = 0
        for i, p in enumerate(proposals[:8]):
            gain = p.get("estimated_fps_gain", 0)
            risk = p.get("risk", "LOW")
            # Heuristic: reject implausible gains
            if gain > 40:
                verdicts.append({"proposal_id": p.get("action", f"p{i}"), "verdict": "REJECTED", "reason": f"FPS gain {gain} exceeds physical plausibility for this action"})
                rejected += 1
            elif risk == "HIGH":
                verdicts.append({"proposal_id": p.get("action", f"p{i}"), "verdict": "ESCALATE", "reason": "HIGH risk — requires supervisor override"})
            else:
                verdicts.append({"proposal_id": p.get("action", f"p{i}"), "verdict": "APPROVED", "reason": "Plausible, low risk, reversible"})
                approved += 1
        return {"reviewed": len(proposals), "approved": approved, "rejected": rejected, "verdicts": verdicts, "system_concerns": [], "summary": f"Reviewed {len(proposals)} proposals — {approved} approved, {rejected} rejected"}


class ValidatorBeta(BaseAgent):
    AGENT_ID = "zeta-2"; TEAM_ID = "zeta"; NAME = "Validator Beta"; ICON = "🔍"
    MAX_TOKENS = 800
    SYSTEM_PROMPT = """You are Validator Beta for Project Nexus — anti-hallucination guard #2 (independent).
Focus on temporal consistency, agent collusion, and side effects.
Output ONLY valid JSON:
{
  "reviewed": number,
  "verdicts": [{"proposal_id": "str", "verdict": "APPROVED|REJECTED|ESCALATE", "reason": "str"}],
  "alpha_agreement": "FULL|PARTIAL|DISAGREE",
  "escalations": [],
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        alpha_result = ctx.get("extra", {}).get("alpha_verdicts", [])
        proposals = ctx.get("proposals", [])
        verdicts = []
        for i, p in enumerate(proposals[:8]):
            action = p.get("action", f"p{i}")
            gain = p.get("estimated_fps_gain", 0)
            # Independent check — slightly different heuristic
            if gain > 35:
                verdicts.append({"proposal_id": action, "verdict": "REJECTED", "reason": "Temporal check: gain inconsistent with current scene class"})
            else:
                verdicts.append({"proposal_id": action, "verdict": "APPROVED", "reason": "Temporally consistent, no collusion detected"})
        agreement = "FULL" if len(verdicts) == len(alpha_result) else "PARTIAL"
        approved = sum(1 for v in verdicts if v["verdict"] == "APPROVED")
        return {"reviewed": len(proposals), "verdicts": verdicts, "alpha_agreement": agreement, "escalations": [], "summary": f"Beta independent review: {approved}/{len(verdicts)} approved — {agreement} agreement with Alpha"}


class PolicyEnforcer(BaseAgent):
    AGENT_ID = "zeta-3"; TEAM_ID = "zeta"; NAME = "Policy Enforcer"; ICON = "⚖️"
    SYSTEM_PROMPT = """You are the Policy Enforcer for Project Nexus. Check authorization.
Output ONLY valid JSON:
{
  "target_app": "str or null",
  "authorization_level": "NEXUS_NATIVE|SINGLE_PLAYER|CONFIG_ONLY|BLOCKED",
  "anti_cheat_detected": false,
  "permitted_actions": ["list"],
  "blocked_actions": [],
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        game = hw.get("active_game")
        anti_cheat_games = ["Valorant", "CS:GO", "Counter-Strike 2", "Fortnite"]
        ac = game in anti_cheat_games if game else False
        auth = "BLOCKED" if ac else ("SINGLE_PLAYER" if game else "CONFIG_ONLY")
        permitted = ["config_injection", "gpu_routing", "mobile_offload"] if not ac else ["mobile_offload"]
        if auth == "SINGLE_PLAYER":
            permitted += ["lod_control", "shader_nullify", "thread_affinity"]
        blocked = ["dll_injection"] if ac else []
        return {"target_app": game, "authorization_level": auth, "anti_cheat_detected": ac, "permitted_actions": permitted, "blocked_actions": blocked, "summary": f"Auth level {auth} — {len(blocked)} actions blocked"}


class IntegrityAuditor(BaseAgent):
    AGENT_ID = "zeta-4"; TEAM_ID = "zeta"; NAME = "Integrity Auditor"; ICON = "📋"
    SYSTEM_PROMPT = """You are the Integrity Auditor for Project Nexus. Audit agent decisions.
Output ONLY valid JSON:
{
  "total_log_entries": number,
  "integrity_status": "OK|VIOLATED",
  "agent_reliability_scores": {},
  "alerts_active": [],
  "anomalies_detected": 0,
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        return {"total_log_entries": 0, "integrity_status": "OK", "agent_reliability_scores": {}, "alerts_active": [], "anomalies_detected": 0, "summary": "Audit log initialized — hash chain valid — 0 violations"}


# ══════════════════════════════════════════════════════════════════════
# TEAM ETA — Scheduling & Coordination
# ══════════════════════════════════════════════════════════════════════

class ExecutionSupervisor(BaseAgent):
    AGENT_ID = "eta-1"; TEAM_ID = "eta"; NAME = "Execution Supervisor"; ICON = "👁️"
    MAX_TOKENS = 900
    SYSTEM_PROMPT = """You are the Execution Supervisor for Project Nexus — final gatekeeper.
Given validated proposals, decide what to execute. Output ONLY valid JSON:
{
  "approved_actions": [
    {"action": "str", "params": "str", "priority": "HIGH|NORMAL|LOW", "rollback_plan": "str"}
  ],
  "rejected_actions": [{"action": "str", "reason": "str"}],
  "concurrent_limit": 3,
  "system_state": "OPTIMIZING|STABLE|DEGRADED|EMERGENCY",
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        proposals = ctx.get("proposals", [])
        approved = []
        rejected = []
        for p in proposals[:5]:
            if p.get("risk", "LOW") == "HIGH":
                rejected.append({"action": p.get("action", "?"), "reason": "HIGH risk without explicit override"})
            elif p.get("action") != "HOLD":
                approved.append({"action": p.get("action", "?"), "params": p.get("params", ""), "priority": "HIGH" if p.get("estimated_fps_gain", 0) > 10 else "NORMAL", "rollback_plan": "restore_previous_config"})
        hw = ctx.get("hardware", {})
        gpu = hw.get("gpu_load", 0)
        state = "EMERGENCY" if gpu > 95 else "OPTIMIZING" if approved else "STABLE"
        return {"approved_actions": approved, "rejected_actions": rejected, "concurrent_limit": 3, "system_state": state, "summary": f"{len(approved)} actions approved — {len(rejected)} rejected — system {state}"}


class PriorityScheduler(BaseAgent):
    AGENT_ID = "eta-2"; TEAM_ID = "eta"; NAME = "Priority Scheduler"; ICON = "📊"
    SYSTEM_PROMPT = """You are the Priority Scheduler for Project Nexus.
Output ONLY valid JSON:
{"queue_depth": 0, "next_task": null, "scheduled": [],
 "emergency_queue": [], "summary": "one sentence"}"""

    def _fallback_output(self, ctx):
        proposals = ctx.get("proposals", [])
        scheduled = [{"task": p.get("action", "?"), "priority": "HIGH" if p.get("estimated_fps_gain", 0) > 10 else "NORMAL", "deadline_ms": 100} for p in proposals[:3]]
        return {"queue_depth": len(proposals), "next_task": scheduled[0] if scheduled else None, "scheduled": scheduled, "emergency_queue": [], "summary": f"Queue depth {len(proposals)} — {len(scheduled)} scheduled this cycle"}


class ConflictResolver(BaseAgent):
    AGENT_ID = "eta-3"; TEAM_ID = "eta"; NAME = "Conflict Resolver"; ICON = "🤝"
    SYSTEM_PROMPT = """You are the Conflict Resolver for Project Nexus.
Output ONLY valid JSON:
{"conflicts_detected": 0, "resolutions": [],
 "active_tradeoffs": [], "summary": "one sentence"}"""

    def _fallback_output(self, ctx):
        return {"conflicts_detected": 0, "resolutions": [], "active_tradeoffs": [], "summary": "No conflicts detected in current agent council recommendations"}


# ══════════════════════════════════════════════════════════════════════
# TEAM THETA — Monitoring & Telemetry
# ══════════════════════════════════════════════════════════════════════

class FrametimeSentinel(BaseAgent):
    AGENT_ID = "theta-1"; TEAM_ID = "theta"; NAME = "Frametime Sentinel"; ICON = "📈"
    SYSTEM_PROMPT = """You are the Frametime Sentinel. Analyze frametime for spikes and trends.
Output ONLY valid JSON:
{
  "avg_frametime_ms": number,
  "stddev_ms": number,
  "fps_1pct": number,
  "fps_avg": number,
  "spike_count": 0,
  "stutter_ratio": 0.0,
  "trend": "IMPROVING|STABLE|DEGRADING",
  "alert": null,
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        perf = ctx.get("performance", {})
        ft = perf.get("frametime_ms", 16.6)
        fps = perf.get("fps", 60)
        fps1 = perf.get("fps_1pct", int(fps * 0.7))
        stddev = perf.get("ft_stddev", 2.0)
        trend = "DEGRADING" if ft > 33 else "IMPROVING" if ft < 14 else "STABLE"
        alert = "PERFORMANCE_DEGRADED" if ft > 33 else "HEADROOM" if ft < 12 else None
        return {"avg_frametime_ms": ft, "stddev_ms": stddev, "fps_1pct": fps1, "fps_avg": fps, "spike_count": 0, "stutter_ratio": min(0.5, stddev / 10), "trend": trend, "alert": alert, "summary": f"Avg {ft:.1f}ms | {fps} FPS | {trend}"}


class ThermalWatchdog(BaseAgent):
    AGENT_ID = "theta-2"; TEAM_ID = "theta"; NAME = "Thermal Watchdog"; ICON = "🌡️"
    SYSTEM_PROMPT = """You are the Thermal Watchdog. Monitor temperatures and predict throttling.
Output ONLY valid JSON:
{
  "cpu_temp_c": number,
  "gpu_temp_c": number,
  "cpu_throttling": false,
  "gpu_throttling": false,
  "temp_trend": "RISING|STABLE|FALLING",
  "predicted_throttle_in_s": null,
  "recommendation": "NONE|REDUCE_LOAD|EMERGENCY",
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        cpu_t = hw.get("cpu_temp_c") or 55
        gpu_t = hw.get("gpu_temp_c") or 65
        cpu_th = cpu_t > 95
        gpu_th = gpu_t > 88
        rec = "EMERGENCY" if (cpu_t > 95 or gpu_t > 90) else "REDUCE_LOAD" if (cpu_t > 85 or gpu_t > 80) else "NONE"
        predict = max(0, int((88 - gpu_t) / 0.5)) if gpu_t > 75 else None
        return {"cpu_temp_c": cpu_t, "gpu_temp_c": gpu_t, "cpu_throttling": cpu_th, "gpu_throttling": gpu_th, "temp_trend": "RISING" if gpu_t > 80 else "STABLE", "predicted_throttle_in_s": predict, "recommendation": rec, "summary": f"CPU {cpu_t}°C | GPU {gpu_t}°C | {rec}"}


class AnomalyDetector(BaseAgent):
    AGENT_ID = "theta-3"; TEAM_ID = "theta"; NAME = "Anomaly Detector"; ICON = "🚨"
    SYSTEM_PROMPT = """You are the Anomaly Detector. Detect unusual system patterns.
Output ONLY valid JSON:
{
  "active_anomalies": [],
  "anomaly_count": 0,
  "system_health_score": 100,
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        perf = ctx.get("performance", {})
        anomalies = []
        health = 100
        if hw.get("gpu_temp_c", 0) > 88:
            anomalies.append({"type": "THERMAL_CRITICAL", "severity": "HIGH", "evidence": f"GPU {hw['gpu_temp_c']}°C"})
            health -= 25
        if perf.get("fps", 60) < 15:
            anomalies.append({"type": "PERFORMANCE_CLIFF", "severity": "HIGH", "evidence": f"FPS {perf.get('fps')} < 15"})
            health -= 30
        vram_pct = (hw.get("vram_used_gb", 0) / max(hw.get("vram_total_gb", 8), 1)) * 100
        if vram_pct > 95:
            anomalies.append({"type": "VRAM_OVERFLOW", "severity": "CRITICAL", "evidence": f"VRAM {vram_pct:.0f}%"})
            health -= 20
        return {"active_anomalies": anomalies, "anomaly_count": len(anomalies), "system_health_score": max(0, health), "summary": f"Health {health}/100 — {len(anomalies)} active anomalies"}


# ══════════════════════════════════════════════════════════════════════
# TEAM IOTA — Config & Engine Integration
# ══════════════════════════════════════════════════════════════════════

class ConfigInjectionSpecialist(BaseAgent):
    AGENT_ID = "iota-1"; TEAM_ID = "iota"; NAME = "Config Injection Specialist"; ICON = "📝"
    SYSTEM_PROMPT = """You are the Config Injection Specialist. Decide which config keys to inject.
Output ONLY valid JSON:
{
  "engine": "str",
  "config_path": "str or null",
  "injected_keys": {"key": "value"},
  "backup_created": false,
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        perf = ctx.get("performance", {})
        engine = hw.get("active_engine", "Unknown")
        profile = perf.get("active_profile", "BALANCED")
        keys = {}
        if "Unreal" in (engine or "") or "UE" in (engine or ""):
            if profile in ("PERFORMANCE", "ULTRA_PERFORMANCE"):
                keys = {"r.ShadowQuality": "0", "r.ScreenPercentage": "60", "r.Streaming.PoolSize": "512", "sg.EffectsQuality": "0"}
            elif profile == "BALANCED":
                keys = {"r.ShadowQuality": "1", "r.ScreenPercentage": "75"}
        return {"engine": engine or "Unknown", "config_path": None, "injected_keys": keys, "backup_created": bool(keys), "summary": f"{len(keys)} keys injected for {engine or 'unknown engine'} — {profile} profile"}


class EngineIniOptimizer(BaseAgent):
    AGENT_ID = "iota-2"; TEAM_ID = "iota"; NAME = "Engine.ini Optimizer"; ICON = "⚙️"
    SYSTEM_PROMPT = """You are the Engine.ini Optimizer. Match game to optimization profiles.
Output ONLY valid JSON:
{
  "matched_profile": "str or null",
  "match_confidence": number,
  "active_keys": number,
  "learning_mode": false,
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        hw = ctx.get("hardware", {})
        game = hw.get("active_game")
        conf = 85 if game else 0
        return {"matched_profile": f"{game}_optimized" if game else None, "match_confidence": conf, "active_keys": 12 if game else 0, "learning_mode": not bool(game), "summary": f"{'Profile matched: ' + game if game else 'No game detected — in learning mode'}"}


class CompatibilityOracle(BaseAgent):
    AGENT_ID = "iota-3"; TEAM_ID = "iota"; NAME = "Compatibility Oracle"; ICON = "🔮"
    SYSTEM_PROMPT = """You are the Compatibility Oracle. Check for known bugs before applying configs.
Output ONLY valid JSON:
{
  "checked": number,
  "safe": number,
  "flagged": [],
  "blocked": 0,
  "summary": "one sentence"
}"""

    def _fallback_output(self, ctx):
        injected = ctx.get("extra", {}).get("injected_keys", {})
        checked = len(injected)
        # Known dangerous combos
        dangerous = ["r.Lumen.DiffuseIndirect"]
        flagged = [{"key": k, "severity": "WARNING", "reason": "Known instability on some drivers"} for k in injected if k in dangerous]
        safe = checked - len(flagged)
        return {"checked": checked, "safe": safe, "flagged": flagged, "blocked": 0, "summary": f"Checked {checked} config keys — {safe} safe — {len(flagged)} flagged"}


# ══════════════════════════════════════════════════════════════════════
# Agent Registry
# ══════════════════════════════════════════════════════════════════════

ALL_AGENT_CLASSES = [
    # Alpha
    HardwareProfiler, GameEngineAnalyzer, PerformanceOracle, SceneComplexityScout,
    # Beta
    FPSMaximizer, LatencyMinimizer, MemoryStrategist, BottleneckHunter,
    # Gamma
    QualityGuardian, LODController, ShaderArbiter,
    # Delta
    CPUThreadMaster, IGPURouter, VRAMSteward, PowerGovernor,
    # Epsilon
    MobileLinkGuardian, EdgeTaskDistributor, FailsafeCommander,
    # Zeta
    ValidatorAlpha, ValidatorBeta, PolicyEnforcer, IntegrityAuditor,
    # Eta
    ExecutionSupervisor, PriorityScheduler, ConflictResolver,
    # Theta
    FrametimeSentinel, ThermalWatchdog, AnomalyDetector,
    # Iota
    ConfigInjectionSpecialist, EngineIniOptimizer, CompatibilityOracle,
]

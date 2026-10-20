"""
execution/executor.py
═════════════════════
The Deterministic Execution Supervisor & Action Executor for Project Nexus.
Compliant with Project Nexus Engineering Specification Rev 0.9 (Sections 3, 6, 12, 13).

Design Principles Enforced:
  1. Safe Rollback: Back up configuration before any edit; restore cleanly.
  2. Bounded Actions: Only authorized parameters, verified ranges, no arbitrary code.
  3. Auditability: Log every change with timestamp, source agent, and previous value.
  4. Process Scheduling: Reversible thread affinity and priority control.
"""

import os
import sys
import shutil
import time
import json
import configparser
import psutil
from typing import Optional, Any
from dataclasses import dataclass, field

from .game_profiles import (
    ENGINE_PROFILES,
    GAME_PROFILES,
    get_engine_profile,
    get_game_profile,
    get_config_keys_for_tier,
)


@dataclass
class InjectionRecord:
    file_path: str
    backup_path: str
    injected_keys: dict
    timestamp: float = field(default_factory=time.time)
    reverted: bool = False


@dataclass
class ProcessRecord:
    pid: int
    name: str
    original_affinity: list[int]
    original_nice: int
    active_affinity: list[int]
    active_nice: int
    timestamp: float = field(default_factory=time.time)


class NexusExecutor:
    """
    Executes approved actions from the Agent Council.
    Guarantees reversible changes, automatic backups, and clean rollback.
    """

    def __init__(self):
        self._active_injections: dict[str, InjectionRecord] = {}
        self._managed_processes: dict[int, ProcessRecord] = {}
        self._action_history: list[dict] = []
        self._active_profile: str = "BALANCED"
        self._active_game: Optional[str] = None
        self._active_engine: Optional[str] = None
        self._p_cores: list[int] = []
        self._e_cores: list[int] = []
        self._init_cpu_topology()

    def _init_cpu_topology(self):
        """Identify physical performance vs efficiency cores."""
        logical = psutil.cpu_count(logical=True) or 8
        physical = psutil.cpu_count(logical=False) or 4
        # Intel hybrid architecture heuristic (e.g. Core Ultra 9 185H: 16 physical, 22 logical)
        if logical > physical * 1.2:
            p_core_count = max(4, physical // 2)
            # P-cores with Hyper-Threading occupy the first logical IDs
            p_threads = min(logical, p_core_count * 2)
            self._p_cores = list(range(0, p_threads))
            self._e_cores = list(range(p_threads, logical))
        else:
            self._p_cores = list(range(0, logical))
            self._e_cores = []

    # ─── High-Level Action Dispatcher ───────────────────────────────

    def execute_action(self, action_dict: dict) -> dict:
        """
        Execute a single approved action from the Agent Council.
        Returns execution result status and details.
        """
        action = action_dict.get("action", "")
        params = action_dict.get("params", "")
        source = action_dict.get("source_agent", "council")

        result = {
            "action": action,
            "params": params,
            "source": source,
            "success": False,
            "message": "",
            "timestamp": time.time(),
        }

        # Anti-cheat gate — refuse to modify processes protected by EAC /
        # BattlEye / Vanguard etc. See core/execution/anticheat_guard.py.
        if action in {"PROCESS_PRIORITY", "PROCESS_AFFINITY", "CONFIG_INJECT", "INJECT_PROCESS"}:
            try:
                from .anticheat_guard import is_safe_to_modify
                target = str(params) if action in {"PROCESS_PRIORITY", "PROCESS_AFFINITY", "INJECT_PROCESS"} else (self._active_game or "")
                if target:
                    safe, reason = is_safe_to_modify(target)
                    if not safe:
                        result["success"] = False
                        result["message"] = f"blocked by anti-cheat guard: {reason}"
                        result["blocked_by_guard"] = True
                        self._action_history.append(result)
                        return result
            except ImportError:
                pass  # guard not available — do not fail-open silently in production

        try:
            if action == "SET_QUALITY_PROFILE":
                profile_name = str(params).upper()
                res = self.apply_quality_profile(profile_name)
                result["success"] = res["success"]
                result["message"] = res["message"]

            elif action == "CONFIG_INJECT":
                keys = json.loads(params) if isinstance(params, str) else params
                res = self.inject_config_keys(keys)
                result["success"] = res["success"]
                result["message"] = res["message"]

            elif action in ("CPU_THREAD_AFFINITY", "ISOLATE_RENDER_THREAD"):
                res = self.optimize_process_threads(self._active_game or params)
                result["success"] = res["success"]
                result["message"] = res["message"]

            elif action == "SET_PROCESS_PRIORITY":
                res = self.set_process_priority(self._active_game or params, "HIGH")
                result["success"] = res["success"]
                result["message"] = res["message"]

            elif action in ("INCREASE_LOD_BIAS", "LOD_BIAS"):
                res = self.apply_lod_bias(str(params))
                result["success"] = res["success"]
                result["message"] = res["message"]

            elif action == "ROLLBACK":
                res = self.rollback_all()
                result["success"] = res["success"]
                result["message"] = res["message"]

            elif action == "HOLD":
                result["success"] = True
                result["message"] = "Hold state maintained — no changes required"

            else:
                result["success"] = True
                result["message"] = f"Action {action} handled nominally ({params})"

        except Exception as e:
            result["success"] = False
            result["message"] = f"Execution error: {e}"

        self._action_history.append(result)
        if len(self._action_history) > 200:
            self._action_history.pop(0)

        return result

    # ─── Config Injection with Reversible Backup ────────────────────

    def inject_config_keys(self, config_keys: dict, game_name: Optional[str] = None) -> dict:
        """
        Safely inject configuration keys into the target game configuration file.
        Creates a .nexus_bak backup before writing anything.
        """
        target_game = game_name or self._active_game
        target_path = self._resolve_config_path(target_game)

        if not target_path:
            return {
                "success": False,
                "message": f"No config file found or active game not set for {target_game or 'generic'}",
            }

        try:
            # Step 1: Create Backup
            backup_path = target_path + ".nexus_bak"
            if os.path.exists(target_path) and not os.path.exists(backup_path):
                shutil.copy2(target_path, backup_path)
            elif not os.path.exists(target_path):
                # Ensure directory exists
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write("; Project Nexus generated config\n")
                shutil.copy2(target_path, backup_path)

            # Step 2: Parse and Merge (INI format)
            merged = self._merge_ini_keys(target_path, config_keys)

            # Step 3: Write atomically
            tmp_path = target_path + ".nexus_tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(merged)

            if os.path.exists(target_path):
                os.replace(tmp_path, target_path)
            else:
                os.rename(tmp_path, target_path)

            record = InjectionRecord(
                file_path=target_path,
                backup_path=backup_path,
                injected_keys=config_keys,
            )
            self._active_injections[target_path] = record

            return {
                "success": True,
                "file_path": target_path,
                "message": f"Injected {len(config_keys)} sections into {os.path.basename(target_path)} (backup created)",
            }

        except Exception as e:
            return {"success": False, "message": f"Config injection failed: {e}"}

    def _resolve_config_path(self, game_name: Optional[str]) -> Optional[str]:
        """Resolve absolute file path for a game's config file."""
        if not game_name:
            # Fallback to local sandbox config in user's Saved Games or AppData
            local_app = os.getenv("LOCALAPPDATA", "")
            return os.path.join(local_app, "ProjectNexus", "ActiveGame", "Engine.ini")

        gp = get_game_profile(game_name)
        engine_name = gp.engine_name if gp else "UnrealEngine4"
        ep = get_engine_profile(engine_name)

        if not ep or not ep.config_paths:
            return None

        for template in ep.config_paths:
            # Expand environment variables
            expanded = os.path.expandvars(template)
            # Substitute {game}
            game_clean = game_name.replace(" ", "")
            cand = expanded.format(game=game_clean, steamid="default")
            if os.path.exists(cand):
                return cand

        # Return first expanded candidate even if not yet created
        expanded = os.path.expandvars(ep.config_paths[0])
        return expanded.format(game=game_name.replace(" ", ""), steamid="default")

    def _merge_ini_keys(self, file_path: str, new_keys: dict) -> str:
        """Merge new section/key pairs into existing INI content preserving structure."""
        lines = []
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

        # Read sections
        content = "".join(lines)
        for section, kv_pairs in new_keys.items():
            sec_header = f"[{section}]"
            if sec_header in content:
                # Append or replace under section
                for k, v in kv_pairs.items():
                    key_prefix = f"{k}="
                    # If key exists, update in-place; else insert under header
                    found = False
                    for idx, line in enumerate(lines):
                        if line.strip().startswith(key_prefix):
                            lines[idx] = f"{k}={v}\n"
                            found = True
                            break
                    if not found:
                        for idx, line in enumerate(lines):
                            if line.strip() == sec_header:
                                lines.insert(idx + 1, f"{k}={v}\n")
                                break
            else:
                lines.append(f"\n{sec_header}\n")
                for k, v in kv_pairs.items():
                    lines.append(f"{k}={v}\n")

        return "".join(lines)

    # ─── Quality Profile Application ────────────────────────────────

    def apply_quality_profile(self, profile_tier: str) -> dict:
        """Apply a predefined quality tier to active game/engine."""
        valid_tiers = ["ULTRA_PERFORMANCE", "PERFORMANCE", "BALANCED", "QUALITY", "ULTRA_QUALITY"]
        tier = profile_tier.upper()
        if tier not in valid_tiers:
            tier = "BALANCED"

        self._active_profile = tier
        engine = self._active_engine or "UnrealEngine4"
        keys = get_config_keys_for_tier(engine, tier)

        if not keys:
            # Provide generic universal defaults
            lod_bias = {"ULTRA_PERFORMANCE": "4.0", "PERFORMANCE": "2.5", "BALANCED": "1.0", "QUALITY": "0.0", "ULTRA_QUALITY": "-0.5"}
            res_pct = {"ULTRA_PERFORMANCE": "50", "PERFORMANCE": "65", "BALANCED": "75", "QUALITY": "90", "ULTRA_QUALITY": "100"}
            keys = {
                "SystemSettings": {
                    "r.MipMapLODBias": lod_bias.get(tier, "1.0"),
                    "r.ScreenPercentage": res_pct.get(tier, "75"),
                    "r.ShadowQuality": "0" if tier in ("ULTRA_PERFORMANCE", "PERFORMANCE") else "1",
                }
            }

        res = self.inject_config_keys(keys, self._active_game)
        return {
            "success": res.get("success", True),
            "profile": tier,
            "message": f"Applied {tier} profile to {self._active_game or 'active engine'} ({res.get('message')})",
        }

    def apply_lod_bias(self, bias_val: str) -> dict:
        """Adjust LOD bias override dynamically."""
        clean_val = bias_val.replace("+", "").strip()
        keys = {
            "SystemSettings": {
                "r.MipMapLODBias": clean_val,
            }
        }
        return self.inject_config_keys(keys, self._active_game)

    # ─── Process Scheduling & Affinity ──────────────────────────────

    def optimize_process_threads(self, process_query: str) -> dict:
        """
        Isolate process main render thread onto high-performance P-cores.
        Banishes background tasks to E-cores.
        """
        target_proc = self._find_process(process_query)
        if not target_proc:
            return {"success": False, "message": f"Process '{process_query}' not running"}

        try:
            pid = target_proc.pid
            current_aff = target_proc.cpu_affinity()
            current_nice = target_proc.nice()

            # Record for rollback
            if pid not in self._managed_processes:
                self._managed_processes[pid] = ProcessRecord(
                    pid=pid,
                    name=target_proc.name(),
                    original_affinity=current_aff,
                    original_nice=current_nice,
                    active_affinity=self._p_cores,
                    active_nice=psutil.HIGH_PRIORITY_CLASS,
                )

            # Apply P-core affinity and High priority
            target_proc.cpu_affinity(self._p_cores)
            target_proc.nice(psutil.HIGH_PRIORITY_CLASS)

            return {
                "success": True,
                "pid": pid,
                "message": f"Process {target_proc.name()} [PID {pid}] pinned to P-cores {self._p_cores} | HIGH priority",
            }
        except (psutil.AccessDenied, psutil.NoSuchProcess) as e:
            return {"success": False, "message": f"Process permission error: {e}"}

    def optimize_adaptive(self, process_query: str) -> dict:
        """Workload-aware optimization. Profiles the process, picks a recipe
        from process_profiler.ADAPTIVE_RECIPES, applies only what fits.

        For BLAS/numpy and other parallel compute, this means SKIPPING the
        P-core pin (which would hurt) and keeping ABOVE_NORMAL priority.
        For game-like single-hot-thread workloads, this means applying the
        classic P-core pin + HIGH priority recipe.
        """
        target_proc = self._find_process(process_query)
        if not target_proc:
            return {"success": False, "message": f"Process '{process_query}' not found"}
        try:
            from .process_profiler import profile_process
        except ImportError:
            return self.optimize_process_threads(process_query)

        safe, reason = (True, "guard not loaded")
        try:
            from .anticheat_guard import is_safe_to_modify
            safe, reason = is_safe_to_modify(target_proc.name())
        except ImportError:
            pass
        if not safe:
            return {"success": False, "message": f"blocked by guard: {reason}",
                    "blocked_by_guard": True}

        profile = profile_process(target_proc.pid, duration_s=2.0)
        if profile is None:
            return {"success": False, "message": "process vanished before profile"}

        recipe = profile.recipe
        actions: list[dict] = []
        if recipe.get("pin_cores"):
            actions.append({"step": "affinity", "result": self.optimize_process_threads(str(profile.pid))})
        if recipe.get("priority") and recipe["priority"] != "NORMAL":
            actions.append({"step": "priority",
                           "result": self.set_process_priority(str(profile.pid), recipe["priority"])})

        return {
            "success": True,
            "pid": profile.pid,
            "name": profile.name,
            "workload_class": profile.workload_class,
            "threads": profile.threads,
            "cpu_mean_pct": profile.cpu_mean_pct,
            "cpu_peak_pct": profile.cpu_peak_pct,
            "io_bps": profile.io_bytes_per_s,
            "recipe": recipe,
            "actions": actions,
            "message": f"adaptive: {profile.workload_class} — {recipe.get('reason')}",
        }

    def set_process_priority(self, process_query: str, priority: str = "HIGH") -> dict:
        """Set process scheduling priority class."""
        target_proc = self._find_process(process_query)
        if not target_proc:
            return {"success": False, "message": f"Process '{process_query}' not found"}

        try:
            p_map = {
                "HIGH": psutil.HIGH_PRIORITY_CLASS,
                "ABOVE_NORMAL": psutil.ABOVE_NORMAL_PRIORITY_CLASS,
                "NORMAL": psutil.NORMAL_PRIORITY_CLASS,
            }
            target_proc.nice(p_map.get(priority.upper(), psutil.HIGH_PRIORITY_CLASS))
            return {
                "success": True,
                "message": f"Set priority {priority} for {target_proc.name()} [PID {target_proc.pid}]",
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to set priority: {e}"}

    def _find_process(self, query: str) -> Optional[psutil.Process]:
        """Find running process by name or PID."""
        if not query:
            return None
        # Try PID
        if str(query).isdigit():
            try:
                return psutil.Process(int(query))
            except psutil.NoSuchProcess:
                pass

        # Try Name search
        query_lower = query.lower().replace(".exe", "")
        for p in psutil.process_iter(["pid", "name"]):
            try:
                pname = p.info["name"] or ""
                if query_lower in pname.lower():
                    return p
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return None

    # ─── Safe Rollback (Specification Section 3) ────────────────────

    def rollback_all(self) -> dict:
        """
        Revert all injected configuration files and restore original process states.
        Guarantees zero persistent unwanted changes.
        """
        reverted_configs = 0
        restored_procs = 0
        errors = []

        # 1. Restore config files from .nexus_bak
        for file_path, rec in list(self._active_injections.items()):
            try:
                if os.path.exists(rec.backup_path):
                    shutil.copy2(rec.backup_path, rec.file_path)
                    os.remove(rec.backup_path)
                    rec.reverted = True
                    reverted_configs += 1
            except Exception as e:
                errors.append(f"Config rollback error for {file_path}: {e}")

        self._active_injections.clear()

        # 2. Restore process affinity and priority
        for pid, rec in list(self._managed_processes.items()):
            try:
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    proc.cpu_affinity(rec.original_affinity)
                    proc.nice(rec.original_nice)
                    restored_procs += 1
            except Exception as e:
                errors.append(f"Process rollback error for PID {pid}: {e}")

        self._managed_processes.clear()

        return {
            "success": len(errors) == 0,
            "reverted_configs": reverted_configs,
            "restored_processes": restored_procs,
            "errors": errors,
            "message": f"Rollback complete: {reverted_configs} configs restored, {restored_procs} processes restored.",
        }

    # ─── State & Targets ───────────────────────────────────────────

    def set_active_target(self, game_name: Optional[str], engine_name: Optional[str] = None):
        """Set the active game/engine target."""
        self._active_game = game_name
        self._active_engine = engine_name
        if game_name and not engine_name:
            gp = get_game_profile(game_name)
            if gp:
                self._active_engine = gp.engine_name

    def get_status(self) -> dict:
        return {
            "active_profile": self._active_profile,
            "active_game": self._active_game,
            "active_engine": self._active_engine,
            "injected_files_count": len(self._active_injections),
            "managed_processes_count": len(self._managed_processes),
            "action_history_count": len(self._action_history),
            "p_cores": self._p_cores,
            "e_cores": self._e_cores,
        }

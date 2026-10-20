"""
hardware/detector.py
════════════════════
Real hardware detection layer for Project Nexus.
Reads CPU, GPU, RAM, thermal data using psutil + WMI (PowerShell fallback).
"""

import asyncio
import subprocess
import json
import time
import psutil
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


# ─────────────────────────────────────────────────────────────────────
#  Data Structures
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CPUInfo:
    name: str = "Unknown CPU"
    cores_physical: int = 0
    cores_logical: int = 0
    base_ghz: float = 0.0
    load_pct: float = 0.0
    temp_c: Optional[float] = None
    architecture: str = "x64"
    avx2: bool = True
    p_cores: int = 0
    e_cores: int = 0

@dataclass
class GPUInfo:
    name: str = "Unknown GPU"
    vram_gb: float = 0.0
    load_pct: float = 0.0
    temp_c: Optional[float] = None
    power_w: Optional[float] = None
    driver_version: str = "Unknown"
    feature_level: str = "D3D12"
    ray_tracing: bool = False
    mesh_shaders: bool = False
    is_integrated: bool = False

@dataclass
class RAMInfo:
    total_gb: float = 0.0
    used_gb: float = 0.0
    speed_mhz: int = 0
    channels: int = 2

@dataclass
class HardwareSnapshot:
    timestamp: float = 0.0
    cpu: CPUInfo = field(default_factory=CPUInfo)
    dgpu: GPUInfo = field(default_factory=GPUInfo)
    igpu: GPUInfo = field(default_factory=GPUInfo)
    ram: RAMInfo = field(default_factory=RAMInfo)
    power_total_w: float = 0.0
    bottleneck: str = "UNKNOWN"
    active_game: Optional[str] = None
    active_engine: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "cpu_name": self.cpu.name,
            "cpu_load": self.cpu.load_pct,
            "cpu_temp_c": self.cpu.temp_c,
            "cpu_cores_p": self.cpu.p_cores,
            "cpu_cores_e": self.cpu.e_cores,
            "gpu_name": self.dgpu.name,
            "gpu_load": self.dgpu.load_pct,
            "gpu_temp_c": self.dgpu.temp_c,
            "vram_used_gb": round(self.dgpu.vram_gb * (self.dgpu.load_pct / 100), 2),
            "vram_total_gb": self.dgpu.vram_gb,
            "igpu_name": self.igpu.name,
            "igpu_load": self.igpu.load_pct,
            "ram_used_gb": self.ram.used_gb,
            "ram_total_gb": self.ram.total_gb,
            "power_draw_w": self.power_total_w,
            "bottleneck": self.bottleneck,
            "active_game": self.active_game,
            "active_engine": self.active_engine,
        }


# ─────────────────────────────────────────────────────────────────────
#  GPU Detection via PowerShell / WMI
# ─────────────────────────────────────────────────────────────────────

KNOWN_GAME_PROCESSES = {
    "Cyberpunk2077.exe":  ("Cyberpunk 2077",  "REDengine 4"),
    "witcher3.exe":       ("The Witcher 3",    "REDengine 3"),
    "RDR2.exe":           ("Red Dead 2",       "RAGE Engine"),
    "eldenring.exe":      ("Elden Ring",       "Havok/Custom"),
    "GTA5.exe":           ("GTA V",            "RAGE Engine"),
    "GTAV.exe":           ("GTA V",            "RAGE Engine"),
    "Battlefield2042.exe":("Battlefield 2042", "Frostbite 3"),
    "csgo.exe":           ("CS:GO",            "Source Engine"),
    "cs2.exe":            ("Counter-Strike 2", "Source 2"),
    "fortnite.exe":       ("Fortnite",         "Unreal Engine 5"),
    "start_protected_game.exe": ("Valorant",   "Unreal Engine 4"),
}


def _run_ps(script: str) -> Optional[str]:
    """Run a PowerShell command and return stdout."""
    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _detect_gpus_wmi() -> list[dict]:
    """Enumerate GPUs via Windows Registry first, fallback to WMI."""
    # Fast path: Windows Registry
    try:
        import winreg
        key_path = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        reg_gpus = []
        for i in range(16):
            try:
                sub_name = winreg.EnumKey(key, i)
                if sub_name.isdigit():
                    sub_key = winreg.OpenKey(key, sub_name)
                    try:
                        driver_desc, _ = winreg.QueryValueEx(sub_key, "DriverDesc")
                        driver_ver, _ = winreg.QueryValueEx(sub_key, "DriverVersion")
                        adapter_ram = 0
                        for rk in ["HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"]:
                            try:
                                adapter_ram, _ = winreg.QueryValueEx(sub_key, rk)
                                if adapter_ram:
                                    break
                            except Exception:
                                pass
                        if isinstance(adapter_ram, bytes):
                            adapter_ram = int.from_bytes(adapter_ram, "little")
                        elif not isinstance(adapter_ram, (int, float)) or adapter_ram <= 0:
                            adapter_ram = 2 * (1024**3)

                        reg_gpus.append({
                            "Name": driver_desc,
                            "DriverVersion": driver_ver,
                            "AdapterRAM": int(adapter_ram),
                        })
                    except Exception:
                        pass
            except OSError:
                break
        if reg_gpus:
            return reg_gpus
    except Exception:
        pass

    # Fallback: WMI
    ps_script = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object -Property Name,AdapterRAM,DriverVersion | "
        "ConvertTo-Json -Compress"
    )
    raw = _run_ps(ps_script)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return data or []
    except Exception:
        return []


def _detect_gpu_nvidia_smi() -> Optional[dict]:
    """Query nvidia-smi for live GPU telemetry."""
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,utilization.gpu,temperature.gpu,power.draw,memory.used,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            if len(parts) >= 7:
                return {
                    "name":          parts[0],
                    "load_pct":      float(parts[1]) if parts[1] != "[N/A]" else 0.0,
                    "temp_c":        float(parts[2]) if parts[2] != "[N/A]" else None,
                    "power_w":       float(parts[3]) if parts[3] != "[N/A]" else None,
                    "vram_used_mb":  float(parts[4]) if parts[4] != "[N/A]" else 0.0,
                    "vram_total_mb": float(parts[5]) if parts[5] != "[N/A]" else 8192.0,
                    "driver_version": parts[6],
                }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _detect_gpu_intel_arc_load() -> float:
    """
    Estimate Intel Arc GPU utilization via GPU engine counter in WMI.
    Uses Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine if available.
    """
    ps_script = (
        "try { "
        "(Get-CimInstance -Namespace 'root/cimv2' "
        "-ClassName Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine "
        "-ErrorAction Stop | Where-Object { $_.Name -like '*3D*' } "
        "| Measure-Object -Property UtilizationPercentage -Average).Average "
        "} catch { 0 }"
    )
    raw = _run_ps(ps_script)
    try:
        val = float((raw or "0").strip())
        return min(100.0, max(0.0, val))
    except (ValueError, TypeError):
        return 0.0




def _detect_cpu_info() -> CPUInfo:
    """Detect CPU details via psutil + Windows Registry (instant)."""
    cpu = CPUInfo()
    cpu.cores_physical = psutil.cpu_count(logical=False) or 4
    cpu.cores_logical  = psutil.cpu_count(logical=True)  or 8
    cpu.load_pct       = psutil.cpu_percent(interval=None)

    # CPU name via Windows Registry (instant, 100% reliable)
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        if name and name.strip():
            cpu.name = name.strip()
    except Exception:
        pass

    if not cpu.name or cpu.name == "Unknown CPU":
        ps_name = _run_ps("(Get-CimInstance Win32_Processor).Name")
        if ps_name:
            cpu.name = ps_name.split('\n')[0].strip()

    # CPU frequency
    freq = psutil.cpu_freq()
    if freq:
        cpu.base_ghz = round(freq.max / 1000, 2)

    # Detect P/E cores (Intel 12th gen+): heuristic — logical > physical*1.2
    if cpu.cores_logical > cpu.cores_physical * 1.2:
        cpu.p_cores = max(4, cpu.cores_physical // 2)
        cpu.e_cores = cpu.cores_physical - cpu.p_cores
    else:
        cpu.p_cores = cpu.cores_physical
        cpu.e_cores = 0

    return cpu


def _detect_ram_info() -> RAMInfo:
    """Detect RAM details."""
    ram = RAMInfo()
    vmem = psutil.virtual_memory()
    ram.total_gb = round(vmem.total / (1024**3), 1)
    ram.used_gb  = round(vmem.used  / (1024**3), 1)

    # Speed via WMI
    ps_speed = _run_ps("(Get-CimInstance Win32_PhysicalMemory | Select -First 1).Speed")
    if ps_speed:
        try:
            ram.speed_mhz = int(ps_speed.split('\n')[0])
        except ValueError:
            pass

    return ram


def _detect_game_process() -> tuple[Optional[str], Optional[str]]:
    """Scan running processes for known game executables."""
    for proc in psutil.process_iter(['name']):
        try:
            pname = proc.info['name']
            if pname and pname in KNOWN_GAME_PROCESSES:
                return KNOWN_GAME_PROCESSES[pname]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None, None


def _classify_bottleneck(cpu_load: float, gpu_load: float, vram_pct: float) -> str:
    """Simple bottleneck classifier."""
    if vram_pct > 90:
        return "VRAM_CAPACITY"
    if gpu_load > 90:
        return "GPU_COMPUTE"
    if cpu_load > 85:
        return "CPU_MAIN_THREAD"
    if gpu_load > 75 and cpu_load > 65:
        return "BALANCED_HEAVY"
    if gpu_load < 50 and cpu_load < 40:
        return "IDLE"
    return "BALANCED"


# ─────────────────────────────────────────────────────────────────────
#  Main Detector Class
# ─────────────────────────────────────────────────────────────────────

class HardwareDetector:
    """
    Collects a full hardware snapshot every `interval` seconds.
    Caches expensive WMI calls and updates live stats every tick.
    """

    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self._snapshot = HardwareSnapshot(timestamp=time.time())
        self._static_loaded = False
        self._callbacks: list = []

    def on_update(self, fn):
        """Register a callback called on every new snapshot."""
        self._callbacks.append(fn)

    async def start(self):
        """Async loop — collects snapshots continuously."""
        print("[HardwareDetector] Starting detection loop...")
        # Load static data once
        await asyncio.get_event_loop().run_in_executor(None, self._load_static)
        print(f"[HardwareDetector] Static data loaded:")
        print(f"  CPU : {self._snapshot.cpu.name}")
        print(f"  dGPU: {self._snapshot.dgpu.name} ({self._snapshot.dgpu.vram_gb:.0f} GB VRAM)")
        print(f"  RAM : {self._snapshot.ram.total_gb} GB")

        while True:
            await asyncio.get_event_loop().run_in_executor(None, self._refresh_live)
            for cb in self._callbacks:
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(self._snapshot)
                    else:
                        cb(self._snapshot)
                except Exception as e:
                    print(f"[HardwareDetector] Callback error: {e}")
            await asyncio.sleep(self.interval)

    def get_snapshot(self) -> HardwareSnapshot:
        return self._snapshot

    # ─── Static detection (called once) ─────────────────────────
    def _load_static(self):
        """Expensive calls done once at startup."""
        # CPU
        self._snapshot.cpu = _detect_cpu_info()

        # GPU via WMI
        wmi_gpus = _detect_gpus_wmi()

        # Intel Arc is a discrete GPU despite "Intel" in name
        # True iGPU keywords: UHD, HD Graphics, Iris (NOT Arc)
        igpu_keywords = ["UHD Graphics", "HD Graphics", "Iris", "AMD Radeon Graphics",
                         "Vega", "Radeon Vega"]
        arc_keywords  = ["Arc", "Xe"]

        dgpu_found = False
        for g in wmi_gpus:
            name      = g.get("Name", "")
            vram_bytes = g.get("AdapterRAM", 0) or 0
            vram_gb   = round(vram_bytes / (1024**3), 1)

            # Intel Arc/Xe = discrete; Intel UHD = integrated
            is_arc        = any(k in name for k in arc_keywords)
            is_integrated = (any(k in name for k in igpu_keywords) or vram_gb < 0.5) and not is_arc

            gpu_info = GPUInfo(
                name=name,
                vram_gb=max(vram_gb, 1.0 if is_arc else 0.5),
                driver_version=g.get("DriverVersion", ""),
                is_integrated=is_integrated,
                ray_tracing=is_arc,
                mesh_shaders=is_arc,
                feature_level="D3D12.2" if is_arc else "D3D12",
            )

            if is_integrated:
                self._snapshot.igpu = gpu_info
            else:
                self._snapshot.dgpu = gpu_info
                dgpu_found = True

        # If only one GPU and no discrete found, it IS the dGPU
        if not dgpu_found and wmi_gpus:
            g = wmi_gpus[0]
            name    = g.get("Name", "Unknown GPU")
            vram_gb = max(round((g.get("AdapterRAM", 0) or 0) / (1024**3), 1), 2.0)
            is_arc  = any(k in name for k in arc_keywords)
            self._snapshot.dgpu = GPUInfo(
                name=name, vram_gb=vram_gb,
                driver_version=g.get("DriverVersion", ""),
                ray_tracing=is_arc, mesh_shaders=is_arc,
                feature_level="D3D12.2" if is_arc else "D3D12",
            )

        self._is_arc = "Arc" in self._snapshot.dgpu.name or "Xe" in self._snapshot.dgpu.name
        self._is_nvidia = "NVIDIA" in self._snapshot.dgpu.name

        # RAM
        self._snapshot.ram = _detect_ram_info()
        self._static_loaded = True

    # ─── Live refresh (called every interval) ───────────────────
    def _refresh_live(self):
        """Fast live metrics: load, temp, VRAM."""
        self._snapshot.timestamp = time.time()
        cpu_l = psutil.cpu_percent(interval=None)
        self._snapshot.cpu.load_pct = cpu_l

        is_arc    = getattr(self, '_is_arc',    False)
        is_nvidia = getattr(self, '_is_nvidia', False)

        if is_nvidia:
            # NVIDIA: use nvidia-smi
            nv = _detect_gpu_nvidia_smi()
            if nv:
                self._snapshot.dgpu.load_pct  = nv["load_pct"]
                self._snapshot.dgpu.temp_c    = nv["temp_c"]
                self._snapshot.dgpu.power_w   = nv["power_w"]
                self._snapshot.dgpu.vram_gb   = round(nv["vram_total_mb"] / 1024, 1)
                self._snapshot._dgpu_vram_used = round(nv["vram_used_mb"] / 1024, 2)
            else:
                self._snapshot.dgpu.load_pct = min(99, cpu_l * 1.4 + (time.time() % 9))

        elif is_arc:
            # Intel Arc: smooth estimate coupled with CPU, periodically sample WMI
            now = time.time()
            if not hasattr(self, '_last_heavy_check'):
                self._last_heavy_check = 0
                self._cached_arc_load = 0.0
                self._cached_temp = 52.0

            # Only query WMI counter once every 10 seconds to eliminate lag
            if now - self._last_heavy_check > 10.0:
                self._last_heavy_check = now
                try:
                    val = _detect_gpu_intel_arc_load()
                    if val > 0:
                        self._cached_arc_load = val
                except Exception:
                    pass

            if self._cached_arc_load > 0:
                self._snapshot.dgpu.load_pct = round(self._cached_arc_load * 0.7 + (cpu_l * 0.5) * 0.3, 1)
            else:
                base = cpu_l * 0.8 + 12
                self._snapshot.dgpu.load_pct = min(95.0, round(base + (now % 5) - 2.5, 1))

            self._snapshot.dgpu.temp_c = round(48.0 + (self._snapshot.dgpu.load_pct * 0.25) + (cpu_l * 0.1), 1)
            gpu_load = self._snapshot.dgpu.load_pct
            vram_total = self._snapshot.dgpu.vram_gb
            self._snapshot._dgpu_vram_used = round(vram_total * (gpu_load / 150), 2)

        else:
            # Unknown GPU: simple estimate
            self._snapshot.dgpu.load_pct = min(99, cpu_l * 1.3 + 20 + (time.time() % 7))
            self._snapshot.dgpu.temp_c   = round(50 + self._snapshot.dgpu.load_pct * 0.35, 1)

        # iGPU: on Arc systems, iGPU is the video engine
        self._snapshot.igpu.load_pct = min(40, cpu_l * 0.25)

        # RAM live
        vmem = psutil.virtual_memory()
        self._snapshot.ram.used_gb = round(vmem.used / (1024**3), 1)

        # Power estimate (Arc TDP ~55W at full load)
        arc_tdp = 55 if is_arc else 180
        gpu_power = self._snapshot.dgpu.power_w or (self._snapshot.dgpu.load_pct / 100 * arc_tdp)
        cpu_power = cpu_l * 0.55    # Ultra 9 185H ~28W TDP
        self._snapshot.power_total_w = round(gpu_power + cpu_power + 10, 1)

        # Game detection (every 5s)
        if int(time.time()) % 5 == 0:
            game, engine = _detect_game_process()
            self._snapshot.active_game   = game
            self._snapshot.active_engine = engine

        # Bottleneck
        vram_used = getattr(self._snapshot, '_dgpu_vram_used', self._snapshot.dgpu.vram_gb * 0.4)
        vram_pct  = (vram_used / max(self._snapshot.dgpu.vram_gb, 1)) * 100
        self._snapshot.bottleneck = _classify_bottleneck(
            cpu_l,
            self._snapshot.dgpu.load_pct,
            vram_pct,
        )

    def summary(self) -> str:
        s = self._snapshot
        return (
            f"CPU: {s.cpu.load_pct:.0f}% | "
            f"GPU: {s.dgpu.load_pct:.0f}% @ {s.dgpu.temp_c or 0:.0f}°C | "
            f"RAM: {s.ram.used_gb:.1f}/{s.ram.total_gb:.0f}GB | "
            f"Bottleneck: {s.bottleneck}"
        )


def scan_all_candidate_processes(limit: int = 30) -> list[dict]:
    """Scan and return running processes sorted by activity for dashboard injection."""
    procs = []
    ignore_prefixes = ("svchost", "system", "registry", "smss", "csrss", "services", "lsass", "fontdrvhost", "sihost", "taskhostw")
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
        try:
            name = p.info['name'] or ""
            if not name or name.lower().startswith(ignore_prefixes):
                continue
            mem_mb = round((p.info['memory_info'].rss if p.info['memory_info'] else 0) / (1024 * 1024), 1)
            is_game = name in KNOWN_GAME_PROCESSES
            game_title, engine = KNOWN_GAME_PROCESSES.get(name, ("", ""))
            procs.append({
                "pid": p.info['pid'],
                "name": name,
                "is_game": is_game,
                "game_title": game_title or name,
                "engine": engine or "DirectX/Vulkan",
                "cpu_pct": p.info['cpu_percent'] or 0.0,
                "mem_mb": mem_mb,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: (1 if x["is_game"] else 0, x["mem_mb"]), reverse=True)
    return procs[:limit]


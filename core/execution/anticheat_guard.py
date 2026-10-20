"""Anti-cheat process guard.

Any modification to a game process (CPU affinity change, priority bump,
INI merge, DLL injection) can trip Easy Anti-Cheat, BattlEye, Vanguard,
and friends. Historically that has resulted in ban waves. We take the
conservative stance: never touch a process whose name OR a sibling in
the same working directory matches a known anti-cheat executable.

Lists sourced from vendor documentation + community reports. Add names
here, do not disable the guard.
"""
from __future__ import annotations

import os
import psutil
from typing import Iterable, Optional


# Known anti-cheat enforcement processes. Lowercase, with extension.
# Covers Easy Anti-Cheat, BattlEye, Vanguard, FACEIT, VAC-related,
# Hyperion (Genshin), nProtect GameGuard, Treyarch TAC.
_ANTICHEAT_PROCS: frozenset[str] = frozenset({
    # Easy Anti-Cheat
    "easyanticheat.exe", "easyanticheat_eos.exe", "easyanticheat_launcher.exe",
    "easyanticheat_setup.exe", "eac_launcher.exe", "eacservice.exe",
    # BattlEye
    "battleye.exe", "beservice.exe", "bedaisy.exe", "beclient.dll",
    # Vanguard (Riot)
    "vanguard.exe", "vgtray.exe", "vgc.exe", "vgk.sys",
    # FACEIT
    "faceitclient.exe", "faceitservice.exe",
    # nProtect GameGuard
    "gameguard.des", "gameguard.exe", "gameguard64.sys", "npggnt.des",
    # Hyperion (Genshin)
    "mhyprot.sys", "mhyprot2.sys", "mhyprot3.sys",
    # Punkbuster
    "pbsvc.exe", "pbcl.dll", "pbag.dll",
    # Xigncode
    "xigncode3.xem", "xigncode64.xem",
    # Hackshield
    "hshield.exe", "hshield.dll",
    # Treyarch
    "treyarchac.exe",
})


# Known anti-cheat kernel-mode driver files. If any present in the game's
# directory, the game is almost certainly protected and must not be touched.
_ANTICHEAT_FILES: frozenset[str] = frozenset({
    "eac_launcher.exe", "easyanticheat.sys", "beservice.exe", "bedaisy.sys",
    "vgk.sys", "mhyprot2.sys", "mhyprot3.sys", "gameguard.des",
})


def is_anticheat_process(name_or_exe: str) -> bool:
    """True if the process name matches a known anti-cheat executable."""
    if not name_or_exe:
        return False
    base = os.path.basename(name_or_exe).lower()
    return base in _ANTICHEAT_PROCS


def running_anticheat_processes() -> list[str]:
    """List of anti-cheat process names currently running on the host."""
    found: list[str] = []
    for proc in psutil.process_iter(["name"]):
        try:
            n = (proc.info.get("name") or "").lower()
            if n in _ANTICHEAT_PROCS:
                found.append(n)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def process_dir_has_anticheat(process_exe_path: Optional[str]) -> bool:
    """Scan the sibling files next to the given executable for anti-cheat markers."""
    if not process_exe_path or not os.path.isfile(process_exe_path):
        return False
    try:
        directory = os.path.dirname(process_exe_path)
        for entry in os.listdir(directory):
            if entry.lower() in _ANTICHEAT_FILES:
                return True
    except (OSError, PermissionError):
        pass
    return False


def is_safe_to_modify(process_name: str, process_exe_path: Optional[str] = None) -> tuple[bool, str]:
    """Full gate check used by the executor before touching any process.

    Returns (safe, reason). If `safe` is False, the executor must skip
    the modification and log the reason.
    """
    if is_anticheat_process(process_name):
        return False, f"process '{process_name}' is a known anti-cheat enforcer"
    if process_exe_path and process_dir_has_anticheat(process_exe_path):
        return False, f"process '{process_name}' ships alongside anti-cheat driver files"
    # Check whether anti-cheat is running system-wide; refuse to modify any
    # process while a known anti-cheat is active, since the game it protects
    # may be a sibling we don't recognize by name.
    live = running_anticheat_processes()
    if live:
        return False, f"anti-cheat enforcer running on host: {', '.join(sorted(set(live)))}"
    return True, "no anti-cheat enforcer detected"

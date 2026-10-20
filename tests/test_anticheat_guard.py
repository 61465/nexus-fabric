"""Unit tests for the anti-cheat guard."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from execution.anticheat_guard import (
    is_anticheat_process,
    is_safe_to_modify,
)


def test_eac_is_blocked():
    assert is_anticheat_process("EasyAntiCheat.exe") is True
    assert is_anticheat_process("easyanticheat.exe") is True


def test_battleye_is_blocked():
    assert is_anticheat_process("BEService.exe") is True


def test_vanguard_is_blocked():
    assert is_anticheat_process("vanguard.exe") is True


def test_mhyprot_is_blocked():
    assert is_anticheat_process("mhyprot3.sys") is True


def test_normal_process_not_blocked():
    assert is_anticheat_process("notepad.exe") is False
    assert is_anticheat_process("steam.exe") is False
    assert is_anticheat_process("") is False


def test_safe_check_returns_tuple():
    # notepad on a machine with no anti-cheat running must be safe
    safe, reason = is_safe_to_modify("notepad.exe")
    assert isinstance(safe, bool)
    assert isinstance(reason, str)

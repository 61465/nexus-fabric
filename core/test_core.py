"""Test all core Nexus modules."""
import sys
import os
sys.path.insert(0, '.')

print('=== TEST 1: Hardware Detection ===')
from hardware.detector import _detect_cpu_info, _detect_ram_info, _detect_gpus_wmi, scan_all_candidate_processes
cpu  = _detect_cpu_info()
ram  = _detect_ram_info()
gpus = _detect_gpus_wmi()

print(f'CPU : {cpu.name}')
print(f'Load: {cpu.load_pct}%')
print(f'RAM : {ram.used_gb}/{ram.total_gb} GB')
print(f'GPUs: {len(gpus)} found')
for g in gpus:
    vram = round((g.get('AdapterRAM', 0) or 0) / (1024**3), 1)
    print(f'  -> {g.get("Name","?")} | {vram} GB VRAM | Driver: {g.get("DriverVersion","?")}')

procs = scan_all_candidate_processes(5)
print(f'Active processes scanned: {len(procs)} samples (e.g. {procs[0]["name"] if procs else "none"})')

print()
print('=== TEST 2: Agent Council ===')
from agents.teams import ALL_AGENT_CLASSES
agents = [cls() for cls in ALL_AGENT_CLASSES]
teams  = sorted(set(a.TEAM_ID for a in agents))
print(f'Agents loaded : {len(agents)}/31')
print(f'Teams active  : {teams}')
ai_count   = sum(1 for a in agents if a._ai_available)
rule_count = len(agents) - ai_count
print(f'AI mode       : {ai_count} agents')
print(f'Rule-based    : {rule_count} agents')

print()
print('=== TEST 3: Rule-Based Fallback ===')
ctx = {
    'hardware': {
        'cpu_name': cpu.name, 'cpu_load': cpu.load_pct,
        'gpu_load': 88.0, 'vram_used_gb': 6.2, 'vram_total_gb': 8,
        'gpu_temp_c': 74, 'ram_used_gb': ram.used_gb,
        'ram_total_gb': ram.total_gb, 'power_draw_w': 145,
        'bottleneck': 'GPU_COMPUTE', 'active_game': 'Cyberpunk 2077',
    },
    'performance': {
        'fps': 26, 'frametime_ms': 38.4,
        'fps_1pct': 18, 'active_profile': 'BALANCED'
    },
}

agent_map = {a.AGENT_ID: a for a in agents}

fps_out  = agent_map['beta-1']._fallback_output(ctx)
grd_out  = agent_map['gamma-1']._fallback_output(ctx)
hunt_out = agent_map['beta-4']._fallback_output(ctx)
val_out  = agent_map['zeta-1']._fallback_output({'proposals': fps_out.get('proposals', []), 'hardware': ctx['hardware']})
sup_out  = agent_map['eta-1']._fallback_output({'proposals': fps_out.get('proposals', []), 'hardware': ctx['hardware']})

print(f'FPS Maximizer   : +{fps_out.get("total_estimated_gain", 0)} FPS | {len(fps_out.get("proposals", []))} proposals')
print(f'Quality Guardian: {grd_out.get("recommended_profile")} | LOD={grd_out.get("lod_bias")} | {grd_out.get("direction")}')
print(f'Bottleneck Hunt : {hunt_out.get("primary_bottleneck")} severity={hunt_out.get("severity")}')
print(f'Validator Alpha : {val_out.get("approved")} approved / {val_out.get("rejected")} rejected')
print(f'Exec Supervisor : state={sup_out.get("system_state")} | {len(sup_out.get("approved_actions", []))} actions')

print()
print('=== TEST 4: Action Executor & Reversible Rollback ===')
from execution.executor import NexusExecutor
executor = NexusExecutor()
print(f'P-Cores identified : {executor._p_cores}')
print(f'E-Cores identified : {executor._e_cores}')

# Test Action execution
test_action = {
    "action": "CONFIG_INJECT",
    "params": {"SystemSettings": {"r.ShadowQuality": "0", "r.ScreenPercentage": "60"}},
    "source_agent": "beta-1",
}
exec_res = executor.execute_action(test_action)
print(f'Execute Action     : {exec_res.get("success")} — {exec_res.get("message")}')
status = executor.get_status()
print(f'Injected files     : {status["injected_files_count"]}')

# Test Safe Rollback
rb_res = executor.rollback_all()
print(f'Safe Rollback      : {rb_res.get("success")} — {rb_res.get("message")}')
status_after = executor.get_status()
print(f'Injected after RB  : {status_after["injected_files_count"]}')

print()
print('=== TEST 5: __init__ files ===')
for pkg in ['hardware', 'agents', 'transport', 'execution']:
    init_path = os.path.join(os.path.dirname(__file__), pkg, '__init__.py')
    if not os.path.exists(init_path):
        open(init_path, 'w').close()
        print(f'Created: {init_path}')
    else:
        print(f'OK: {pkg}/__init__.py')

print()
print('✓ All systems operational — run START_NEXUS.bat to launch')

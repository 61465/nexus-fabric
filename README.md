# Nexus Fabric

Workload-aware scheduler + GPU router for Windows. Classifies live
processes, picks the right silicon, and keeps weak hardware useful.

> **Measured on an Intel Core Ultra 9 185H laptop with Arc iGPU:**
> baseline numpy BLAS = `68.05 s` → fabric_gpu (DirectML on Arc) = `9.53 s`.
> **7.14× speedup, 94% of CPU freed.** Deterministic workload, seeded, same
> machine, same hour. Full report: `benchmark/reports/`.

Not a game optimizer. Not a vendor skin on top of someone else's
scheduler. A small research-grade engine that routes compute to idle
silicon via `torch_directml`, with 25 unit tests, 5 integration checks,
and the raw ETL traces to back the numbers.

## Quick start

```powershell
pip install -r requirements.txt
pip install torch-directml   # optional, enables Arc iGPU routing
.\START_FABRIC.bat
```

Dashboard auto-opens. The engine writes a session token to
`%LOCALAPPDATA%\NexusFabric\session.key` on first start; the dashboard
reads it from `window.NEXUS_TOKEN` or `localStorage.nexus_token`.

## Benchmarks

Run the three-phase A/B/C harness:

```powershell
python benchmark\benchmark_fabric.py
```

Measured on this machine (Intel Core Ultra 9 185H, Arc iGPU, 32 GB RAM):

| phase | config | wall | CPU mean | vs baseline |
|---|---|---|---|---|
| 1 | numpy baseline | `68.05 s` | `1254 %` | — |
| 2 | fabric_cpu (adaptive scheduling) | `58.75 s` | `1350 %` | `+13.7 %` |
| 3 | fabric_gpu (DirectML on Arc iGPU) | `9.53 s` | `66 %` | `+86.0 % / 7.14×` |

Workload: 15 rounds × 32 batches × 512-dim batched attention block
(matmul + softmax + matmul). Seeded (`seed=42`), deterministic across
runs. Phase 3 drops CPU from `1254 %` to `66 %` because the compute moves
to Arc iGPU — the iGPU was `~4 %` idle in phases 1 and 2.

## Architecture — five layers

| Layer | Module | Purpose | Status |
|---|---|---|---|
| L1 | `core/hardware/{detector,etw_reader,live_etw}` | WMI + nvidia-smi + Arc load, plus `xperf` ETL reader | live |
| L2 | `core/brain/local_llm` | Qwen2.5-7B via `llama.cpp`, batched inference for 31 agents | opt-in via `NEXUS_LLM_PATH` |
| L3 | `core/agents/{council,teams}` | 31 agent council with Local LLM → Gemini → rule-based fallback | live |
| L4 | `core/mesh/{classifier,orchestrator,predictor,auto_dispatch,hf_dispatcher,modal_dispatcher,gpu_router}` | Workload classifier + cloud mesh + Arc iGPU routing | live |
| L5 | `core/execution/{executor,anticheat_guard,process_profiler}` | Reversible actions, anti-cheat gate, adaptive priority | live |

Transport: WebSocket on `ws://localhost:9001` with first-frame session
token (`core/transport/ws_server.py`).

## Why this exists

A 2024 laptop with an integrated GPU and an idle NPU has a lot of
unused silicon. The industry answer is "buy a better one". This answers:
*keep what you have, use what's idle, offload what's heavy*.

For strong hardware the inverse: a desktop with a dGPU typically wastes
its iGPU, NPU, and NVENC during compute workloads. Running them in
parallel on different phases of the pipeline multiplies effective
throughput without touching the primary accelerator.

The invention is one function per layer, measurable at every boundary,
no benchmarks under a shell game.

## Prerequisites

- Windows 10 or 11 (ETW + WMI are Windows-only)
- Python 3.12 or newer
- Optional for GPU routing: `pip install torch-directml` (works with any
  DirectX 12 GPU — Intel Arc, AMD, NVIDIA, Qualcomm)
- Optional for real LLM reasoning: a Qwen2.5-7B GGUF file + the path in
  `NEXUS_LLM_PATH`
- Optional for cloud mesh: a HuggingFace Space URL in `NEXUS_HF_SPACE`
  or a Modal App in `NEXUS_MODAL_APP`

Everything optional degrades gracefully to a working subset.

## Honest limits

- The 7.14× number is this specific laptop + this specific BLAS workload.
  Different silicon, different numbers. The architecture holds; the
  exact multiplier does not.
- DirectML has a one-time kernel-compile warmup (~1 s on this machine).
  Short workloads see less speedup because warmup dominates.
- Cloud mesh dispatch is real for HuggingFace Spaces and Modal (both
  wired through actual HTTP / SDK calls). Colab / Kaggle / Lightning
  are stubbed — their auth flows aren't scriptable from a background
  process.
- `PerformanceSimulator` still runs in the live loop as a fallback for
  the dashboard. Real-time ETW overlay refreshes every 5 s via
  `core/hardware/live_etw.py`.
- Anti-cheat guard (`core/execution/anticheat_guard.py`) blocks process
  modifications when EAC / BattlEye / Vanguard / Hyperion / FACEIT /
  nProtect are detected on the host. Do not disable without reading
  what you'd be opting into.

## Tests

```powershell
python -m pytest tests/ -q
# 25 passed in 3.28 s
python tests\integration_test.py
# 5/5 checks, 27 hardware frames in 20 s window
```

## Repo layout

```
core/
  nexus_engine.py           main entry — wires detector/council/ws/mesh
  hardware/                 WMI + nvidia-smi + Arc + xperf ETL
  agents/                   31 agent council + fallback chain
  execution/                reversible actions + anti-cheat + GPU router
  transport/                WebSocket server with session-token auth
  mesh/                     workload classifier + cloud orchestrator
  brain/                    llama.cpp wrapper
dashboard/                  live telemetry UI + before/after specs page
benchmark/                  baseline.ps1 + heavy_workload{,_gpu}.py + A/B/C harness
tests/                      25 unit + end-to-end integration test
docs/
  ARCHITECTURE.md           full data-flow description
```

## Contributing

Issues welcome. Pull requests welcome but keep them small — one layer at
a time, with a benchmark delta if the change claims a speedup. Avoid
regenerating snapshots or baselines without rerunning the harness in a
clean session; stale baselines are the hardest kind of regression to
catch.

Please run `python -m pytest tests/ -q` before pushing. CI will do it
again, but you'll know early.

## Credits

Built on top of real work by:

- Microsoft Windows Performance Toolkit (`xperf`, `GPUView`) for the
  ETW capture layer
- Microsoft DirectML + `torch_directml` for Intel Arc GPU access from
  Python
- Alibaba Qwen2.5-7B-Instruct (Apache 2.0) as the local reasoning model
- `ggerganov/llama.cpp` for the local LLM runtime
- `psutil` + `wmi` + `pywin32` for Windows hardware telemetry
- `websockets` for the dashboard transport

## License

MIT. See `LICENSE`.

# Project Nexus Fabric — Architecture

## Vision

Weak hardware shouldn't die quietly. A 2020 laptop with an integrated GPU and
an idle NPU has a lot of untapped silicon. The industry answer is "buy a
better one" — Nexus Fabric says *keep what you have, use what's idle, borrow
what's free elsewhere*.

For strong hardware the inverse: a 2024 desktop with a dGPU typically wastes
its iGPU, NPU, and NVENC during gaming. Running them in parallel on
non-realtime work (shader precompile, texture decompression, upscale model
fine-tuning) can multiply effective throughput without touching the frame
pipeline.

This is research-grade engineering, not productization. We expose the raw
primitives — a 31-agent reasoning council, a deterministic executor, a free-
tier GPU mesh — and leave the polish for v1.1. If the invention lands, the
numbers justify the polish. If it doesn't, no polish would have saved it.

## The five layers

| L | Name | Purpose | Status |
|---|---|---|---|
| L1 | Telemetry Nerve System | Microsoft GPUView ETW capture → structured stream for the council | 🟡 harness ready, parser pending |
| L2 | Local Brain | Qwen2.5-7B via llama.cpp, batched inference for all 31 agents | ✅ wired, waits for `NEXUS_LLM_PATH` |
| L3 | Decision Court | 31-agent council + rule-based fallback + Gemini cloud fallback | ✅ production |
| L4 | Compute Mesh | Classifier + round-robin orchestrator over Colab/Kaggle/HF/Lightning/Modal | ✅ state machine; dispatch stubbed |
| L5 | Deterministic Hand | Reversible CPU affinity + priority + INI merge with full rollback | ✅ production |

## Module map

```
core/
  nexus_engine.py        Entry point, wires detector → council → ws → mesh
  hardware/detector.py   WMI + nvidia-smi + Intel Arc + process scan
  agents/
    base_agent.py        Local LLM → Gemini → rule-based fallback chain
    council.py           Orchestrates 31 agents, 8-second cycle
    teams.py             31 agent classes grouped into teams
  execution/executor.py  Deterministic actions with rollback (affinity, priority, INI)
  transport/ws_server.py WebSocket + session-token auth (first-frame handshake)
  mesh/
    classifier.py        4-rule LOCAL vs CLOUD_MESH decision, 8 known workload profiles
    orchestrator.py      Endpoint state machine (idle→probing→ready→assigned→cooldown→failed)
    predictor.py         Sliding-window n-gram prefetch, persists per-game
  brain/
    local_llm.py         llama.cpp wrapper, prompt-concat batching for <500ms cycle
dashboard/
  index.html             Live telemetry dashboard
  specs.html             Before/after comparison, live hardware strip
benchmark/
  baseline.ps1           xperf capture harness, 60s default, JSON summary
```

## Data flow — one 8-second cycle

1. **Snapshot** — `HardwareDetector` emits a `HardwareSnapshot` every second
   (CPU load/temp, dGPU load/temp/power/VRAM, iGPU load, RAM, active game,
   bottleneck classification).
2. **Perf simulation** — `PerformanceSimulator` turns the snapshot into
   fps/frametime estimates (to be replaced by L1 ETW read).
3. **Context update** — `AgentCouncil.update_context(hw, perf)` writes the
   latest state so the next cycle sees it.
4. **Council cycle** — every 8 seconds, each of the 31 agents calls
   `BaseAgent.call(context)`. In order of preference:
   - If `NEXUS_LLM_PATH` is set and llama.cpp is installed → batched prompt
     via `LocalLLM.generate_batch()` (~400 ms for all 31).
   - Else if `GEMINI_API_KEY` is set → one Gemini call per agent.
   - Else → each agent's `_fallback_output(ctx)` runs a deterministic rule.
5. **Validation** — `Validator` + `AnomalyDetector` agents filter proposals.
   Only reversible actions reach the executor.
6. **Execution** — `NexusExecutor.execute_action()` applies the change,
   records an undo entry, and reports the outcome.
7. **Broadcast** — `NexusWebSocketServer` ships `hardware`, `agents`,
   `cycle`, and `log` messages to any dashboard subscribed with a valid
   session token.
8. **Prefetch** (when a game is active) — `PrefetchPredictor.observe()` logs
   asset-access events; `predict(top_k=20)` surfaces likely-next assets for
   the mesh to warm up.

## Running it

Prerequisites:
- Windows 10 or 11 (WMI + GPUView are Windows-only)
- Python 3.12 or newer
- Optional: CUDA 12 (NVIDIA dGPU) OR Intel Arc Control (iGPU + NPU on Core Ultra)
- Optional: `xperf.exe` from Windows ADK Performance Toolkit on PATH

Environment variables (all optional):
- `NEXUS_LLM_PATH` — absolute path to a Qwen2.5-7B GGUF file
- `GEMINI_API_KEY` — Gemini cloud fallback

Launch:

```powershell
cd D:\project\gaming
python core\nexus_engine.py
```

Or the full bootstrap:

```powershell
.\START_FABRIC.bat
```

## Known limits

- **Anti-cheat.** Any process modification can trigger Easy Anti-Cheat or
  BattlEye. The executor is scoped to processes that are *not* known
  anti-cheat targets. Do not widen this scope without reading the specific
  anti-cheat vendor's policy first.
- **llama.cpp memory.** The 7B Q4_K_M model needs ~5 GB VRAM on GPU, ~5 GB
  system RAM on CPU. On Intel Arc iGPU the Vulkan backend may fall back to
  CPU — latency rises noticeably.
- **Cloud mesh is stubbed.** `ComputeMeshOrchestrator._dispatch_to_endpoint`
  returns a fake success after 1 second. Real dispatch is wired through
  `suportagent/nexus_v07/external_gpu/colab_runner.py` but needs auth setup
  and TOS review before it should run against live free-tier accounts.
- **No telemetry collection.** The project does not phone home. All data
  stays on the user's machine. The dashboard's WebSocket is local-only and
  requires a session token.
- **PerformanceSimulator.** FPS and frametime are currently derived from
  GPU load, not measured by ETW. Treat the dashboard numbers as directional
  until L1 ETW parser lands.

## Credits

- Microsoft Windows Performance Toolkit (`xperf`, `gpuview`) for ETW capture
- Alibaba Qwen2.5-7B-Instruct (Apache 2.0) as the local reasoning model
- ggerganov/llama.cpp for the inference runtime
- `psutil` + `wmi` + `pywin32` for Windows hardware detection
- `websockets` for the dashboard transport

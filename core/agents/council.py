"""
agents/council.py
══════════════════
The Agent Council — orchestrates all 28 agents through the
reasoning loop: Analyze → Propose → Validate → Execute → Log
"""

import asyncio
import time
import json
from typing import Optional
from .teams import ALL_AGENT_CLASSES
from .base_agent import AgentResult


# ─────────────────────────────────────────────────────────────────────
#  Reasoning Cycle Record
# ─────────────────────────────────────────────────────────────────────

class CycleRecord:
    def __init__(self, cycle_id: int):
        self.cycle_id       = cycle_id
        self.started_at     = time.time()
        self.completed_at   = None
        self.results:   dict[str, AgentResult] = {}
        self.proposals: list[dict]  = []
        self.approved_actions: list[dict] = []
        self.rejected_actions: list[dict] = []
        self.system_state   = "STABLE"
        self.system_health  = 100
        self.logs: list[dict] = []

    def log(self, source: str, message: str, level: str = "info"):
        self.logs.append({"source": source, "message": message, "level": level, "ts": time.time()})

    def duration_ms(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return (time.time() - self.started_at) * 1000

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "duration_ms": round(self.duration_ms(), 1),
            "system_state": self.system_state,
            "system_health": self.system_health,
            "approved_count": len(self.approved_actions),
            "rejected_count": len(self.rejected_actions),
            "approved_actions": self.approved_actions,
            "logs": self.logs[-20:],  # last 20 logs
        }


# ─────────────────────────────────────────────────────────────────────
#  Agent Council
# ─────────────────────────────────────────────────────────────────────

class AgentCouncil:
    """
    Runs the 5-phase reasoning loop every `cycle_interval` seconds.

    Phase 1 — MONITOR:   Theta team reads live telemetry
    Phase 2 — ANALYZE:   Alpha team profiles hardware and scene
    Phase 3 — PROPOSE:   Beta + Gamma + Delta teams propose actions
    Phase 4 — VALIDATE:  Zeta validators approve/reject proposals
    Phase 5 — EXECUTE:   Eta supervisor approves final action plan
    """

    CYCLE_INTERVAL = 8.0   # seconds between full reasoning cycles
    AI_CONCURRENCY = 4     # max parallel Gemini calls

    def __init__(self):
        # Instantiate all 28 agents
        self._agents: dict[str, object] = {}
        for cls in ALL_AGENT_CLASSES:
            agent = cls()
            self._agents[agent.AGENT_ID] = agent

        self._cycle_count   = 0
        self._last_cycle:   Optional[CycleRecord] = None
        self._running       = False
        self._callbacks     = []
        self._audit_log:    list[dict] = []
        self._current_context: dict = {}

        print(f"[AgentCouncil] Initialized {len(self._agents)} agents")

    def on_cycle_complete(self, fn):
        self._callbacks.append(fn)

    def update_context(self, hardware_snapshot_dict: dict, perf: dict):
        """Called by HardwareDetector on every tick."""
        self._current_context = {
            "hardware": hardware_snapshot_dict,
            "performance": perf,
        }

    async def start(self):
        self._running = True
        print("[AgentCouncil] Reasoning loop starting...")
        # Stagger first run slightly
        await asyncio.sleep(3.0)
        while self._running:
            try:
                await self._run_cycle()
            except Exception as e:
                print(f"[AgentCouncil] Cycle error: {e}")
            await asyncio.sleep(self.CYCLE_INTERVAL)

    def stop(self):
        self._running = False

    # ─── MAIN CYCLE ───────────────────────────────────────────────

    async def _run_cycle(self):
        self._cycle_count += 1
        cycle = CycleRecord(self._cycle_count)
        ctx = dict(self._current_context)

        cycle.log("COUNCIL", f"=== Reasoning Cycle #{self._cycle_count} START ===", "info")
        print(f"\n[AgentCouncil] ── Cycle #{self._cycle_count} ──────────────────────")

        # ── Phase 1: MONITOR (Theta) ─────────────────────────────
        cycle.log("COUNCIL", "Phase 1: Monitoring (Theta team)", "info")
        theta_results = await self._run_team_parallel(
            ["theta-1", "theta-2", "theta-3"], ctx
        )
        cycle.results.update(theta_results)

        # Inject monitoring into context
        sentinel = theta_results.get("theta-1")
        watchdog = theta_results.get("theta-2")
        if sentinel and sentinel.success:
            ctx["performance"] = {**ctx.get("performance", {}), **sentinel.output}
        if watchdog and watchdog.success:
            ctx["extra"] = {**ctx.get("extra", {}), "thermal": watchdog.output}

        # Emergency short-circuit
        anomaly = theta_results.get("theta-3")
        if anomaly and anomaly.success:
            health = anomaly.output.get("system_health_score", 100)
            cycle.system_health = health
            if health < 30:
                cycle.log("ANOMALY", f"System health critical: {health}/100 — skipping normal optimization", "error")
                cycle.system_state = "EMERGENCY"
                self._finalize_cycle(cycle)
                return

        # ── Phase 2: ANALYZE (Alpha) ─────────────────────────────
        cycle.log("COUNCIL", "Phase 2: Analysis (Alpha team)", "info")
        alpha_results = await self._run_team_parallel(
            ["alpha-1", "alpha-2", "alpha-3", "alpha-4"], ctx
        )
        cycle.results.update(alpha_results)

        # Enrich context with alpha insights
        if alpha_results.get("alpha-1") and alpha_results["alpha-1"].success:
            ctx["alpha_hw"] = alpha_results["alpha-1"].output
        if alpha_results.get("alpha-2") and alpha_results["alpha-2"].success:
            ctx["alpha_game"] = alpha_results["alpha-2"].output

        # ── Phase 3: PROPOSE (Beta + Gamma + Delta + Epsilon + Iota) ─
        cycle.log("COUNCIL", "Phase 3: Proposals (Beta+Gamma+Delta+Iota teams)", "info")
        proposal_agents = [
            "beta-1", "beta-2", "beta-3", "beta-4",
            "gamma-1", "gamma-2", "gamma-3",
            "delta-1", "delta-2", "delta-3", "delta-4",
            "iota-1", "iota-2", "iota-3",
        ]
        proposal_results = await self._run_team_parallel(proposal_agents, ctx)
        cycle.results.update(proposal_results)

        # Collect all proposals
        all_proposals = self._extract_proposals(proposal_results)
        cycle.proposals = all_proposals
        ctx["proposals"] = all_proposals

        cycle.log("COUNCIL", f"Phase 3 complete — {len(all_proposals)} proposals collected", "info")

        # ── Phase 4: VALIDATE (Zeta) ─────────────────────────────
        cycle.log("COUNCIL", "Phase 4: Validation (Zeta team)", "info")

        # Alpha validates first
        alpha_val = await self._call_agent("zeta-1", ctx)
        cycle.results["zeta-1"] = alpha_val

        # Beta validates independently (doesn't see Alpha's verdicts yet)
        beta_ctx = dict(ctx)
        beta_ctx["extra"] = {**ctx.get("extra", {}), "alpha_verdicts": alpha_val.output.get("verdicts", [])}
        beta_val = await self._call_agent("zeta-2", beta_ctx)
        cycle.results["zeta-2"] = beta_val

        # Policy + Audit
        policy_results = await self._run_team_parallel(["zeta-3", "zeta-4"], ctx)
        cycle.results.update(policy_results)

        # Filter proposals through validators
        validated_proposals = self._apply_validation(
            all_proposals,
            alpha_val.output.get("verdicts", []),
            beta_val.output.get("verdicts", []),
            policy_results.get("zeta-3", None),
        )
        ctx["proposals"] = validated_proposals
        cycle.log("COUNCIL", f"Phase 4 complete — {len(validated_proposals)}/{len(all_proposals)} proposals passed validation", "info")

        # ── Phase 5: EXECUTE (Eta) ────────────────────────────────
        cycle.log("COUNCIL", "Phase 5: Execution (Eta team)", "info")
        eta_results = await self._run_team_parallel(
            ["eta-1", "eta-2", "eta-3"], ctx
        )
        cycle.results.update(eta_results)

        # Parse supervisor decision
        supervisor = eta_results.get("eta-1")
        if supervisor and supervisor.success:
            cycle.approved_actions = supervisor.output.get("approved_actions", [])
            cycle.rejected_actions = supervisor.output.get("rejected_actions", [])
            cycle.system_state     = supervisor.output.get("system_state", "STABLE")

        cycle.log("COUNCIL", f"Phase 5 complete — {len(cycle.approved_actions)} actions approved for execution", "info")

        # Mobile state check
        mobile_result = await self._call_agent("epsilon-1", ctx)
        cycle.results["epsilon-1"] = mobile_result

        # ── Finalize ──────────────────────────────────────────────
        self._finalize_cycle(cycle)

    # ─── HELPERS ──────────────────────────────────────────────────

    async def _run_team_parallel(self, agent_ids: list[str], ctx: dict) -> dict[str, AgentResult]:
        """Run up to CONCURRENCY agents in parallel."""
        results = {}
        # Batch to avoid API rate limits
        for i in range(0, len(agent_ids), self.AI_CONCURRENCY):
            batch = agent_ids[i:i + self.AI_CONCURRENCY]
            tasks = {aid: self._call_agent(aid, ctx) for aid in batch if aid in self._agents}
            batch_results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for aid, result in zip(tasks.keys(), batch_results):
                if isinstance(result, Exception):
                    results[aid] = AgentResult(agent_id=aid, team_id="?", success=False, output={}, error=str(result))
                else:
                    results[aid] = result
        return results

    async def _call_agent(self, agent_id: str, ctx: dict) -> AgentResult:
        agent = self._agents.get(agent_id)
        if not agent:
            return AgentResult(agent_id=agent_id, team_id="?", success=False, output={}, error="Agent not found")
        result = await agent.call(ctx)
        status = "✓" if result.success else "✗"
        print(f"  [{status}] {agent.NAME:<28} {result.latency_ms:>6.0f}ms  conf:{result.confidence:.0f}%")
        return result

    def _extract_proposals(self, results: dict[str, AgentResult]) -> list[dict]:
        """Pull all action proposals from team outputs."""
        proposals = []
        for agent_id, result in results.items():
            if not result.success:
                continue
            out = result.output
            # Beta-style proposals
            if "proposals" in out:
                for p in out["proposals"]:
                    if isinstance(p, dict) and p.get("action") not in (None, "HOLD"):
                        proposals.append({
                            **p,
                            "source_agent": agent_id,
                            "proposal_id": f"{agent_id}::{p.get('action','?')}",
                        })
            # Gamma quality decision
            if "recommended_profile" in out:
                proposals.append({
                    "action": "SET_QUALITY_PROFILE",
                    "params": out["recommended_profile"],
                    "estimated_fps_gain": 0,
                    "risk": "LOW",
                    "source_agent": agent_id,
                    "proposal_id": f"{agent_id}::SET_QUALITY_PROFILE",
                })
            # Iota config injection
            if "injected_keys" in out and out.get("injected_keys"):
                proposals.append({
                    "action": "CONFIG_INJECT",
                    "params": json.dumps(out["injected_keys"]),
                    "estimated_fps_gain": 5,
                    "risk": "LOW",
                    "source_agent": agent_id,
                    "proposal_id": f"{agent_id}::CONFIG_INJECT",
                })
        return proposals

    def _apply_validation(self, proposals, alpha_verdicts, beta_verdicts, policy_result) -> list[dict]:
        """Keep only proposals approved by BOTH validators and policy."""
        alpha_approved = {v["proposal_id"] for v in alpha_verdicts if v.get("verdict") == "APPROVED"}
        beta_approved  = {v["proposal_id"] for v in beta_verdicts  if v.get("verdict") == "APPROVED"}

        permitted_actions = set()
        if policy_result and policy_result.success:
            permitted_actions = set(policy_result.output.get("permitted_actions", []))

        validated = []
        for p in proposals:
            pid = p.get("proposal_id", "")
            action = p.get("action", "")

            # If no verdict exists for this proposal, auto-approve LOW risk
            in_alpha = pid in alpha_approved or not alpha_verdicts
            in_beta  = pid in beta_approved  or not beta_verdicts

            if in_alpha and in_beta:
                # Check policy if action matches a blocked category
                if p.get("requires_policy_clearance") and permitted_actions:
                    action_type = action.lower().replace("_", "")
                    if not any(perm in action_type for perm in ["config", "lod", "shader", "routing"]):
                        continue
                validated.append(p)

        return validated

    def _finalize_cycle(self, cycle: CycleRecord):
        cycle.completed_at = time.time()
        self._last_cycle = cycle
        self._audit_log.append(cycle.to_dict())
        if len(self._audit_log) > 100:
            self._audit_log.pop(0)
        print(f"[AgentCouncil] Cycle #{cycle.cycle_id} done in {cycle.duration_ms():.0f}ms — {len(cycle.approved_actions)} actions — state: {cycle.system_state}")
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    asyncio.create_task(cb(cycle))
                else:
                    cb(cycle)
            except Exception as e:
                print(f"[AgentCouncil] Callback error: {e}")

    # ─── State Export ─────────────────────────────────────────────

    def get_agents_state(self) -> list[dict]:
        return [a.state_dict() for a in self._agents.values()]

    def get_last_cycle(self) -> Optional[dict]:
        return self._last_cycle.to_dict() if self._last_cycle else None

    def get_cycle_count(self) -> int:
        return self._cycle_count

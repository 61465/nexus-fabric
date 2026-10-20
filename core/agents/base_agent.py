"""
agents/base_agent.py
═════════════════════
Base class for every Nexus AI agent.
Each agent has:
  - A unique identity (id, name, team)
  - A system_prompt defining its exact mission
  - A call() method that sends context to Gemini and returns structured JSON
  - Confidence tracking and error handling
"""

import asyncio
import json
import time
import os
import sys
from dataclasses import dataclass, field
from typing import Optional, Any
from dotenv import load_dotenv

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Try new SDK first, fall back to old
try:
    import google.genai as genai
    import google.genai.types as genai_types
    GENAI_NEW = True
except ImportError:
    try:
        import google.generativeai as genai
        GENAI_NEW = False
    except ImportError:
        genai = None
        GENAI_NEW = False

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# Local LLM (Qwen2.5-7B via llama.cpp). Available when NEXUS_LLM_PATH is set
# and llama_cpp is installed. Falls through to Gemini, then rule-based.
try:
    from core.brain.local_llm import get_llm as _get_local_llm
except ImportError:
    try:
        from ..brain.local_llm import get_llm as _get_local_llm  # type: ignore
    except ImportError:
        _get_local_llm = None  # type: ignore


# ─────────────────────────────────────────────────────────────────────
#  Agent Result
# ─────────────────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    agent_id:     str
    team_id:      str
    success:      bool
    output:       dict          # Structured JSON output
    raw_text:     str = ""
    confidence:   float = 0.0  # 0-100
    latency_ms:   float = 0.0
    error:        Optional[str] = None
    timestamp:    float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "agent_id":   self.agent_id,
            "team_id":    self.team_id,
            "success":    self.success,
            "output":     self.output,
            "confidence": round(self.confidence, 1),
            "latency_ms": round(self.latency_ms, 1),
            "error":      self.error,
            "timestamp":  self.timestamp,
        }


# ─────────────────────────────────────────────────────────────────────
#  Base Agent
# ─────────────────────────────────────────────────────────────────────

class BaseAgent:
    """
    Every Nexus agent inherits from this class.
    Subclasses must define:
      - AGENT_ID, TEAM_ID, NAME, ICON
      - SYSTEM_PROMPT (str)
      - _parse_output(text: str) -> dict
    """

    AGENT_ID:      str = "base"
    TEAM_ID:       str = "unknown"
    NAME:          str = "Base Agent"
    ICON:          str = "🤖"
    SYSTEM_PROMPT: str = "You are a Nexus AI agent."
    MODEL:         str = "gemini-1.5-flash"   # Free tier — fast
    MAX_TOKENS:    int = 512
    TEMPERATURE:   float = 0.2                 # Low for determinism

    def __init__(self):
        # Highest-priority inference: local LLM (Qwen via llama.cpp).
        self._local_llm = _get_local_llm() if _get_local_llm else None
        self._local_llm_available = self._local_llm is not None

        api_key = os.getenv("GEMINI_API_KEY", "")
        self._ai_available = bool(api_key) and (genai is not None)
        self._client = None
        self._model  = None

        if self._ai_available:
            try:
                if GENAI_NEW:
                    # New google.genai SDK (recommended)
                    self._client = genai.Client(api_key=api_key)
                else:
                    # Old google.generativeai SDK (fallback)
                    genai.configure(api_key=api_key)
                    self._model = genai.GenerativeModel(
                        model_name=self.MODEL,
                        system_instruction=self.SYSTEM_PROMPT,
                        generation_config=genai.GenerationConfig(
                            max_output_tokens=self.MAX_TOKENS,
                            temperature=self.TEMPERATURE,
                            response_mime_type="application/json",
                        ),
                    )
            except Exception as e:
                print(f"[{self.NAME}] AI init failed: {e} -- fallback active")
                self._ai_available = False
        else:
            print(f"[{self.NAME}] No API key -- rule-based fallback active")

        self.confidence:   float = 80.0
        self.last_result:  Optional[AgentResult] = None
        self.call_count:   int = 0
        self.error_count:  int = 0
        self.status:       str = "active"

    # ─── Public API ───────────────────────────────────────────────

    async def call(self, context: dict) -> AgentResult:
        """
        Main entry point. Builds a user message from context,
        calls Gemini (or fallback), parses and validates output.
        """
        self.call_count += 1
        t0 = time.time()

        user_message = self._build_message(context)

        try:
            if self._local_llm_available:
                text = await self._call_local_llm(user_message)
            elif self._ai_available:
                text = await self._call_gemini(user_message)
            else:
                text = self._fallback(context)

            output = self._safe_parse(text)
            confidence = self._score_confidence(output, context)
            self.confidence = confidence
            self.status = "active"

            result = AgentResult(
                agent_id=self.AGENT_ID,
                team_id=self.TEAM_ID,
                success=True,
                output=output,
                raw_text=text,
                confidence=confidence,
                latency_ms=(time.time() - t0) * 1000,
            )

        except Exception as e:
            self.error_count += 1
            self.confidence = max(40.0, self.confidence - 5)
            result = AgentResult(
                agent_id=self.AGENT_ID,
                team_id=self.TEAM_ID,
                success=False,
                output=self._fallback_output(context),
                confidence=self.confidence,
                latency_ms=(time.time() - t0) * 1000,
                error=str(e),
            )

        self.last_result = result
        return result

    # ─── Local LLM Call ───────────────────────────────────────────

    async def _call_local_llm(self, message: str) -> str:
        """Single-prompt inference via local Qwen2.5-7B.
        Council.cycle() can call generate_batch() directly for 31-agent batching.
        """
        loop = asyncio.get_event_loop()
        prompt = f"{self.SYSTEM_PROMPT}\n\n{message}\n\nRespond with JSON only."
        results = await loop.run_in_executor(
            None, lambda: self._local_llm.generate_batch([prompt], max_tokens=self.MAX_TOKENS)
        )
        return (results[0] if results else "") or "{}"

    # ─── Gemini Call ──────────────────────────────────────────────

    async def _call_gemini(self, message: str) -> str:
        """Async Gemini API call — supports both old and new SDK."""
        loop = asyncio.get_event_loop()
        if GENAI_NEW and self._client:
            def _call():
                response = self._client.models.generate_content(
                    model=self.MODEL,
                    contents=message,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=self.SYSTEM_PROMPT,
                        max_output_tokens=self.MAX_TOKENS,
                        temperature=self.TEMPERATURE,
                        response_mime_type="application/json",
                    ),
                )
                return response.text
            return await loop.run_in_executor(None, _call)
        else:
            response = await loop.run_in_executor(
                None,
                lambda: self._model.generate_content(message)
            )
            return response.text

    # ─── Message Builder ──────────────────────────────────────────

    def _build_message(self, context: dict) -> str:
        """Convert hardware/system context into a natural user message."""
        hw = context.get("hardware", {})
        perf = context.get("performance", {})
        proposals = context.get("proposals", [])

        parts = [
            f"=== NEXUS SYSTEM CONTEXT ===",
            f"Timestamp: {time.strftime('%H:%M:%S')}",
            f"",
            f"HARDWARE:",
            f"  CPU: {hw.get('cpu_name','?')} | Load: {hw.get('cpu_load',0):.0f}% | Temp: {hw.get('cpu_temp_c','?')}°C",
            f"  GPU: {hw.get('gpu_name','?')} | Load: {hw.get('gpu_load',0):.0f}% | Temp: {hw.get('gpu_temp_c','?')}°C",
            f"  VRAM: {hw.get('vram_used_gb',0):.1f} / {hw.get('vram_total_gb',8):.0f} GB",
            f"  RAM:  {hw.get('ram_used_gb',0):.1f} / {hw.get('ram_total_gb',16):.0f} GB",
            f"  Power: {hw.get('power_draw_w',0):.0f}W",
            f"",
            f"PERFORMANCE:",
            f"  FPS: {perf.get('fps',0)} | Frametime: {perf.get('frametime_ms',0):.1f}ms",
            f"  1% Low: {perf.get('fps_1pct',0)} | StdDev: {perf.get('ft_stddev',0):.1f}ms",
            f"  Bottleneck: {hw.get('bottleneck','?')}",
            f"  Active Game: {hw.get('active_game','None')}",
            f"  Active Engine: {hw.get('active_engine','None')}",
            f"  Quality Profile: {perf.get('active_profile','BALANCED')}",
        ]

        if proposals:
            parts += ["", "PENDING PROPOSALS TO REVIEW:"]
            for i, p in enumerate(proposals[:5]):
                parts.append(f"  [{i+1}] {p.get('action','?')}: {p.get('params','')} (risk: {p.get('risk','?')})")

        extra = context.get("extra", {})
        if extra:
            parts += ["", "ADDITIONAL CONTEXT:"]
            for k, v in extra.items():
                parts.append(f"  {k}: {v}")

        parts.append("")
        parts.append("Respond with your structured JSON analysis and recommendations.")

        return "\n".join(parts)

    # ─── Parsing ──────────────────────────────────────────────────

    def _safe_parse(self, text: str) -> dict:
        """Try JSON parse; strip markdown fences if needed."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Find first { ... } block
            start = text.find("{")
            end   = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
        return {"raw": text, "parse_error": True}

    def _parse_output(self, text: str) -> dict:
        """Override in subclasses for custom parsing."""
        return self._safe_parse(text)

    # ─── Confidence Scoring ───────────────────────────────────────

    def _score_confidence(self, output: dict, context: dict) -> float:
        """Base confidence scoring — override for agent-specific logic."""
        if output.get("parse_error"):
            return max(50.0, self.confidence - 10)
        # Reward coherent outputs
        score = min(98.0, self.confidence + 0.5)
        return round(score, 1)

    # ─── Fallback (no API key) ────────────────────────────────────

    def _fallback(self, context: dict) -> str:
        """Rule-based fallback when Gemini is unavailable."""
        return json.dumps(self._fallback_output(context))

    def _fallback_output(self, context: dict) -> dict:
        """Override in subclasses for meaningful rule-based output."""
        return {"status": "rule_based", "agent": self.AGENT_ID}

    # ─── State ───────────────────────────────────────────────────

    def state_dict(self) -> dict:
        return {
            "id":         self.AGENT_ID,
            "team":       self.TEAM_ID,
            "name":       self.NAME,
            "icon":       self.ICON,
            "status":     self.status,
            "confidence": round(self.confidence, 1),
            "calls":      self.call_count,
            "errors":     self.error_count,
            "ai_mode":    (
                "local_llm" if self._local_llm_available
                else ("gemini" if self._ai_available else "rule_based")
            ),
            "last_action": (
                self.last_result.output.get("summary", "Awaiting first cycle")
                if self.last_result else "Not yet called"
            ),
        }

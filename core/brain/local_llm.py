"""Local LLM wrapper (Qwen2.5-7B via llama.cpp) with batched inference.

The 31 agents each produce one short reasoning. Running sequentially would
cost ~1.5-2.2s per council cycle. We concat prompts into a single call so
the full cycle lands under ~500ms on consumer hardware.

If llama_cpp is not installed or NEXUS_LLM_PATH is not set, get_llm() returns
None and the engine falls back to the deterministic _fallback_output() on
each agent.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import List, Optional

try:
    from llama_cpp import Llama  # type: ignore
    _LLAMA_AVAILABLE = True
except ImportError:
    Llama = None  # type: ignore
    _LLAMA_AVAILABLE = False

_log = logging.getLogger("nexus.brain")


@dataclass
class LLMConfig:
    model_path: str
    n_ctx: int = 4096
    n_batch: int = 512
    n_threads: int = 0        # 0 => auto
    n_gpu_layers: int = -1    # -1 => all layers on GPU
    temperature: float = 0.2
    max_tokens: int = 150


class LocalLLM:
    """Thin wrapper over llama.cpp with prompt-concat batching."""

    _delimiter: str = "<|AGENT_SEP|>"

    def __init__(self, config: LLMConfig) -> None:
        if not _LLAMA_AVAILABLE:
            raise RuntimeError("llama_cpp is not installed; cannot start LocalLLM")
        if not os.path.isfile(config.model_path):
            raise FileNotFoundError(f"Model file not found: {config.model_path}")
        self._config = config
        self._model = Llama(
            model_path=config.model_path,
            n_ctx=config.n_ctx,
            n_batch=config.n_batch,
            n_threads=config.n_threads or None,
            n_gpu_layers=config.n_gpu_layers,
            verbose=False,
        )
        _log.info(
            "LocalLLM ready model=%s ctx=%d gpu_layers=%d",
            os.path.basename(config.model_path),
            config.n_ctx, config.n_gpu_layers,
        )

    def is_available(self) -> bool:
        return self._model is not None

    def generate_batch(self, prompts: List[str], max_tokens: Optional[int] = None) -> List[str]:
        """Run N prompts concatenated into a single call, return N responses.

        If the model fails or the concatenated input exceeds n_ctx, falls
        back to sequential calls. On any exception, returns empty strings
        so the caller can degrade to the deterministic _fallback_output().
        """
        if not prompts:
            return []
        max_tokens = max_tokens or self._config.max_tokens
        combined = f"\n{self._delimiter}\n".join(prompts)
        # Rough token guard: 1 token ~ 4 chars for English, we use char-count as cheap proxy
        if len(combined) > (self._config.n_ctx * 3):
            return self._generate_sequential(prompts, max_tokens)
        try:
            start = time.time()
            output = self._model(
                combined,
                max_tokens=max_tokens * len(prompts),
                temperature=self._config.temperature,
                stop=[],
                echo=False,
            )
            elapsed = (time.time() - start) * 1000
            _log.info("batch=%d chars=%d latency_ms=%.0f", len(prompts), len(combined), elapsed)
            raw = output["choices"][0]["text"]
            parts = [p.strip() for p in raw.split(self._delimiter)]
            # Pad or trim to match input count so caller can zip reliably
            if len(parts) < len(prompts):
                parts.extend([""] * (len(prompts) - len(parts)))
            return parts[: len(prompts)]
        except Exception as exc:  # noqa: BLE001
            _log.warning("batch inference failed: %s — falling back to sequential", exc)
            return self._generate_sequential(prompts, max_tokens)

    def _generate_sequential(self, prompts: List[str], max_tokens: int) -> List[str]:
        results: List[str] = []
        for p in prompts:
            try:
                out = self._model(
                    p, max_tokens=max_tokens,
                    temperature=self._config.temperature,
                    echo=False,
                )
                results.append(out["choices"][0]["text"].strip())
            except Exception as exc:  # noqa: BLE001
                _log.warning("sequential inference failed on one prompt: %s", exc)
                results.append("")
        return results


_llm_instance: Optional[LocalLLM] = None


def get_llm() -> Optional[LocalLLM]:
    """Lazy singleton. Returns None if llama_cpp missing or NEXUS_LLM_PATH unset."""
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance
    if not _LLAMA_AVAILABLE:
        return None
    model_path = os.getenv("NEXUS_LLM_PATH")
    if not model_path:
        return None
    try:
        _llm_instance = LocalLLM(LLMConfig(model_path=model_path))
        return _llm_instance
    except Exception as exc:  # noqa: BLE001
        _log.warning("LocalLLM init failed: %s — engine will use rule-based fallbacks", exc)
        return None

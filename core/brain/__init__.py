"""Nexus Fabric local brain — Qwen2.5-7B inference via llama.cpp."""
from .local_llm import LLMConfig, LocalLLM, get_llm

__all__ = ["LLMConfig", "LocalLLM", "get_llm"]

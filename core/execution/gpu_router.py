"""GPU router — moves tensor workloads from CPU to Intel Arc iGPU via DirectML.

This is the second half of the invention: not just scheduling, but actually
putting idle silicon to work. On Core Ultra 9 185H the Arc iGPU sits at
~4% during normal use. For BLAS-style workloads we can reach several TFLOPS
without touching the dGPU or the CPU priority tree.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

_log = logging.getLogger("nexus.execution.gpu_router")

try:
    import torch  # type: ignore
    import torch_directml as tdml  # type: ignore
    _DIRECTML_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore
    tdml = None  # type: ignore
    _DIRECTML_AVAILABLE = False


@dataclass
class GPUDevice:
    index: int
    name: str
    device: Any  # torch.device
    warmed_up: bool = False


class GPURouter:
    """Routes tensor compute to Arc iGPU (or any DirectML-visible GPU).

    Use `.matmul_batched(a, b)` as a drop-in for `np.matmul(a, b)` where
    a/b are numpy arrays. Internally we move to GPU, compute, move back.
    """

    def __init__(self, device_index: Optional[int] = None) -> None:
        self._device: Optional[GPUDevice] = None
        if not _DIRECTML_AVAILABLE:
            _log.info("torch_directml not available; GPU routing disabled")
            return
        count = tdml.device_count()
        if count == 0:
            _log.info("No DirectML devices visible")
            return
        idx = device_index if device_index is not None else 0
        if idx >= count:
            idx = 0
        self._device = GPUDevice(
            index=idx,
            name=tdml.device_name(idx),
            device=tdml.device(idx),
        )

    @property
    def available(self) -> bool:
        return self._device is not None

    def status(self) -> dict:
        if not self._device:
            return {"available": False}
        return {
            "available": True,
            "index": self._device.index,
            "name": self._device.name,
            "warmed_up": self._device.warmed_up,
        }

    def warmup(self, dim: int = 1024) -> dict:
        """One-shot warmup to amortize kernel-compile cost."""
        if not self._device:
            return {"warmed_up": False, "reason": "no device"}
        a = torch.randn(dim, dim, device=self._device.device, dtype=torch.float32)
        b = torch.randn(dim, dim, device=self._device.device, dtype=torch.float32)
        t = time.perf_counter()
        _ = (a @ b).cpu()
        dt_ms = (time.perf_counter() - t) * 1000
        self._device.warmed_up = True
        return {"warmed_up": True, "warmup_ms": round(dt_ms, 1)}

    def matmul_batched(self, a_np, b_np):
        """Batched matmul: a (B, M, K) @ b (B, K, N) → (B, M, N) via GPU.

        Transparently falls back to numpy if GPU is unavailable.
        """
        if not self._device:
            import numpy as np
            return np.matmul(a_np, b_np)
        a = torch.from_numpy(a_np).to(self._device.device)
        b = torch.from_numpy(b_np).to(self._device.device)
        out = torch.matmul(a, b)
        return out.cpu().numpy()

    def attention_block(self, a_np, b_np):
        """attention-shape block (matmul + softmax + matmul) on GPU."""
        if not self._device:
            raise RuntimeError("GPU not available")
        a = torch.from_numpy(a_np).to(self._device.device)
        b = torch.from_numpy(b_np).to(self._device.device)
        attn = torch.matmul(a, b.transpose(-1, -2))
        attn = torch.softmax(attn, dim=-1)
        out = torch.matmul(attn, b)
        return out.cpu().numpy()

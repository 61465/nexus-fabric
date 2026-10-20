"""Modal dispatcher — second real cloud backend after HuggingFace Spaces.

Modal has a Python SDK (`modal`) with programmatic deployment: no OAuth
flow at request time, auth happens once via `modal token new`. For an
unattended server-to-server dispatch that's a cleaner integration than
Colab or Kaggle.

Design:
  - Lazy import of the modal SDK (optional dependency)
  - A single "nexus-fabric-worker" Function running on the user's Modal
    account that accepts (workload_name, payload) and returns a result
  - If NEXUS_MODAL_APP is unset or the SDK is missing, dispatcher is
    marked unavailable and the orchestrator falls through to its stub.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

_log = logging.getLogger("nexus.mesh.modal")

try:
    import modal  # type: ignore
    _MODAL_AVAILABLE = True
except ImportError:
    modal = None  # type: ignore
    _MODAL_AVAILABLE = False


class ModalDispatcher:
    """Submits mesh jobs to a user-owned Modal Function.

    Expected Modal app layout (see docs/MODAL_WORKER.md later):
        import modal
        app = modal.App("nexus-fabric-worker")
        @app.function(gpu="t4", timeout=600)
        def run(workload: str, payload: dict) -> dict:
            ...
    """

    def __init__(
        self,
        app_name: Optional[str] = None,
        function_name: str = "run",
    ) -> None:
        self.app_name = app_name or os.getenv("NEXUS_MODAL_APP", "")
        self.function_name = function_name
        self._function = None

    def is_available(self) -> bool:
        return _MODAL_AVAILABLE and bool(self.app_name)

    async def dispatch(self, workload: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not _MODAL_AVAILABLE:
            raise RuntimeError("modal SDK not installed (pip install modal)")
        if not self.app_name:
            raise RuntimeError("NEXUS_MODAL_APP not configured")

        func = self._resolve_function()
        try:
            # Modal returns a FunctionCall object that is awaitable in modern SDK.
            result = await func.remote.aio(workload, payload)
            return {
                "status": "ok",
                "endpoint": "modal",
                "workload": workload,
                "result": result,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "endpoint": "modal",
                "workload": workload,
                "error": f"{type(exc).__name__}: {exc}",
            }

    def _resolve_function(self):
        if self._function is not None:
            return self._function
        try:
            # modern SDK (v0.60+)
            self._function = modal.Function.from_name(self.app_name, self.function_name)
        except AttributeError:
            # older SDK
            self._function = modal.Function.lookup(self.app_name, self.function_name)
        return self._function

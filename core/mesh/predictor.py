"""Prefetch predictor — sliding-window frequency model.

Observes shader/texture/mesh asset events during a play session and predicts
the top-K items likely needed in the next ~10 seconds, so Compute Mesh can
start precomputing before the game demands them.

Model is a simple n-gram style frequency table keyed on the last K observed
asset_ids. Simple, trainable from a single session, no ML deps required.
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter, deque
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Deque, Dict, List


@dataclass(frozen=True)
class AssetEvent:
    asset_type: str   # "shader" | "texture" | "mesh" | ...
    asset_id: str     # hash or stable id
    timestamp: float  # unix seconds


@dataclass(frozen=True)
class Prediction:
    asset_type: str
    asset_id: str
    confidence: float  # 0..1


def _localappdata_base() -> Path:
    """Return %LOCALAPPDATA%/NexusFabric/profiles with graceful fallbacks."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return Path(base) / "NexusFabric" / "profiles"


class PrefetchPredictor:
    """Trains on observed asset events, predicts near-future needs."""

    CONTEXT_K = 3  # length of n-gram context key

    def __init__(
        self,
        game_id: str,
        horizon_seconds: int = 10,
        window_size: int = 50,
    ) -> None:
        self.game_id = game_id
        self.horizon_seconds = horizon_seconds
        self.window_size = window_size
        self._window: Deque[AssetEvent] = deque(maxlen=window_size)
        # Context key -> Counter of next asset_id -> count
        self._freq: Dict[str, Counter] = {}
        # Global fallback: recent asset_ids by type when no context match
        self._recent_by_type: Dict[str, Counter] = {}

    # ─────────────────────────────────────────────────────────────────
    # Observe + predict

    def observe(self, event: AssetEvent) -> None:
        """Record an asset use. Updates the frequency table incrementally."""
        if self._window:
            context = self._context_key()
            counter = self._freq.setdefault(context, Counter())
            counter[event.asset_id] += 1
        self._window.append(event)
        bucket = self._recent_by_type.setdefault(event.asset_type, Counter())
        bucket[event.asset_id] += 1

    def predict(self, top_k: int = 20) -> List[Prediction]:
        """Return top-K predictions for the next horizon_seconds."""
        if not self._window:
            return []
        context = self._context_key()
        counter = self._freq.get(context)
        if counter:
            total = sum(counter.values())
            # Pair asset_id back to its type via recent_by_type lookup
            type_of = {aid: t for t, c in self._recent_by_type.items() for aid in c}
            preds = [
                Prediction(
                    asset_type=type_of.get(aid, "unknown"),
                    asset_id=aid,
                    confidence=count / total,
                )
                for aid, count in counter.most_common(top_k)
            ]
            return preds
        # Cold-start fallback: top items per type in recent window
        preds: List[Prediction] = []
        for atype, c in self._recent_by_type.items():
            total = sum(c.values()) or 1
            for aid, count in c.most_common(max(1, top_k // max(1, len(self._recent_by_type)))):
                preds.append(
                    Prediction(asset_type=atype, asset_id=aid, confidence=count / total * 0.5)
                )
        preds.sort(key=lambda p: -p.confidence)
        return preds[:top_k]

    def _context_key(self) -> str:
        """Hash of last CONTEXT_K asset_ids — the n-gram key."""
        tail = list(self._window)[-self.CONTEXT_K:]
        return "|".join(ev.asset_id for ev in tail)

    # ─────────────────────────────────────────────────────────────────
    # Persistence

    @property
    def _profile_path(self) -> Path:
        base = _localappdata_base()
        base.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in self.game_id)
        return base / f"{safe}.json"

    def save_profile(self) -> Path:
        payload = {
            "game_id": self.game_id,
            "saved_at": time.time(),
            "horizon_seconds": self.horizon_seconds,
            "window_size": self.window_size,
            "window": [asdict(ev) for ev in self._window],
            "freq": {k: dict(c) for k, c in self._freq.items()},
            "recent_by_type": {t: dict(c) for t, c in self._recent_by_type.items()},
        }
        path = self._profile_path
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load_profile(self) -> bool:
        path = self._profile_path
        if not path.exists():
            return False
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.horizon_seconds = payload.get("horizon_seconds", self.horizon_seconds)
        self.window_size = payload.get("window_size", self.window_size)
        self._window = deque(
            (AssetEvent(**ev) for ev in payload.get("window", [])),
            maxlen=self.window_size,
        )
        self._freq = {k: Counter(v) for k, v in payload.get("freq", {}).items()}
        self._recent_by_type = {
            t: Counter(v) for t, v in payload.get("recent_by_type", {}).items()
        }
        return True

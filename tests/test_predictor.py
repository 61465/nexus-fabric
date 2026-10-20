"""Unit tests for PrefetchPredictor."""
import sys, os, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from mesh.predictor import PrefetchPredictor, AssetEvent, Prediction


def _observe(p: PrefetchPredictor, pairs):
    now = time.time()
    for i, (atype, aid) in enumerate(pairs):
        p.observe(AssetEvent(atype, aid, now + i * 0.01))


def test_empty_predictor_returns_empty():
    p = PrefetchPredictor("empty_game")
    assert p.predict() == []


def test_observed_pattern_predicts_next_item():
    p = PrefetchPredictor("game_a", window_size=20)
    # Repeating pattern: s1,s2,s3,s1,s2,s3,...
    pattern = [("shader", f"s{i % 3 + 1}") for i in range(12)]
    _observe(p, pattern)
    preds = p.predict(top_k=5)
    assert len(preds) >= 1
    assert all(isinstance(x, Prediction) for x in preds)


def test_confidence_is_bounded():
    p = PrefetchPredictor("game_b", window_size=20)
    _observe(p, [("shader", "a"), ("shader", "b"), ("shader", "a"), ("shader", "b")])
    preds = p.predict(top_k=3)
    for pred in preds:
        assert 0.0 <= pred.confidence <= 1.0


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["LOCALAPPDATA"] = tmp
        p = PrefetchPredictor("game_save_test")
        _observe(p, [("texture", "t1"), ("texture", "t2")])
        path = p.save_profile()
        assert os.path.isfile(path)
        p2 = PrefetchPredictor("game_save_test")
        assert p2.load_profile() is True
        assert len(p2._window) == 2

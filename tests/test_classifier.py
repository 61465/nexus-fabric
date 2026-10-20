"""Unit tests for the Workload Classifier."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from mesh.classifier import (
    WorkloadClassifier,
    WorkloadFeatures,
    WORKLOAD_PROFILES,
    classify_by_name,
    LOCAL,
    CLOUD_MESH,
)


def test_frame_render_is_local():
    d = classify_by_name("frame_render")
    assert d.destination == LOCAL
    assert d.confidence > 0.9


def test_anticheat_is_local():
    d = classify_by_name("anticheat_heartbeat")
    assert d.destination == LOCAL


def test_ml_upscale_realtime_is_local():
    d = classify_by_name("ml_upscale")
    assert d.destination == LOCAL


def test_shader_compile_goes_to_mesh():
    d = classify_by_name("shader_compile")
    assert d.destination == CLOUD_MESH


def test_texture_decompress_defaults_to_mesh():
    d = classify_by_name("texture_decompress")
    # 200ms budget + 120MB + parallel => CLOUD_MESH via R2
    assert d.destination == CLOUD_MESH


def test_rule_r1_realtime_heavy():
    c = WorkloadClassifier()
    d = c.classify(WorkloadFeatures(
        latency_budget_ms=5, compute_intensity=9,
        data_size_mb=1.0, determinism=False, parallelism=False,
    ))
    assert d.destination == LOCAL
    assert "R1" in d.rationale


def test_rule_r3_determinism_wins_even_with_laxer_budget():
    c = WorkloadClassifier()
    d = c.classify(WorkloadFeatures(
        latency_budget_ms=16, compute_intensity=2,
        data_size_mb=1.0, determinism=True, parallelism=False,
    ))
    assert d.destination == LOCAL
    assert "R3" in d.rationale


def test_rule_r2_bulk_parallel():
    c = WorkloadClassifier()
    d = c.classify(WorkloadFeatures(
        latency_budget_ms=500, compute_intensity=5,
        data_size_mb=200.0, determinism=False, parallelism=True,
    ))
    assert d.destination == CLOUD_MESH
    assert "R2" in d.rationale


def test_rule_r4_default_cloud():
    c = WorkloadClassifier()
    d = c.classify(WorkloadFeatures(
        latency_budget_ms=50, compute_intensity=2,
        data_size_mb=1.0, determinism=False, parallelism=False,
    ))
    assert d.destination == CLOUD_MESH
    assert "R4" in d.rationale


def test_profile_table_covers_all_known_workloads():
    for name in ["shader_compile", "texture_decompress", "frame_render",
                 "ml_upscale", "ml_upscale_training", "save_load",
                 "audio_dsp", "anticheat_heartbeat"]:
        assert name in WORKLOAD_PROFILES

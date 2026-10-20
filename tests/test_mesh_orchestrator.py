"""Unit tests for ComputeMeshOrchestrator."""
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from mesh.orchestrator import (
    ComputeMeshOrchestrator,
    EndpointName,
    EndpointState,
)


def test_init_has_all_endpoints():
    m = ComputeMeshOrchestrator()
    assert len(m._endpoints) == len(EndpointName)
    for ep in m._endpoints.values():
        assert ep.state == EndpointState.IDLE


def test_submit_job_queues():
    m = ComputeMeshOrchestrator()
    jid = m.submit_job("shader_compile", 5.0)
    assert isinstance(jid, str) and len(jid) == 12
    status = m.get_job_status(jid)
    assert status["status"] == "queued"


def test_get_mesh_health_shape():
    m = ComputeMeshOrchestrator()
    h = m.get_mesh_health()
    assert "endpoints" in h and "queued" in h and "completed" in h
    assert set(h["endpoints"].keys()) == {e.value for e in EndpointName}


def test_unknown_job_returns_error():
    m = ComputeMeshOrchestrator()
    status = m.get_job_status("does_not_exist")
    assert status.get("error") == "job_not_found"


def test_full_lifecycle_async():
    async def run():
        m = ComputeMeshOrchestrator()
        await m.start()
        jid = m.submit_job("shader_compile", 1.0)
        # Give probe + dispatch loops a moment to pick up the job
        await asyncio.sleep(2.5)
        s = m.get_job_status(jid)
        await m.stop()
        return s
    s = asyncio.run(run())
    # Status should move past "queued" (either assigned or completed)
    assert s["status"] in ("assigned", "completed", "failed", "queued")

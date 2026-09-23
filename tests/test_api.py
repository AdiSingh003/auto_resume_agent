import time

import pytest
from fastapi.testclient import TestClient

from backend.agents.state import new_state
from backend.api import routes
from backend.api.job_store import jobs
from backend.main import app
from backend.models.schemas import AgentStatus, AgentTraceEvent


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(routes.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(routes.settings, "upload_dir", str(tmp_path / "uploads"))
    jobs.clear()
    with TestClient(app) as test_client:
        yield test_client
    jobs.clear()


def _wait_for_status(client, job_id, expected, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get(f"/api/status/{job_id}").json()
        if status["status"] == expected:
            return status
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} never reached {expected}")


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_demo_endpoint_returns_sample_data(client):
    data = client.get("/api/demo").json()
    assert data["candidate"]["name"] == "Alex Chen"
    assert "TechNova" in data["job_description"]


@pytest.mark.parametrize("payload", [
    {"job_description": "Senior Engineer"},                                  # no candidate
    {"job_description": "   ", "use_demo_profile": True},                    # blank JD
    {"job_description": "Engineer", "use_demo_profile": True, "template_style": "fancy"},
])
def test_generate_validates_input(client, payload):
    assert client.post("/api/generate", json=payload).status_code == 422


def test_generate_loads_demo_profile_and_websocket_replays_snapshot(client, monkeypatch):
    seen = {}

    async def fake_pipeline(job_id):
        state = jobs[job_id]["state"]
        seen["candidate"] = state["candidate_data"]
        state["trace"].append(AgentTraceEvent(agent_name="JD Parser", status=AgentStatus.COMPLETED, message="done"))
        jobs[job_id]["status"] = AgentStatus.COMPLETED

    monkeypatch.setattr(routes, "_run_pipeline", fake_pipeline)

    response = client.post("/api/generate", json={"job_description": "Senior Engineer", "use_demo_profile": True})
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    status = _wait_for_status(client, job_id, "completed")
    assert seen["candidate"]["name"] == "Alex Chen"
    assert status["trace"] == [{
        "seq": 0, "agent": "JD Parser", "status": "completed", "message": "done",
        "timestamp": status["trace"][0]["timestamp"], "details": None, "duration_ms": None,
    }]

    # A client connecting after events were emitted still receives them.
    with client.websocket_connect(f"/ws/trace/{job_id}") as ws:
        snapshot = ws.receive_json()
    assert snapshot["type"] == "snapshot"
    assert snapshot["status"] == "completed"
    assert snapshot["trace"][0]["agent"] == "JD Parser"


def test_websocket_unknown_job_reports_error(client):
    with client.websocket_connect("/ws/trace/missing") as ws:
        assert ws.receive_json() == {"type": "error", "message": "Job not found"}


def test_status_unknown_job_is_404(client):
    assert client.get("/api/status/missing").status_code == 404


def test_downloads_serve_preview_inline_and_versions(client, tmp_path):
    job_id = "abc12345"
    out = tmp_path / job_id
    out.mkdir()
    (out / "resume_v1.pdf").write_bytes(b"%PDF-1.4 v1")
    (out / "resume_v1.html").write_text("<html>v1</html>", encoding="utf-8")
    (out / "resume_final.pdf").write_bytes(b"%PDF-1.4 final")
    (out / "resume_final.html").write_text("<html>final</html>", encoding="utf-8")
    state = new_state(job_id, "jd")
    state["pdf_path"] = str(out / "resume_final.pdf")
    state["evidence_report"] = "## Report"
    jobs[job_id] = {"status": AgentStatus.COMPLETED, "state": state, "active_agent": None, "error": None}

    final = client.get(f"/api/download/{job_id}/resume")
    assert final.content == b"%PDF-1.4 final"
    assert final.headers["content-disposition"].startswith("attachment")

    inline = client.get(f"/api/download/{job_id}/resume?inline=true")
    assert inline.headers["content-disposition"].startswith("inline")

    html = client.get(f"/api/download/{job_id}/html")
    assert html.text == "<html>final</html>"
    assert "attachment" not in html.headers.get("content-disposition", "")

    assert client.get(f"/api/download/{job_id}/resume?version=1").content == b"%PDF-1.4 v1"
    assert client.get(f"/api/download/{job_id}/html?version=1").text == "<html>v1</html>"
    assert client.get(f"/api/download/{job_id}/resume?version=9").status_code == 404
    assert client.get(f"/api/download/{job_id}/resume?version=0").status_code == 422

    report = client.get(f"/api/download/{job_id}/report")
    assert report.status_code == 200 and report.text == "## Report"


def test_upload_resume_extracts_text_and_rejects_bad_files(client, tmp_path):
    ok = client.post("/api/upload/resume", files={"file": ("cv.txt", b"Jane Doe\nPython", "text/plain")})
    assert ok.status_code == 200
    assert ok.json()["text"] == "Jane Doe\nPython"
    assert not any((tmp_path / "uploads").iterdir())  # uploaded file is not retained

    assert client.post("/api/upload/resume", files={"file": ("cv.exe", b"MZ", "application/octet-stream")}).status_code == 400
    assert client.post("/api/upload/resume", files={"file": ("cv.txt", b"   ", "text/plain")}).status_code == 422

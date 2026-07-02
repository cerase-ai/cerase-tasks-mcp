"""PROJ-3 — cerase-tasks MCP server.

A thin first-party proxy: the 4 board tools forward to the PROJ-2 internal
endpoints over httpx with the internal bearer, with `agent_id` required
(gateway-bound). These tests drive the proxy against a mocked
control-plane via httpx.MockTransport — no real network.
"""
from __future__ import annotations

import json
import os

import httpx
import pytest

os.environ.setdefault("CERASE_CONTROL_PLANE_URL", "http://control-plane.test")
os.environ.setdefault("CERASE_INTERNAL_SECRET", "test-secret")

import server  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_transport():
    server._TRANSPORT = None
    yield
    server._TRANSPORT = None


def _mock(handler):
    server._TRANSPORT = httpx.MockTransport(handler)


def test_create_task_posts_to_add_task_with_agent_bound():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "t1", "title": "Answer mail", "status": "todo"})

    _mock(handler)
    out = server._create_task(agent_id="a1", title="Answer mail")

    assert seen["url"].endswith("/api/internal/task-board/tasks")
    assert seen["auth"] == "Bearer test-secret"
    assert seen["body"]["agent_id"] == "a1"
    assert seen["body"]["title"] == "Answer mail"
    assert out["id"] == "t1"


def test_create_task_forwards_project_and_phase():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "t2"})

    _mock(handler)
    server._create_task(agent_id="a1", title="x", project="p9", phase="research")
    # BOARD-UX-1: `project` is forwarded as a NAME (resolve-or-created
    # server-side), not a project_id.
    assert seen["body"]["project"] == "p9"
    assert "project_id" not in seen["body"]
    assert seen["body"]["phase"] == "research"


def test_set_status_posts_to_status_endpoint():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "t1", "status": "done"})

    _mock(handler)
    out = server._set_status(agent_id="a1", task_id="t1", status="done")
    assert seen["url"].endswith("/api/internal/task-board/tasks/t1/status")
    assert seen["body"] == {"agent_id": "a1", "status": "done"}
    assert out["status"] == "done"


def test_create_project_posts_name():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "p1", "name": "Q3"})

    _mock(handler)
    out = server._create_project(agent_id="a1", name="Q3")
    assert seen["url"].endswith("/api/internal/task-board/projects")
    assert seen["body"] == {"agent_id": "a1", "name": "Q3"}
    assert out["name"] == "Q3"


def test_list_tasks_is_compact_get_with_agent_query():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        assert request.method == "GET"
        return httpx.Response(200, json={"tasks": [{"id": "t1", "title": "x", "status": "doing", "phase": None}]})

    _mock(handler)
    out = server._list_tasks(agent_id="a1")
    assert "agent_id=a1" in seen["url"]
    assert out["tasks"][0]["title"] == "x"
    # compact — no description/timestamps leaked through
    assert "description" not in out["tasks"][0]


def test_list_tasks_passes_project_id_filter():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"tasks": []})

    _mock(handler)
    pid = "01890a5d-ac96-774b-bcce-b302099a8057"
    server._list_tasks(agent_id="a1", project=pid)
    assert f"project_id={pid}" in seen["url"]


def test_list_tasks_rejects_a_project_name_fail_loud():
    # listOpen scopes ONLY by `project_id` (a UUID) — sending a NAME under
    # that key silently matches nothing and the agent gets a success-shaped
    # empty board. A name must be refused loudly, and no request issued.
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={"tasks": []})

    _mock(handler)
    with pytest.raises(ValueError, match="project id"):
        server._list_tasks(agent_id="a1", project="Q3 Report")
    assert calls == []


@pytest.mark.parametrize("fn,kwargs", [
    (lambda: server._create_task(agent_id="", title="x"), None),
    (lambda: server._set_status(agent_id="", task_id="t", status="done"), None),
    (lambda: server._create_project(agent_id="", name="x"), None),
    (lambda: server._list_tasks(agent_id=""), None),
])
def test_empty_agent_id_raises(fn, kwargs):
    with pytest.raises(ValueError, match="agent_id"):
        fn()


def test_transport_error_surfaces_cleanly():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    _mock(handler)
    with pytest.raises(httpx.HTTPStatusError):
        server._create_task(agent_id="a1", title="x")

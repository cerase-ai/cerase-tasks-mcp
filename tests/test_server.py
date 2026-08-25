"""PROJ-3 — cerase-tasks MCP server.

A thin first-party proxy: the board tools forward to the PROJ-2 internal
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


def test_create_task_forwards_project_as_name_not_project_id():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "t2"})

    _mock(handler)
    server._create_task(agent_id="a1", title="x", project="p9", phase="research")
    assert seen["body"]["project"] == "p9"
    assert "project_id" not in seen["body"]
    assert seen["body"]["phase"] == "research"


def test_create_task_carries_a_description_when_one_is_given():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "t3"})

    _mock(handler)
    server._create_task(
        agent_id="a1",
        title="Answer the Rossi mail",
        description="Quotation for 40 units, they asked for delivery before the 30th.",
    )
    assert seen["body"]["description"].startswith("Quotation for 40 units")


def test_create_task_omits_description_rather_than_sending_null():
    # The endpoint takes `nullable`, so a null would be accepted and stored as
    # one. Omitting the key keeps a task created without a description
    # byte-identical to every task created before the parameter existed.
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "t4"})

    _mock(handler)
    server._create_task(agent_id="a1", title="x")
    assert "description" not in seen["body"]


def test_create_task_tool_passes_the_description_through():
    # The decorated tool is what the model calls, and it is a separate
    # signature from the function under test above: a parameter added to one
    # and not the other is a tool that advertises a field it drops.
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "t5"})

    _mock(handler)
    server.create_task(agent_id="a1", title="x", description="why this task exists")
    assert seen["body"]["description"] == "why this task exists"


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
    assert f"project={pid}" in seen["url"]


def test_list_tasks_passes_a_project_name_through():
    # The name is the form the agent holds — it filed under one. The board
    # resolves an id OR a name under the single `project` key; refusing the
    # name here would put the burden back on the agent to carry an id.
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"tasks": []})

    _mock(handler)
    server._list_tasks(agent_id="a1", project="Q3 Report")
    assert "project=Q3+Report" in seen["url"] or "project=Q3%20Report" in seen["url"]


def test_list_projects_is_a_get_scoped_to_the_agent():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["method"] = request.method
        return httpx.Response(200, json={"projects": [{"id": "p1", "name": "Q3", "folder": None}]})

    _mock(handler)
    out = server._list_projects(agent_id="a1")
    assert seen["method"] == "GET"
    assert seen["url"].endswith("/api/internal/task-board/projects?agent_id=a1")
    assert out["projects"][0]["name"] == "Q3"


def test_rename_project_posts_the_new_name_to_the_named_project():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "p1", "name": "Q3 Financials"})

    _mock(handler)
    out = server._rename_project(agent_id="a1", project="Q3 Report", name="Q3 Financials")
    assert seen["url"].endswith("/api/internal/task-board/projects/Q3%20Report/rename")
    assert seen["body"] == {"agent_id": "a1", "name": "Q3 Financials"}
    assert out["name"] == "Q3 Financials"


def test_merge_projects_posts_source_and_target():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "p2", "tasks_moved": 3})

    _mock(handler)
    out = server._merge_projects(agent_id="a1", source="Report Q3", into="Q3 Report")
    assert seen["url"].endswith("/api/internal/task-board/projects/merge")
    assert seen["body"] == {"agent_id": "a1", "source": "Report Q3", "into": "Q3 Report"}
    assert out["tasks_moved"] == 3


def test_delete_project_issues_a_delete_carrying_the_agent():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"deleted": True})

    _mock(handler)
    out = server._delete_project(agent_id="a1", project="Vuoto")
    assert seen["method"] == "DELETE"
    assert "/api/internal/task-board/projects/Vuoto" in seen["url"]
    assert "agent_id=a1" in seen["url"]
    assert out["deleted"] is True


def test_delete_project_surfaces_the_refusal_when_it_still_holds_tasks():
    # The board refuses a non-empty project because the task rows cascade. The
    # agent has to see that refusal, not a generic failure.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"error": "still holds tasks", "tasks": 2})

    _mock(handler)
    with pytest.raises(httpx.HTTPStatusError):
        server._delete_project(agent_id="a1", project="Pieno")


def test_project_folder_posts_to_the_folder_route():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"folder": "projects/p1", "created": True})

    _mock(handler)
    out = server._project_folder(agent_id="a1", project="Q3 Report")
    assert seen["url"].endswith("/api/internal/task-board/projects/Q3%20Report/folder")
    assert seen["body"] == {"agent_id": "a1"}
    assert out["folder"] == "projects/p1"


@pytest.mark.parametrize("fn,kwargs", [
    (lambda: server._create_task(agent_id="", title="x"), None),
    (lambda: server._set_status(agent_id="", task_id="t", status="done"), None),
    (lambda: server._create_project(agent_id="", name="x"), None),
    (lambda: server._list_tasks(agent_id=""), None),
    (lambda: server._list_projects(agent_id=""), None),
    (lambda: server._rename_project(agent_id="", project="p", name="n"), None),
    (lambda: server._merge_projects(agent_id="", source="a", into="b"), None),
    (lambda: server._delete_project(agent_id="", project="p"), None),
    (lambda: server._project_folder(agent_id="", project="p"), None),
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

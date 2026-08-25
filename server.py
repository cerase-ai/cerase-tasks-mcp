#!/usr/bin/env python3
"""Cerase Tasks MCP — the agent's Projects & Tasks board (PROJ-3).

A first-party MCP (same delivery pattern as cerase-memory/transcriber)
the policy gateway routes to. Unlike those, this server does no work of
its own: it is a **thin proxy** to the PROJ-2 control-plane internal
endpoints, which own the durable board state. The gateway injects the
calling Agent's `agent_id` into every call (un-spoofable), so the agent
can only ever touch its own board.

Tools (9):
  - create_task(agent_id, title, project?, phase?, description?) → the new task
  - set_status(agent_id, task_id, status)          → updated task
  - list_tasks(agent_id, project?)                 → compact open list
  - create_project(agent_id, name)                 → the new project
  - list_projects(agent_id)                        → the whole board's projects
  - rename_project(agent_id, project, name)        → renamed project
  - merge_projects(agent_id, source, into)         → target + tasks moved
  - delete_project(agent_id, project)              → only when it holds none
  - project_folder(agent_id, project)              → workspace folder path

Boundaries the agent must respect (enforced in AGENTS.md, not here):
mem0 = facts it knows · workspace = the files · this board = the STATE.

Env vars:
  - CERASE_CONTROL_PLANE_URL (default http://cerase-control-plane:8000)
  - CERASE_INTERNAL_SECRET   (the internal-bearer shared secret)
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("cerase-tasks")

# Test seam: when set to an httpx transport (e.g. MockTransport) the
# client routes through it instead of the network. Production leaves it
# None. Never set in the running container.
_TRANSPORT: httpx.BaseTransport | None = None

_TIMEOUT = httpx.Timeout(10.0)


def _base_url() -> str:
    return os.environ.get("CERASE_CONTROL_PLANE_URL", "http://cerase-control-plane:8000").rstrip("/")


def _client() -> httpx.Client:
    # Only attach the Authorization header when the secret is present —
    # httpx rejects an empty `Bearer ` value with "Illegal header value".
    secret = os.environ.get("CERASE_INTERNAL_SECRET", "").strip()
    # Accept: application/json makes Laravel return JSON validation errors
    # (422) instead of a 302 redirect when a field is rejected.
    headers = {"Accept": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    return httpx.Client(
        base_url=_base_url(),
        headers=headers,
        timeout=_TIMEOUT,
        transport=_TRANSPORT,
    )


def _require_agent(agent_id: str) -> None:
    if not agent_id:
        raise ValueError("agent_id is required (cannot be empty) — it is bound by the gateway")


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    with _client() as c:
        resp = c.post(path, json=payload)
    resp.raise_for_status()
    return resp.json()


def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    with _client() as c:
        resp = c.get(path, params=params)
    resp.raise_for_status()
    return resp.json()


def _delete(path: str, params: dict[str, Any]) -> dict[str, Any]:
    with _client() as c:
        resp = c.request("DELETE", path, params=params)
    resp.raise_for_status()
    return resp.json()


# ── core logic (importable, no decorator) ────────────────────────────

def _create_task(agent_id: str, title: str, project: str | None = None,
                 phase: str | None = None, description: str | None = None) -> dict[str, Any]:
    _require_agent(agent_id)
    payload: dict[str, Any] = {"agent_id": agent_id, "title": title}
    if project:
        # `project` is a NAME (resolve-or-created server-side),
        # not a UUID — no id to capture from create_project and thread.
        payload["project"] = project
    if phase:
        payload["phase"] = phase
    if description:
        # The column and the endpoint have accepted this since the board
        # existed and no tool ever offered it: of the 28 tasks on the first
        # appliance to run one, 28 had a null description, and one title was
        # 200 characters of answer text because there was nowhere else for it
        # to go. The column caps the title at 300 and this one at nothing.
        payload["description"] = description
    return _post("/api/internal/task-board/tasks", payload)


def _set_status(agent_id: str, task_id: str, status: str) -> dict[str, Any]:
    _require_agent(agent_id)
    return _post(
        f"/api/internal/task-board/tasks/{task_id}/status",
        {"agent_id": agent_id, "status": status},
    )


def _list_tasks(agent_id: str, project: str | None = None) -> dict[str, Any]:
    _require_agent(agent_id)
    params: dict[str, Any] = {"agent_id": agent_id}
    if project:
        # A name and an id are both accepted, under one key. The list endpoint
        # used to scope by id alone, so the form an agent actually holds — the
        # name it filed under — matched nothing and returned an empty board
        # that looked like a successful answer.
        params["project"] = project
    return _get("/api/internal/task-board/tasks", params)


def _create_project(agent_id: str, name: str) -> dict[str, Any]:
    _require_agent(agent_id)
    return _post("/api/internal/task-board/projects", {"agent_id": agent_id, "name": name})


def _list_projects(agent_id: str) -> dict[str, Any]:
    _require_agent(agent_id)
    return _get("/api/internal/task-board/projects", {"agent_id": agent_id})


def _rename_project(agent_id: str, project: str, name: str) -> dict[str, Any]:
    _require_agent(agent_id)
    return _post(
        f"/api/internal/task-board/projects/{project}/rename",
        {"agent_id": agent_id, "name": name},
    )


def _merge_projects(agent_id: str, source: str, into: str) -> dict[str, Any]:
    _require_agent(agent_id)
    return _post(
        "/api/internal/task-board/projects/merge",
        {"agent_id": agent_id, "source": source, "into": into},
    )


def _delete_project(agent_id: str, project: str) -> dict[str, Any]:
    _require_agent(agent_id)
    return _delete(
        f"/api/internal/task-board/projects/{project}",
        {"agent_id": agent_id},
    )


def _project_folder(agent_id: str, project: str) -> dict[str, Any]:
    _require_agent(agent_id)
    return _post(
        f"/api/internal/task-board/projects/{project}/folder",
        {"agent_id": agent_id},
    )


# ── MCP tool surface (thin wrappers) ─────────────────────────────────

@mcp.tool()
def create_task(agent_id: str, title: str, project: str | None = None,
                phase: str | None = None, description: str | None = None) -> dict[str, Any]:
    """Record a user-recognisable unit of work on your board (e.g. answer
    a mail, summarise a PDF) — not micro-steps. Lands in "General" unless
    `project` is given: pass the project NAME (e.g. "Q3 Report") and it is
    created if it doesn't exist yet — no need to create_project first or
    pass an id. `agent_id` is gateway-bound.

    Keep `title` to the short name a person would use in a sentence, and put
    everything else in `description`: what was asked, which file or mail it
    concerns, what "done" means here. The person reading the board a month
    later sees the title first and opens the description to remember what the
    work actually was — a title carrying both reads as neither.
    """
    return _create_task(agent_id, title, project, phase, description)


@mcp.tool()
def set_status(agent_id: str, task_id: str, status: str) -> dict[str, Any]:
    """Move a task along backlog/todo/doing/review/done. Set `doing` when
    you start and `done` when finished — the board records elapsed time.
    `agent_id` is gateway-bound.
    """
    return _set_status(agent_id, task_id, status)


@mcp.tool()
def list_tasks(agent_id: str, project: str | None = None) -> dict[str, Any]:
    """List your open tasks (compact: id, title, status, phase, project).
    Call on demand to re-orient when resuming work — do NOT re-read the
    whole conversation. `agent_id` is gateway-bound. `project` scopes the
    list and takes the project NAME or its id; omit it to list every open
    task.
    """
    return _list_tasks(agent_id, project)


@mcp.tool()
def create_project(agent_id: str, name: str) -> dict[str, Any]:
    """Create a project to group related tasks for a substantial,
    multi-task piece of work; small one-offs can stay in "General". A name
    you already have comes back as that project instead of a second one —
    case and surrounding spaces do not make a new project.
    `agent_id` is gateway-bound.
    """
    return _create_project(agent_id, name)


@mcp.tool()
def list_projects(agent_id: str) -> dict[str, Any]:
    """List your projects with how many tasks each holds (open and total)
    and its workspace folder when it has one. Use it to see what you are
    carrying before opening yet another project. `agent_id` is
    gateway-bound.
    """
    return _list_projects(agent_id)


@mcp.tool()
def rename_project(agent_id: str, project: str, name: str) -> dict[str, Any]:
    """Rename one of your projects — pass its current NAME or id. Refused
    when the new name is already another project's: merge those two
    instead. "General" keeps its name. `agent_id` is gateway-bound.
    """
    return _rename_project(agent_id, project, name)


@mcp.tool()
def merge_projects(agent_id: str, source: str, into: str) -> dict[str, Any]:
    """Move every task of `source` into `into` (each a project NAME or id)
    and retire `source`. Its workspace folder travels with its tasks. Use
    this when you find you opened two projects for one piece of work.
    "General" is emptied rather than removed. `agent_id` is gateway-bound.
    """
    return _merge_projects(agent_id, source, into)


@mcp.tool()
def delete_project(agent_id: str, project: str) -> dict[str, Any]:
    """Delete an EMPTY project — pass its NAME or id. A project that still
    holds tasks is refused, because deleting it would take that work's
    history with it: merge it into another project instead. "General"
    cannot be deleted. `agent_id` is gateway-bound.
    """
    return _delete_project(agent_id, project)


@mcp.tool()
def project_folder(agent_id: str, project: str) -> dict[str, Any]:
    """Get the workspace folder for one of your projects (NAME or id),
    creating it on first call. Put that project's files under the returned
    path so you can find them later — most projects never need one.
    `agent_id` is gateway-bound.
    """
    return _project_folder(agent_id, project)


if __name__ == "__main__":
    mcp.run()

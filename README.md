# cerase-tasks-mcp

An MCP server that gives a Cerase assistant a board of projects and tasks for
the work it does. It stores nothing: every tool is one HTTP call to the board
endpoints of the Cerase control-plane, which keeps the board in its database
and shows it in the console. Outside a Cerase appliance it has nothing to talk
to.

## Tools

| Tool | What it does | Arguments | Returns |
|---|---|---|---|
| `create_task` | Files a task. It lands in the project "General" unless `project` names another, and a project named that way is created if it does not exist. | `agent_id`, `title`, optional `project` (name), `phase`, `description` | `{id, title, status, project, hint}` |
| `set_status` | Moves a task to `backlog`, `todo`, `doing`, `review` or `done`; the board records the elapsed time. | `agent_id`, `task_id`, `status` | `{id, status, started_at, completed_at, hint}` |
| `list_tasks` | Lists the open tasks: id, title, status, phase, project. | `agent_id`, optional `project` (name or id) | `{tasks}` |
| `create_project` | Creates a project. A name that already exists, ignoring case and surrounding spaces, returns that project. | `agent_id`, `name` | `{id, name, created}` |
| `list_projects` | Lists the projects with their open and total task counts and their workspace folder, if any. | `agent_id` | `{projects}` |
| `rename_project` | Renames a project. Refused when the new name belongs to another project; "General" keeps its name. | `agent_id`, `project` (name or id), `name` | `{id, name}` |
| `merge_projects` | Moves every task of `source`, and its workspace folder, into `into`, then retires `source`. "General" is emptied, not removed. | `agent_id`, `source`, `into` (names or ids) | `{id, name, tasks_moved, source_kept, folder}` |
| `delete_project` | Deletes a project that holds no tasks. "General" cannot be deleted. | `agent_id`, `project` (name or id) | `{deleted}` |
| `project_folder` | Returns the project's folder in the assistant's workspace, creating it on the first call. | `agent_id`, `project` (name or id) | `{id, name, folder, created}` |

`agent_id` must not be empty, and every request carries it, so the
control-plane answers with the calling assistant's own board. Inside Cerase the
gateway fills it; the model cannot set it. The rules quoted above (name
matching, refusals, "General") are enforced by the control-plane, not by this
server.

The control-plane refuses a `title` longer than 300 characters. The tool
descriptions tell the assistant to keep the title to a short name and to put
what was asked, and what done means, in `description`. The `hint` field in the
answers to `create_task` and `set_status` reminds the assistant to move the
task to `done` before it replies.

## Settings

| Variable | Default | Purpose |
|---|---|---|
| `CERASE_CONTROL_PLANE_URL` | `http://cerase-control-plane:8000` | Control-plane base URL; the default is its service name inside a Cerase appliance. Requests go to `/api/internal/task-board/…`. |
| `CERASE_INTERNAL_SECRET` | empty | Bearer token for those requests; no `Authorization` header is sent when it is empty. |

## Installation

The connector is published in the Cerase Marketplace as
`studio.guidance/cerase-tasks`
([marketplace page](https://marketplace.cerase.ai/en/p/studio.guidance/cerase-tasks)).
Every Cerase appliance installs it at boot, so its assistants have it without
an install step. The `workplan` skill is what tells an assistant when to use
the board.

The image `ghcr.io/cerase-ai/cerase-tasks-mcp` is built and published from the
copy of these files kept in the Cerase appliance repository, which is private.
This repository carries the same files byte for byte, so a change made only
here does not reach the image.

## Build and run locally

```sh
docker build -t cerase-tasks-mcp .
docker run --rm -p 3000:3000 \
  -e CERASE_CONTROL_PLANE_URL=http://<control-plane>:8000 \
  -e CERASE_INTERNAL_SECRET=<bearer> \
  cerase-tasks-mcp
```

`server.py` speaks MCP over stdio; the image runs it behind `mcp-proxy`, which
serves Streamable HTTP at `http://localhost:3000/mcp` and SSE at
`http://localhost:3000/sse`. The image's `HEALTHCHECK` runs
`scripts/healthcheck.py`, an MCP client that completes the handshake and lists
the tools over `/mcp`; its `CERASE_HEALTHCHECK_*` variables exist to point it
at a stub in tests.

The tests replace the HTTP transport with a mock, so they need no
control-plane:

```sh
pip install -r requirements.txt pytest
python -m pytest tests/
```

## License

MIT. See [LICENSE](LICENSE).

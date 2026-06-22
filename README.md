# cerase-tasks MCP

The agent's **Projects & Tasks board** (PROJ-3). A thin first-party
proxy to the control-plane PROJ-2 internal endpoints — it owns no state
itself; the durable, Filament-renderable board lives in the
control-plane Postgres (Decision B). Same delivery pattern as
`cerase-memory` / `cerase-transcriber`: the policy gateway routes to it
and injects the calling Agent's `agent_id` (un-spoofable), so the agent
can only ever touch its own board.

## Tools

- `create_task(agent_id, title, project?, phase?) → task` — record a
  unit of work the user would recognise (NOT a micro-step). Lands in the
  default "General" project unless `project` (a project id) is given.
- `set_status(agent_id, task_id, status) → task` — move along
  backlog/todo/doing/review/done; the board stamps elapsed time.
- `list_tasks(agent_id, project?) → {tasks}` — compact open list
  (`id, title, status, phase`); call on demand to re-orient.
- `create_project(agent_id, name) → project`.

`agent_id` is required and gateway-bound — the server raises on empty.

## Boundaries

mem0 = facts the agent knows · workspace = the actual files · **this
board = the STATE of the work**. Micro-steps (how the agent does it)
stay in OpenCode's ephemeral native todo, never here.

## Env

- `CERASE_CONTROL_PLANE_URL` (default `http://cerase-control-plane:8000`)
- `CERASE_INTERNAL_SECRET` (the internal-bearer shared secret)

GHCR image `ghcr.io/cerase-ai/cerase-tasks-mcp:<tag>`.

# Cerase Tasks MCP — the agent's Projects & Tasks board (PROJ-3).
#
# A thin first-party proxy to the control-plane PROJ-2 internal
# endpoints (no work of its own). Exposes 4 tools: create_task,
# set_status, list_tasks, create_project. FastMCP stdio bridged by
# mcp-proxy — same shape as the other cerase-* MCP images.
FROM python:3.13.9-slim@sha256:326df678c20c78d465db501563f3492d17c42a4afe33a1f2bf5406a1d56b0e86

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.lock /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.lock \
    && rm /tmp/requirements.txt /tmp/requirements.lock

COPY server.py /app/server.py

RUN groupadd -r appuser \
 && useradd -r -g appuser -u 1000 -m -d /home/appuser -s /usr/sbin/nologin appuser \
 && chown -R appuser:appuser /app
USER appuser
WORKDIR /home/appuser

EXPOSE 3000

# M-CI-3: image-level liveness — runtime-spawned MCP containers have no
# compose healthcheck, this is the only signal `docker ps`/doctor sees.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import socket; socket.create_connection(('127.0.0.1', 3000), timeout=5)" || exit 1

ENTRYPOINT ["sh", "-c", "exec mcp-proxy --port 3000 --host 0.0.0.0 --pass-environment -- python /app/server.py"]

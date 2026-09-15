#!/bin/bash
# ==============================================================================
# Cloud Run Dual-Process Supervisor:
# Runs the Node Malloy Publisher (execution & UI) + Stage 3 Python MCP Server (RAG)
# together in ONE container, listening on Cloud Run's $PORT (default 8080).
#
#   Node publisher  -> 127.0.0.1:4000  (UI & REST API)
#   Node publisher  -> 127.0.0.1:5050  (internal query execution engine)
#   Python server   -> PORT / 8080     (public Cloud Run MCP gateway + UI proxy)
#
# Features:
#   * Answers malloy_getContext via Stage 3 Dual-Pathway (Path A in-RAM + Path B ChromaDB)
#   * Relays all execution queries to Node publisher on 127.0.0.1:5050
#   * Proxies all UI & REST requests to Node publisher on 127.0.0.1:4000
#   * Traps SIGTERM and SIGINT to gracefully terminate both processes
# ==============================================================================
set -e

CTX_DIR="/app/context"
NODE_PID=""
PYTHON_PID=""

cleanup() {
  echo "[entrypoint] Received shutdown signal, gracefully terminating processes..."
  [ -n "$PYTHON_PID" ] && kill -TERM "$PYTHON_PID" 2>/dev/null || true
  [ -n "$NODE_PID" ] && kill -TERM "$NODE_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}

trap cleanup TERM INT

echo "[entrypoint] Starting Malloy Publisher (Node) on 127.0.0.1:4000 (UI) and 127.0.0.1:5050 (MCP) ..."
npx @malloy-publisher/server \
  --init \
  --server_root /app/workspace \
  --host 127.0.0.1 \
  --port 4000 \
  --mcp_port 5050 &
NODE_PID=$!

echo "[entrypoint] Waiting for Node MCP on 127.0.0.1:5050 ..."
i=0
until curl -s -o /dev/null --max-time 2 \
      -X POST http://127.0.0.1:5050/mcp \
      -H "Content-Type: application/json" \
      -H "Accept: application/json, text/event-stream" \
      -d '{"jsonrpc":"2.0","id":0,"method":"tools/list","params":{}}'; do
  i=$((i + 1))
  [ "$i" -gt 60 ] && { echo "[entrypoint] Node MCP not ready after 60s; starting Stage 3 server anyway."; break; }
  sleep 1
done
echo "[entrypoint] Node MCP is ready! (attempt $i)"

echo "[entrypoint] Starting Stage 3 Dual-Pathway MCP Server on PORT=${PORT:-8080} ..."
cd "$CTX_DIR"
python3 step_3_mcp_server/step_3_mcp_dual_pathway_server.py &
PYTHON_PID=$!

# Wait for either process to exit; if one dies, terminate both and exit
wait -n "$PYTHON_PID" "$NODE_PID" 2>/dev/null || wait "$PYTHON_PID"
cleanup

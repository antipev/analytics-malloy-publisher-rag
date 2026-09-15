# Deployment & Operations Guide

This guide details how to run the **Malloy Publisher UI** and **Malloy Publisher MCP Server** locally in your web browser and deploy to **Google Cloud Run**, along with data preparation, Gemini CLI integration, and Google Apps Script endpoints.

---

## 1. Live Production Endpoints

| Service | Target URL | Description |
| :--- | :--- | :--- |
| **Malloy Publisher UI** | https://malloy-publisher-bolcwt6srq-nn.a.run.app | Interactive visual explorer and web dashboard |
| **Malloy Publisher MCP** | https://malloy-publisher-mcp-bolcwt6srq-nn.a.run.app/mcp | AI Agent MCP endpoint (Dual-Pathway fast router + ChromaDB) |
| **Google Apps Script Web App** | https://script.google.com/macros/s/AKfycbzfCG7RNWVxVkaiHiGdeGKf9d74co43LzjjEZj_JqPH-fRKQINcSwsLJezBryfy39FQ/exec | Google Apps Script frontend integration |

### Environment Path Mapping
* **Host / Development Root:** `/home/maxantipev/analytics-malloy-publisher/`
* **Docker Container Root:** `/app/`

---

## 2. DuckDB Parquet Path Resolution Architecture (CRITICAL)

In a multi-package repository architecture, `.malloy` models must run seamlessly in both **VS Code (interactive modeling)** and **Malloy Publisher (production web/MCP engine & Cloud Run)**.

### The Challenge
* **Model Encapsulation:** Packages inside `workspace/` (such as `workspace/thelook_ecommerce/`) are self-contained. Their models reference Parquet files using clean package-relative paths:
  ```malloy
  source: distribution_centers_raw is duckdb.table('1_raw_views/distribution_centers/*.parquet')
  ```
* **Malloy Publisher (Local & Cloud Run):** When running `npx @malloy-publisher/server --server_root ./workspace`, Publisher automatically isolates each package and anchors DuckDB's `workingDirectory` directly to the package root (`workspace/thelook_ecommerce/` or `/app/workspace/thelook_ecommerce/` in Docker). `1_raw_views/...` resolves natively.
* **VS Code Malloy Extension:** When developers open the repository root (`analytics-malloy-publisher`) in VS Code, DuckDB defaults its search path to the workspace root. Without configuration, DuckDB searches for `/analytics-malloy-publisher/1_raw_views/...` and throws:
  `IO Error: No files found that match the pattern "1_raw_views/distribution_centers/*.parquet"`

### The Solution: Top-Level `malloy-config.json`
To bridge the developer environment with the production server, the root configuration file [`malloy-config.json`](./malloy-config.json) explicitly maps DuckDB's working directory to the active package:

```json
{
    "connections": {
        "bigquery": {
          "is": "bigquery",
          "defaultProjectId": "my-1-st-project-training"
        },
        "duckdb": {
            "is": "duckdb",
            "workingDirectory": "workspace/thelook_ecommerce"
        }
    }
}
```

### Result: 100% Dual-Environment Compatibility
1. **In VS Code:** The Malloy extension discovers the root `malloy-config.json` and routes DuckDB queries into `workspace/thelook_ecommerce/`, allowing full interactive execution, schema discovery, and query previews.
2. **In Malloy Publisher:** The server uses its built-in package sandboxing, ignoring the IDE config and serving `thelook_ecommerce` directly.
3. **In Cloud Run (Docker):** Standard package-relative paths work out-of-the-box with zero path rewrites, symlinks, or container modifications.

---

## 3. DuckDB Database Preparation (Optional Standalone File)

Each package in Malloy Publisher automatically receives its own DuckDB sandbox when querying `.parquet` files directly via `duckdb.table(...)`. 

If you wish to create a standalone consolidated DuckDB database file (`thelook.db`):

```bash
duckdb thelook.db <<EOF
CREATE TABLE distribution_centers AS SELECT * FROM read_parquet('workspace/thelook_ecommerce/1_raw_views/distribution_centers/*.parquet');
CREATE TABLE events               AS SELECT * FROM read_parquet('workspace/thelook_ecommerce/1_raw_views/events/*.parquet');
CREATE TABLE inventory_items      AS SELECT * FROM read_parquet('workspace/thelook_ecommerce/1_raw_views/inventory_items/*.parquet');
CREATE TABLE order_items          AS SELECT * FROM read_parquet('workspace/thelook_ecommerce/1_raw_views/order_items/*.parquet');
CREATE TABLE products             AS SELECT * FROM read_parquet('workspace/thelook_ecommerce/1_raw_views/products/*.parquet');
CREATE TABLE users                AS SELECT * FROM read_parquet('workspace/thelook_ecommerce/1_raw_views/users/*.parquet');
CREATE TABLE orders               AS SELECT * FROM read_parquet('workspace/thelook_ecommerce/1_raw_views/orders/*.parquet');
.exit
EOF
```

---

## 4. Running Malloy Publisher Locally in the Web Browser

### Workspace Configuration (`workspace/publisher.config.json`)
The workspace configuration links environment `theLook-DEMO` to packages within `workspace/`:

```json
{
  "frozenConfig": false,
  "environments": [
    {
      "name": "theLook-DEMO",
      "connections": [],
      "packages": [
        {
          "name": "thelook_ecommerce",
          "location": "./thelook_ecommerce"
        }
      ]
    }
  ]
}
```

### Quick Start: Launch Web UI
Run the official Malloy Publisher server from the repository root:

```bash
# Ensure Node 20+ is in PATH
####export PATH="$HOME/.nvm/versions/node/v20.20.0/bin:$PATH"
export PATH="/home/maxantipev/.nvm/versions/node/v20.20.0/bin:$PATH"
export PATH="$HOME/.nvm/versions/node/v20.20.0/bin:$PATH"

# Start Malloy Publisher UI pointing to the workspace
npx @malloy-publisher/server --init --server_root ./workspace --port 4000

```

1. Open your web browser to: **`http://localhost:4000`**
2. You will see the **theLook-DEMO** environment with the **thelook_ecommerce** package.
3. Click on **`ecommerce_explore`** to open the interactive Visual Explorer (drag and drop dimensions, measures, filters, and run queries).
4. Click on **`business_pulse`** under Dashboards to view pre-rendered KPIs, line charts, and brand ranking tables.

### Active Development / Live Reload (Watch Mode)
When modifying `.malloy` models or notebooks, launch with `--watch-env` so Publisher reloads edits in place:

```bash
npx @malloy-publisher/server --init --server_root ./workspace --port 4000 --watch-env theLook-DEMO
```

### Local Health & Diagnostic Endpoints
```bash
# Check server health
curl http://localhost:4000/health

# List registered environments and packages
curl http://localhost:4000/api/v0/environments
```

---

## 5. Running the Complete MCP System Locally

To run both the execution engine and the Python Dual-Pathway AI RAG gateway on your machine:

### Terminal 1: Launch Execution Engine & Node MCP
```bash
export PATH="$HOME/.nvm/versions/node/v20.20.0/bin:$PATH"
npx @malloy-publisher/server --init --server_root ./workspace --port 4000 --mcp_port 5050
```

### Terminal 2: Launch Stage 3 Dual-Pathway Python MCP Gateway
```bash
cd /home/maxantipev/analytics-malloy-publisher/context
source .venv/bin/activate
PORT=8080 python3 step_3_mcp_server/step_3_mcp_dual_pathway_server.py
```
* **AI Agent Gateway:** Connect your AI agent / Claude / Gemini CLI to `http://localhost:8080/mcp`.
* **Execution Engine:** Queries forward seamlessly to internal port `5050`.

---

## 6. Google Cloud Run Deployment Workflow

Both services share an identical container architecture based on `node:20-slim`. The only difference is that `Dockerfile.mcp` defines `ENV MALLOY_SERVER_MODE=mcp`, exposes port `5050`, and passes `--mcp_port 5050`.

Prior to building each service, copy the respective Dockerfile to `Dockerfile` at root:

### Option A: Deploy Malloy Publisher UI (`malloy-publisher`)

1. **Prepare Dockerfile:**
   ```bash
   cp Dockerfile.ui Dockerfile
   ```

2. **Build and push container image to Google Container Registry:**
   ```bash
   gcloud builds submit --tag gcr.io/my-1-st-project-training/malloy-publisher .
   ```

3. **Deploy UI Service to Cloud Run:**
   ```bash
   gcloud run deploy malloy-publisher \
     --image gcr.io/my-1-st-project-training/malloy-publisher \
     --platform managed \
     --region northamerica-northeast1 \
     --allow-unauthenticated \
     --memory 4Gi \
     --cpu 2 \
     --cpu-boost \
     --timeout 600
   ```

4. **Verify UI Deployment Logs:**
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=malloy-publisher" \
     --limit 20 \
     --format="table(timestamp, textPayload)"
   ```

---

### Option B: Deploy Malloy Publisher MCP (`malloy-publisher-mcp`)

1. **Prepare Dockerfile:**
   ```bash
   cp Dockerfile.mcp Dockerfile
   ```

2. **Build and push MCP container image to Google Container Registry:**
   ```bash
   gcloud builds submit --tag gcr.io/my-1-st-project-training/malloy-publisher-mcp .
   ```

3. **Deploy MCP Service to Cloud Run:**
   ```bash
   gcloud run deploy malloy-publisher-mcp \
     --image gcr.io/my-1-st-project-training/malloy-publisher-mcp \
     --platform managed \
     --region northamerica-northeast1 \
     --allow-unauthenticated \
     --memory 4Gi \
     --cpu 2 \
     --cpu-boost \
     --timeout 600 \
     --port 5050
   ```

4. **Verify MCP Deployment Logs:**
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=malloy-publisher-mcp" \
     --limit 20 \
     --format="table(timestamp, textPayload)"
   ```

---

## 7. Connecting AI Clients (Gemini CLI)

### 1. Test Endpoint Availability via `curl`
```bash
curl -X POST https://malloy-publisher-mcp-bolcwt6srq-nn.a.run.app/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}'
```

### 2. Register Server with Gemini CLI
```bash
gemini mcp add malloy-cloud --transport sse \
  --header "Accept: application/json, text/event-stream" \
  https://malloy-publisher-mcp-bolcwt6srq-nn.a.run.app/mcp
```

### 3. Verify in Gemini CLI
```bash
gemini
# Inside the Gemini prompt:
/mcp list
```

---

## 8. Google Apps Script Integration

* **Deployment ID:** `AKfycbzfCG7RNWVxVkaiHiGdeGKf9d74co43LzjjEZj_JqPH-fRKQINcSwsLJezBryfy39FQ`
* **Script ID:** `1xnakl-tht4OiX4kySkMptTz2jmMBJIjfhfAv7MdelCaf534qen4DRdfW`
* **Web App URL:** `https://script.google.com/macros/s/AKfycbzfCG7RNWVxVkaiHiGdeGKf9d74co43LzjjEZj_JqPH-fRKQINcSwsLJezBryfy39FQ/exec`

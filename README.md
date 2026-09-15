# Analytics Malloy Publisher: Project Overview

This project implements a production-grade **Malloy Publisher & Agentic AI Semantic Layer** featuring a unified package modeling architecture and a dual-pathway Context RAG retrieval engine.

## 📂 Project Structure

The repository is organized into three primary layers:

### 1. Multi-Package Publisher Workspace: `workspace/`
Contains the publisher environment configuration and self-contained analytical packages:
* **`publisher.config.json`:** Global environment definitions linking packages to environments (`workspace/publisher.config.json`).
* **`malloy-config.json` (Root):** Developer IDE configuration mapping DuckDB's `workingDirectory` to `workspace/thelook_ecommerce`, guaranteeing identical Parquet path resolution in VS Code and Malloy Publisher.
* **`thelook_ecommerce/`:** Production eCommerce star-schema package:
  * **`1_raw_views/`:** Raw physical table views (`config.malloy`) and Parquet storage files.
  * **`2_refinements/`:** Staging entities, primary keys, semantic measures, and `#(doc)` definitions (`orders`, `order_items`, `products`, `users`, `events`, `event_session_facts`, `event_session_funnel`, `inventory_items`, `distribution_centers`, `bridge`).
  * **`3_explores/`:** Analytical star schema explores (`ecommerce_explore.malloy` unifying domains through the compose bridge pattern).
  * **`4_analysis/`:** Business dashboards (`business_pulse.dashboard.malloynb`) and exploratory ad-hoc queries.
  * **`public/`:** Pre-compiled static HTML data apps served directly by Malloy Publisher (`fulfillment_centers_2026.html`, `top_products_2026.html`).
  * **`publisher.json`:** Package manifest explicitly declaring published explores (e.g. `3_explores/ecommerce_explore.malloy`).
  * **Documentation:** See [`workspace/thelook_ecommerce/README.md`](file:///home/maxantipev/analytics-malloy-publisher/workspace/thelook_ecommerce/README.md).

### 2. AI Context & Retrieval Engine: `context/`
AST compilation, schema context extraction, and the **Stage 3 Dual-Pathway Execution Engine**:
* **Stage 1 (`step_1_extract/`)**: AST compilation via Node `@malloydata/malloy` compiler, generating schema snapshots (`data/step_1_<context>_raw_extracted.json`) and auto-deriving domain intent definitions (`data/step_1_<context>_domain_context.json`).
* **Stage 2 (`step_2_build_rag/`)**: Multi-Layer Intent Graph RAG construction (Business Intents, Entities, and Metrics) persisted to `data/step_2_<context>_rag_intent_graph.json` and indexed into ChromaDB.
* **Stage 3 (`step_3_mcp_server/`)**: Cloud Run MCP Server gateway hosting the public MCP endpoint (port 8080). Implements **Path A** (<0.02ms in-RAM Fast Router) and **Path B** (ChromaDB vector search), providing the 4-Pillar 3-Section context blueprint to downstream AI agents. Relays SQL execution to Node on internal port 5050.
* **Orchestrator (`orchestration/run_context_pipeline.py`)**: Unified build runner driving Stage 1 extraction, Stage 2 RAG building, and Chroma indexing (`python3 orchestration/run_context_pipeline.py --all --index-chroma`).
* **Documentation:** See [`context/README.md`](file:///home/maxantipev/analytics-malloy-publisher/context/README.md).

---

## 🌐 Live Production Endpoints
* **Malloy Publisher UI:** https://malloy-publisher-bolcwt6srq-nn.a.run.app/
* **Malloy MCP Server:**   https://malloy-publisher-mcp-bolcwt6srq-nn.a.run.app/mcp
* **Google Apps Script:**  https://script.google.com/macros/s/AKfycbzfCG7RNWVxVkaiHiGdeGKf9d74co43LzjjEZj_JqPH-fRKQINcSwsLJezBryfy39FQ/exec
* **Full Deployment Manual:** See [DEPLOYMENT.md](./DEPLOYMENT.md)

---

## 🚀 Workflow

1. **Develop:** Build, test, and document models with `#(doc)` tags in `workspace/thelook_ecommerce/2_refinements/` and `workspace/thelook_ecommerce/3_explores/`.
2. **Publish:** Declare target explores explicitly in `workspace/thelook_ecommerce/publisher.json`.
3. **Index & Context:** Run `context` pipeline (`run_context_pipeline.py --all --index-chroma`) to generate the Intent Graph and ChromaDB embeddings.
4. **Deploy:** Build and deploy containers to Cloud Run or run locally using [DEPLOYMENT.md](./DEPLOYMENT.md).
5. **Verify:** Run business queries against MCP and evaluate results in [TEST.md](./TEST.md).

---

## 📄 Publishing Static HTML Data Apps

Static report HTML files can be served by Malloy Publisher with no build step — just drop them in the package's `public/` folder:

1. **Place files:** Copy your `.html` reports into `thelook_ecommerce/public/` (e.g. `fulfillment_centers_2026.html`, `top_products_2026.html`).
2. **Serve:** Publisher serves every file under `public/` at `/environments/<env>/packages/<pkg>/<file>`.
3. **Redeploy:** Rebuild + redeploy the Docker image — the `public/` folder is included automatically.

> Only `public/` is web-served; models, data, and `publisher.json` stay private.

---

## 🔗 Resources
* [Malloy Official Docs](https://docs.malloydata.dev/)
* [Modeling Best Practices](https://docs.malloydata.dev/documentation/language/modeling)
* [Malloy Publisher Info](https://github.com/malloydata/malloy-publisher)


## 🤖 Gemini AI Setup
Objective 1: to use AI agent for coding => Technical users, Aanlysts, Engineers

Objective 2: to use AI agent for quering MCP Server => for Analysts, Business Users

### Step 1: Install NVM
Run this command in your terminal to download and install NVM:
```
Bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
```

### Step 2: Reload your terminal environment
To make the nvm command available without closing and reopening your terminal, run:
```
Bash
source ~/.bashrc
```
(Note: If you are using Zsh instead of Bash, run source ~/.zshrc instead).


### Step 3: Install Node.js
Now, you can install the latest Long Term Support (LTS) version of Node.js, which is fully compatible with the Gemini CLI:
```
Bash
nvm install --lts
```
### Step 4: Verify the installation
Check that Node and NPM installed correctly and are on the right versions:
```
Bash
node -v
npm -v
```

(You should see a version number starting with v18, v20, or v22).

________________________________________
### Step 5: Install the Gemini CLI
Now that your environment is properly set up, you can successfully install and run the Gemini CLI:
```
Bash
npm install -g @google/gemini-cli
```
Once it finishes, just type:

```
Bash
gemini
```

It will prompt you to log in via your browser, and you'll be ready to use it!

Reference: https://geminicli.com/docs/get-started/installation/


## 🤖 Connecting Gemini CLI to Malloy Publisher MCP
The Gemini CLI uses a `settings.json` file to manage external tool connections. Here is exactly how to set it up.

### Step 1: Open the Gemini CLI settings file
The global configuration file for the Gemini CLI lives in a hidden .gemini folder in your home directory.
Run this command in your terminal to create the directory (if it doesn't exist) and open/create the file `settings.json`(if it does't exist yet):
```
Bash
mkdir -p ~/.gemini

```
### Step 2: Add your MCP server configuration
In the editor, you need to define an mcpServers object. In this particular example, the MCPserver is hosted on Google Cloud Run (https://...a.run.app/), 

Update settings: Cloud Run server specifically uses the /mcp endpoint (not /sse), and it strictly requires that Accept header so it knows to stream the events back to you.
Run this command in your terminal:
```
cat << 'EOF' > ~/.gemini/settings.json
{
  "ide": {
    "hasSeenNudge": true,
    "enabled": true
  },
  "security": {
    "auth": {
      "selectedType": "oauth-personal"
    }
  },
  "mcpServers": {
    "malloy-cloud": {
      "url": "https://malloy-publisher-mcp-bolcwt6srq-nn.a.run.app/mcp",
      "headers": {
        "Accept": "application/json, text/event-stream"
      }
    }
  }
}
EOF
```

### Step 3: Verify the connection
Now, let's make sure the Gemini CLI successfully reads the file and connects to your Malloy server.
Launch the CLI by running:
```
Bash
gemini
```
Once the prompt is ready, type the following built-in slash command to check your active servers:

```
Bash
/mcp list
```

If the configuration is correct, you should see a 🟢 malloyPublisher - Ready status indicator along with a list of the specific tools and prompts your Malloy server exposes!
________________________________________



## 🤖 GEMINI Skills set up
In oder to correctly query Malloy Publisher MCP server skill set for Gemeni needed.

Follow these guide here:
https://geminicli.com/docs/cli/skills/
https://geminicli.com/docs/cli/creating-skills/

For this particular case current repository contains [View Gemini Configuration](./.gemini/) folder (usually outside of this repository, but for this case added to repository for convenience) with "malloy-query-best-practices" skill for testing

---

## 🧪 MCP & RAG Verification Test (Live Cloud Run)

### 1. Verification Command & Live Response

Execute the following `curl` command in your terminal to test the live Cloud Run MCP server context retrieval tool (`malloy_getContext`):

```bash
curl -X POST https://malloy-publisher-mcp-bolcwt6srq-nn.a.run.app/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "malloy_getContext",
      "arguments": {
        "environmentName": "theLook-DEMO",
        "packageName": "thelook_ecommerce",
        "query": "Which traffic channels generate the highest profit margins and sales volume?"
      }
    }
  }'
```

#### Expected Server Response:
```json
event: message
data: {"result":{"isError":false,"content":[{"type":"resource","resource":{"uri":"malloy://environment/theLook-DEMO/package/thelook_ecommerce#get-context","mimeType":"application/json","text":"{\"results\":[{\"kind\":\"measure\",\"name\":\"Average_Gross_Margin\",\"source\":\"ecommerce_explore\",\"environmentName\":\"theLook-DEMO\",\"packageName\":\"thelook_ecommerce\",\"modelPath\":\"3_explores/ecommerce_explore.malloy\",\"doc\":\"\\\"The average profitability per order, calculated as the total gross margin divided by the number of orders.\\\"\"},{\"kind\":\"dimension\",\"name\":\"User_Traffic_Source\",\"source\":\"ecommerce_explore\",\"environmentName\":\"theLook-DEMO\",\"packageName\":\"thelook_ecommerce\",\"modelPath\":\"3_explores/ecommerce_explore.malloy\",\"doc\":\"\\\"The marketing channel or source that brought the user to the site.\\\"\"},{\"kind\":\"measure\",\"name\":\"Total_Gross_Margin\",\"source\":\"ecommerce_explore\",\"environmentName\":\"theLook-DEMO\",\"packageName\":\"thelook_ecommerce\",\"modelPath\":\"3_explores/ecommerce_explore.malloy\",\"doc\":\"\\\"The total profit remaining after subtracting the cost of goods sold (COGS) from total revenue.\\\"\"},{\"kind\":\"measure\",\"name\":\"Gross_Markup_Percent\",\"source\":\"ecommerce_explore\",\"environmentName\":\"theLook-DEMO\",\"packageName\":\"thelook_ecommerce\",\"modelPath\":\"3_explores/ecommerce_explore.malloy\",\"doc\":\"\\\"Markup Percentage: The profit expressed as a percentage of the cost (ROI on inventory investment).\\\" percent\"}]}"}}]},"jsonrpc":"2.0","id":2}
```

---

### 💡 Why RAG is Now Successfully Executed & Working (Plain English)

1. **Semantic Concept Mapping**:
   When given the unstructured question *"Which traffic channels generate the highest profit margins and sales volume?"*, the RAG retrieval engine correctly translated business concepts into exact Malloy schema primitives:
   - **"Traffic Channels"** $\rightarrow$ `User_Traffic_Source` (Dimension)
   - **"Profit Margins & Sales Volume"** $\rightarrow$ `Average_Gross_Margin`, `Total_Gross_Margin`, and `Gross_Markup_Percent` (Measures).

2. **Zero Context Bloat / Token Efficiency**:
   Instead of dumping hundreds of raw schema fields or the entire DuckDB database into the LLM context, the RAG engine extracted **only the exact 4 relevant dimensions & measures** required for an AI agent to write a valid Malloy query.

3. **Sub-Millisecond Routing & Live Cloud Production**:
   The request was handled over a live Google Cloud Run HTTP/SSE endpoint via JSON-RPC 2.0 (`"isError": false`), demonstrating that pre-built Intent Knowledge Graphs in `context` are compiled directly into the production container and served live.

> 📊 **Full Live Testing & Executive Business Results:**  
> For the complete 6-scenario live evaluation report (including the Flagship Q1 2026 Distribution Center Profitability ranking, Company-Wide Financials, Supply Chain Lost Sales, and Global Demographics), see **[`context/TEST.md`](./context/TEST.md)**.

---

### 💡 Suggested Additional Test Queries

#### Test 1: Customer Demographics & Geographic Analysis
```bash
curl -X POST https://malloy-publisher-mcp-bolcwt6srq-nn.a.run.app/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "malloy_getContext",
      "arguments": {
        "environmentName": "theLook-DEMO",
        "packageName": "thelook_ecommerce",
        "query": "What are total sales by user country and age demographic?"
      }
    }
  }'
```

#### Test 2: Order Fulfillment & Logistics Performance
```bash
curl -X POST https://malloy-publisher-mcp-bolcwt6srq-nn.a.run.app/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "malloy_getContext",
      "arguments": {
        "environmentName": "theLook-DEMO",
        "packageName": "thelook_ecommerce",
        "query": "How many orders were shipped and delivered versus canceled?"
      }
    }
  }'
```

#### Test 3: List All Available Tools (MCP Protocol Schema Check)
```bash
curl -X POST https://malloy-publisher-mcp-bolcwt6srq-nn.a.run.app/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/list",
    "params": {}
  }'
```
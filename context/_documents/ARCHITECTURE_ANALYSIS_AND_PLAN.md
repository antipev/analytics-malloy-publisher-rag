# Architecture Analysis & Implementation Plan: `C_Context` for Malloy Publisher MCP on Cloud Run

## 1. Executive Architecture Assessment

The `C_Context` subsystem bridges the **Malloy Semantic Layer** (`A_Semantic_Layer`, `B_Published_Semantic_Layer`) with **AI Agents** calling the Malloy Publisher MCP server on **Google Cloud Run**.

### 1.1 The 4 Core Architectural Requirements (from `C_Context/README.md`)

1. **Stage 1 (Extract & Inspect)**:
   - Extract AST structures directly from `@malloydata/malloy` in Node.js (fields, measures, dimensions, joins, annotations).
   - Flatten them and produce **both** structured JSON (`step_1_<context>_raw_extracted.json`) and developer-inspection Markdown (`step_1_<context>_inspection.md`).
2. **Stage 2 (Chunk & Index)**:
   - Implement Strategy 3 (Agentic / Multi-Layer RAG) by indexing the ontology into 3 node levels:
     - **Business Intent Nodes**: High-level analytical goals (revenue, conversion, inventory).
     - **Entity Graph Nodes**: Root explore and joined entities with cardinality.
     - **Field/Metric Nodes**: Dimensions and measures with full docstrings.
   - Produce **both** structured RAG chunks JSON (`step_2_<context>_rag_intent_graph.json`) and Knowledge Map Markdown (`step_2_<context>_knowledge_map.md`).
3. **Stage 3 (Serve & Answer / MCP Runtime)**:
   - **Path A (<1ms)**: In-Memory Fast Router matching user terms to intents and models in system RAM without network overhead.
   - **Path B (Vector Semantic Search)**: ChromaDB semantic search over field/metric nodes when questions are ambiguous or novel.
   - **4 Pillars of Retrieval Quality**: Fully-qualified namespaces (`order_items.Total_Revenue`), executable Malloy blueprints (`run: explore -> { ... }`), structured 3-section context, and expanded Top-K subgraphs.
4. **Cloud Run Container Deployment**:
   - Run the MCP server reliably within Cloud Run's single-port constraint (`PORT=8080`).
   - Intercept `malloy_getContext` to return rich 4-pillar context.
   - Relay execution queries (`malloy_executeQuery`, `malloy_compile`, etc.) to the official Node.js `@malloy-publisher/server` running on `127.0.0.1:5050`.

---

## 2. File-by-File Forensic Audit

### 2.1 `C_Context/README.md`
* **Status**: Excellent conceptual design, but architecturally out of sync with recent changes.
* **Findings**:
  * **MCP Implementation Discrepancy**: Lines 41–48 state that `step_3_mcp_dual_pathway_server.py` implements the MCP server using `mcp.server.fastmcp`. FastMCP is not used; `mcp_front.py` was introduced as a FastAPI reverse proxy.
  * **Missing Files**: The README does not document `mcp_front.py`, `entrypoint.sh`, `_context_common.py`, or `run_context_pipeline.py`.
  * **File Naming Mismatch**: The README references un-namespaced files (`step_1_malloy_raw_extracted.json`), whereas the active pipeline generates namespaced artifacts (`step_1_<context_id>_raw_extracted.json`).
  * **Markdown Discrepancy**: Requirement 1 mandates both Markdown and JSON artifacts, but line 108 states Markdown generation was commented out.

### 2.2 `_context_common.py`
* **Status**: Clean leaf module; needs minor robustness hardening.
* **Findings**:
  * **Strengths**: Dynamic package discovery from `publisher.config.json` and package-level `publisher.json`. `derive_domain_context()` generates intelligent starting intents and keyword maps with zero manual configuration.
  * **Hardcoded Paths**: `PUBLISHER_CONFIG_PATH = os.path.join(BASE_DIR, "publisher.config.json")` should accept an environment variable override (`MALLOY_PUBLISHER_CONFIG`) for Docker or test environments.
  * **Dimension Selection Edge Case**: In `_looks_technical_dim()`, if an explore has only technical dimensions (e.g. ID-only lookup tables), `_preferred_group_by()` returns an empty list, which can cause downstream template crashes.

### 2.3 `step_1_compile_malloy.js`
* **Status**: Working Node.js compiler bridge.
* **Findings**:
  * **Unused Parameter**: `process.argv[3]` (passed as `config_path` by Python) is never read or used.
  * **Deep Join Limitation**: Flattens nested joins into dotted names (`order_items.inventory_items.cost`), but only tracks top-level entities in `joined_entities`.
  * **Primary Key Formatting**: Assigns `explore.primaryKey || null`. In Malloy AST, `primaryKey` can be an object or array; it should be normalized to a clean string or array of strings.

### 2.4 `step_1_python_context_retrieval_script.py`
* **Status**: Functional, but contains duplicate/conflicting extraction logic.
* **Findings**:
  * **Two Competing Paradigms**:
    1. Legacy directory crawler (`extract_and_inspect_malloy_ontology`): Scans directories via `os.walk`, checks if `"B_Published_Semantic_Layer" in repo_dir`, and builds Markdown tables.
    2. Dynamic package extractor (`compile_package_explores` and `extract_context`): Uses `_context_common.py` to inspect `publisher.config.json`.
  * Running the file via CLI executes the new logic, but importing it as described in the README and Jupyter notebook invokes the legacy crawler.
  * **Markdown Generation Missing**: `extract_context()` does not output the Markdown inspection file required by Requirement 1.

### 2.5 `step_2_build_rag_intent_graph.py`
* **Status**: Successfully generates 203 RAG chunks (6 Intent, 10 Entity, 187 Field nodes), but has syntax edge cases and dead code.
* **Findings**:
  * **Multi-Dot Backtick Bug**:
    ```python
    def malloy_field_ref(name: str) -> str:
        if "." in name:
            head, tail = name.rsplit(".", 1)
            return _wrap(head) + "." + _wrap(tail)
    ```
    If a joined field has multiple dots (e.g. `order_items.inventory_items.cost`), `rsplit(".", 1)` treats `order_items.inventory_items` as `head`. Because `head` contains a dot, `_wrap()` produces `` `order_items.inventory_items`.cost ``, which is invalid Malloy syntax. It should quote each segment independently: `'.'.join(_wrap(seg) for seg in name.split('.'))`.
  * **NoneType Crash**: If `pick_group_by_dimension()` returns `None`, `"group_by: " + malloy_field_ref(group_by)` raises a `TypeError`.
  * **Dead Code**: The `DynamicContextBuilder` class is completely unused by `step_3`, `mcp_front.py`, and `run_context_pipeline.py`.
  * **Hardcoded Legacy Constants**: Top-level `INPUT_JSON_PATH` and `OUTPUT_RAG_JSON_PATH` point to legacy un-namespaced files.

### 2.6 `step_3_mcp_dual_pathway_server.py` & `mcp_front.py` (The Stage 3 Split)
* **Status**: Functionality is currently split across two files: `step_3_mcp_dual_pathway_server.py` (retriever classes & local tests) and `mcp_front.py` (FastAPI reverse proxy on Cloud Run).
* **Findings**:
  * **Redundant File Split**: `mcp_front.py` was created as an HTTP proxy, but its name doesn't match the `step_3_...` convention. Meanwhile, `step_3_mcp_dual_pathway_server.py` is called a "server", but only runs local tests!
  * **The Context Format Paradox**:
    - `DualPathwayRetriever.malloy_getContext()` in `step_3` builds the **3-Section Executable Context** (Canonical Fields + Explore/Join Hierarchy + Valid Query Template).
    - `get_publisher_context()` in `step_3` returns a flat list of `{results: [{kind, name, source, modelPath, doc}]}` to match the Malloy Publisher protocol.
    - `mcp_front.py` calls `get_publisher_context()`, meaning **the 3-section context and query templates are stripped out and never delivered to the LLM agent!**
  * **Duplicated & Inconsistent Vector Search**:
    - `DualPathwayRetriever._execute_vector_search()` uses a naive word-overlap set intersection.
    - `_chroma_field_items()` uses ChromaDB.
    - They are completely separate, duplicated, and inconsistent.
  * **Performance Bottleneck**: `_chroma_field_items()` instantiates a new `chromadb.PersistentClient(path=CHROMA_DIR)` on **every single request**, introducing 100–300ms of file lock and SQLite connection overhead per call.
  * **Connection Churn in Proxy**: `mcp_front.py` creates a new `httpx.AsyncClient` on every single request instead of reusing a persistent client pool.
  * **Missing Endpoints**: `mcp_front.py` only handles `POST /mcp`. It lacks `GET /healthz` for Cloud Run probes and returns 404 for health checks.

### 2.7 `entrypoint.sh`
* **Status**: Boots both Node and Python, but has process management flaws.
* **Findings**:
  * **PID 1 Signal Swallowing**:
    Line 47: `exec python3 mcp_front.py` replaces the shell process. This destroys the bash `trap cleanup TERM INT EXIT` handler. When Cloud Run sends `SIGTERM` to the container, Python receives it, but the background Node.js process is orphaned and never cleanly shut down.
  * **Lack of Process Supervision**: If the Node process crashes after startup, Python does not detect it and continues running, silently returning 500 errors on every relayed query.

### 2.8 Redundant / Orphaned Data Files
* The folder contains two sets of data files:
  1. `step_1_malloy_raw_extracted.json` & `step_2_malloy_rag_intent_graph.json`: Legacy un-namespaced files from early prototypes.
  2. `step_1_<context_id>_raw_extracted.json`, `step_1_<context_id>_domain_context.json`, `step_2_<context_id>_rag_intent_graph.json`: Active per-context files.
  Keeping both creates confusion about which files are authoritative.

---

## 3. Simplified, Architecture-Traceable File Structure

Instead of creating fragmented micro-files and nested folders, we keep the **simple, intuitive, plain-English naming** that you established:
* **Every step matches its stage** (`step_1`, `step_2`, `step_3`).
* **`mcp_front.py` is eliminated** and unified directly into [`step_3_mcp_dual_pathway_server.py`](file:///home/maxantipev/analytics-malloy-publisher/C_Context/step_3_mcp_dual_pathway_server.py), which is the single server running on Cloud Run.
* **Dead code and redundant legacy files are deleted.**

### 3.1 The Clean, Flat File Layout

```
C_Context/
├── README.md                                      # Core Architecture & Execution Guide
├── ARCHITECTURE_ANALYSIS_AND_PLAN.md              # This analysis and implementation plan
├── requirements.txt                               # Python dependencies (FastAPI, ChromaDB, HTTPX, Uvicorn)
├── entrypoint.sh                                  # Cloud Run process supervisor with SIGTERM handling
│
├── _context_common.py                             # Registry discovery, path resolution & auto-domain derivation
├── run_context_pipeline.py                        # Dev-time / Docker build pipeline driver (Stages 1 -> 2 -> Chroma)
│
├── step_1_compile_malloy.js                       # Stage 1: Node.js AST compiler bridge (@malloydata/malloy)
├── step_1_python_context_retrieval_script.py      # Stage 1: Extraction driver & Markdown inspection generator
│
├── step_2_build_rag_intent_graph.py               # Stage 2: Strategy 3 multi-layer chunk builder (Intent/Entity/Field)
│
├── step_3_mcp_dual_pathway_server.py              # Stage 3: Unified Dual-Pathway MCP Server for Cloud Run
│                                                  #   ├── Path A: In-RAM Fast Router (<0.05ms)
│                                                  #   ├── Path B: ChromaDB Semantic Retriever (Singleton)
│                                                  #   ├── 4 Pillars: 3-Section Context + Publisher Resource
│                                                  #   └── FastAPI Gateway: Intercepts context, relays to Node
│
├── chroma_db/                                     # Stage 2 / Path B: Persistent ChromaDB vector index
│
└── [Generated Data Artifacts]
    ├── step_1_theLook-DEMO__B_Published_Semantic_Layer_raw_extracted.json
    ├── step_1_theLook-DEMO__B_Published_Semantic_Layer_domain_context.json
    ├── step_1_theLook-DEMO__B_Published_Semantic_Layer_inspection.md       <-- Re-enabled (Req 1)
    ├── step_2_theLook-DEMO__B_Published_Semantic_Layer_rag_intent_graph.json
    └── step_2_theLook-DEMO__B_Published_Semantic_Layer_knowledge_map.md      <-- Re-enabled (Req 2)
```

### 3.2 What Files Are Removed / Merged

| File / Component | Action | Rationale |
|---|---|---|
| `mcp_front.py` | **Merged into `step_3_mcp_dual_pathway_server.py`** | Having two files for Stage 3 caused confusion. `step_3_mcp_dual_pathway_server.py` becomes the actual FastAPI server that runs on Cloud Run, housing Path A, Path B, context generation, and Node relay. |
| `step_1_malloy_raw_extracted.json` | **Deleted** | Stale un-namespaced copy. The active file is `step_1_theLook-DEMO__B_Published_Semantic_Layer_raw_extracted.json`. |
| `step_2_malloy_rag_intent_graph.json` | **Deleted** | Stale un-namespaced copy. The active file is `step_2_theLook-DEMO__B_Published_Semantic_Layer_rag_intent_graph.json`. |
| `DynamicContextBuilder` in `step_2` | **Deleted** | Dead code that is never imported or called by any downstream script. |
| Legacy `os.walk` crawler in `step_1` | **Deleted** | Replaced with clean package discovery via `_context_common.py`. |
| Simulated word-overlap search in `step_3` | **Deleted** | Replaced with real ChromaDB semantic search in Path B. |

---

## 4. Key Technical Improvements

### 4.1 Unifying `step_3_mcp_dual_pathway_server.py` (Stage 3 + Cloud Run Server)
Instead of having a separate `mcp_front.py`, [`step_3_mcp_dual_pathway_server.py`](file:///home/maxantipev/analytics-malloy-publisher/C_Context/step_3_mcp_dual_pathway_server.py) is organized into 4 clear sections:
1. **Path A (In-Memory Fast Router)**: Preloads the intent graph into memory at startup. Fast keyword matching in `<0.05ms`.
2. **Path B (ChromaDB Vector Retriever)**: Initializes a persistent `chromadb.PersistentClient` once at startup (singleton) to eliminate per-request connection overhead.
3. **4 Pillars Context Formatter**: Builds both:
   - The Malloy Publisher `{results: [...]}` array for tool compatibility.
   - The **3-Section Executable Context** (Canonical Fields + Explore/Join Hierarchy + Valid Query Template) embedded inside the response so the LLM agent receives the executable blueprint!
4. **FastAPI Application (`app`) & Relay**:
   - Manages a pooled `httpx.AsyncClient` via FastAPI lifespan (`@asynccontextmanager`).
   - `POST /mcp`: Intercepts `malloy_getContext` calls and serves them via Path A / Path B. Transparently relays all other calls (`malloy_executeQuery`, `malloy_compile`, `tools/list`) to the upstream Node publisher on `127.0.0.1:5050`.
   - `GET /healthz`: Health check endpoint for Cloud Run readiness and liveness probes.
   - CLI self-test: If executed with `--test`, runs the local query verification suite without starting the web server.

### 4.2 Hardening `step_1_python_context_retrieval_script.py`
- Remove the legacy `extract_and_inspect_malloy_ontology()` function.
- Standardize on `extract_context(package, fresh=False)`.
- Re-enable generating the human-readable Markdown inspection artifact (`step_1_<context_id>_inspection.md`), fulfilling Requirement 1.

### 4.3 Hardening `step_2_build_rag_intent_graph.py`
- **Fix the Multi-Dot Backtick Bug**:
  ```python
  import re
  IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

  def malloy_field_ref(name: str) -> str:
      if not name:
          return ""
      segments = name.split(".")
      quoted = [s if IDENT_RE.match(s) else f"`{s}`" for s in segments]
      return ".".join(quoted)
  ```
- **Fix `NoneType` group_by crash**: Ensure `build_query_template` handles cases where no dimension candidates exist.
- Remove the dead `DynamicContextBuilder` class.
- Re-enable generating `step_2_<context_id>_knowledge_map.md`, fulfilling Requirement 2.

### 4.4 Hardening `entrypoint.sh` for Cloud Run
Update `entrypoint.sh` to run `step_3_mcp_dual_pathway_server.py` and properly trap signals so Node (port 5050) and Python (port 8080) shut down cleanly together:
```bash
#!/bin/bash
set -m  # Enable job control

NODE_PID=""
PYTHON_PID=""

cleanup() {
  echo "[entrypoint] Received termination signal, gracefully shutting down..."
  [ -n "$NODE_PID" ] && kill -TERM "$NODE_PID" 2>/dev/null || true
  [ -n "$PYTHON_PID" ] && kill -TERM "$PYTHON_PID" 2>/dev/null || true
  wait
  exit 0
}
trap cleanup SIGTERM SIGINT

echo "[entrypoint] Starting Node Malloy Publisher on 127.0.0.1:5050..."
npx @malloy-publisher/server \
  --server_root /app \
  --host 127.0.0.1 \
  --port 4000 \
  --mcp-port 5050 \
  --path /app/B_Published_Semantic_Layer/ \
  --mcp &
NODE_PID=$!

echo "[entrypoint] Waiting for Node MCP to become ready..."
until curl -s -o /dev/null -X POST http://127.0.0.1:5050/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":0,"method":"tools/list","params":{}}'; do
  sleep 0.5
done
echo "[entrypoint] Node MCP is ready!"

echo "[entrypoint] Starting Stage 3 Dual-Pathway MCP Server on PORT=${PORT:-8080}..."
python3 step_3_mcp_dual_pathway_server.py &
PYTHON_PID=$!

wait -n
exit $?
```

---

## 5. Step-by-Step Implementation Roadmap

1. **Step 1: Clean Up Redundant Files**
   - Delete stale un-namespaced files: `step_1_malloy_raw_extracted.json` and `step_2_malloy_rag_intent_graph.json`.
   - Remove `mcp_front.py` after migrating its reverse-proxy capabilities into `step_3_mcp_dual_pathway_server.py`.

2. **Step 2: Harden Stage 1 & Stage 2**
   - In `step_1_python_context_retrieval_script.py`: Remove legacy crawler, generate `step_1_<context>_inspection.md`.
   - In `step_2_build_rag_intent_graph.py`: Fix backtick quoting bug, guard `None` group-by, remove `DynamicContextBuilder`, generate `step_2_<context>_knowledge_map.md`.

3. **Step 3: Consolidate Stage 3 (`step_3_mcp_dual_pathway_server.py`)**
   - Merge Path A, persistent ChromaDB singleton (Path B), the 4-Pillars enriched context formatter, and the FastAPI reverse proxy into `step_3_mcp_dual_pathway_server.py`.
   - Add persistent `httpx.AsyncClient` connection pool and `GET /healthz` endpoint.
   - Support both CLI test mode (`--test`) and production server mode.

4. **Step 4: Update `entrypoint.sh` & Pipeline Runner**
   - Update `entrypoint.sh` to boot `step_3_mcp_dual_pathway_server.py` with dual-process monitoring.
   - Verify `run_context_pipeline.py` executes Stage 1, Stage 2, and Chroma indexing smoothly.

5. **Step 5: Synchronize `C_Context/README.md`**
   - Update `C_Context/README.md` to match the cleaned, unified structure and clear operational workflow.

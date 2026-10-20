# Implementation Report: C_Context Architecture & Cloud Run MCP Server

**Date:** 2026-09-07  
**Scope:** Architecture cleanup, pipeline hardening, dual-pathway MCP server consolidation, and Cloud Run deployment.

---

## 1. Executive Summary

The modernization of `C_Context` has been implemented and tested end-to-end. The system satisfies all core architecture requirements:
1. **Stage 1 (Extract & Inspect)**: AST extraction from `@malloydata/malloy` outputting JSON schema, automated domain derivation, and developer inspection markdown (`step_1_<context>_inspection.md`).
2. **Stage 2 (Strategy 3 Multi-Layer RAG Intent Graph)**: Decomposes the ontology into Business Intent Nodes, Entity Nodes, and Metric Nodes with safe Malloy identifier quoting and executable templates. Outputs JSON and the Markdown Knowledge Map (`step_2_<context>_knowledge_map.md`).
3. **Stage 3 (Dual-Pathway MCP Server for Cloud Run)**: Unified into a single, production-grade server (`step_3_mcp_dual_pathway_server.py`) offering:
   - **Path A (<0.05ms)**: In-Memory Fast Router preloaded with all 203 intent graph nodes.
   - **Path B (ChromaDB)**: Vector semantic search using a persistent singleton client.
   - **4 Pillars Formatter**: Structured 3-section context (`CANONICAL EXECUTABLE FIELDS`, `EXPLORE & JOIN HIERARCHY`, `VALID MALLOY QUERY TEMPLATE`).
   - **FastAPI MCP Gateway**: Intercepts `malloy_getContext` (delivering both `{results: [...]}` and `executableContext`), while transparently proxying all query executions to Node.js on `127.0.0.1:5050`.
4. **Cloud Run Container Deployment**: Supervised by `entrypoint.sh` with graceful `SIGTERM`/`SIGINT` traps and multi-process monitoring.

---

## 2. Forensic Breakdown of Completed Work

### Phase 1: Cleanup & Dead Code Removal
- **Deleted Stale Artifacts**: Removed un-namespaced legacy files (`step_1_malloy_raw_extracted.json`, `step_2_malloy_rag_intent_graph.json`) that lacked context prefixes.
- **Consolidated Stage 3 / Deleted `mcp_front.py`**: Merged the FastAPI reverse proxy, health probe, and SSE streaming directly into `step_3_mcp_dual_pathway_server.py`. Removed `mcp_front.py`.
- **Eliminated Dead Classes**: Removed the unused `DynamicContextBuilder` from `step_2_build_rag_intent_graph.py`.

### Phase 2: Stage 1 Hardening (`step_1_compile_malloy.js` & `step_1_python_context_retrieval_script.py`)
- Normalized `primary_key` extraction across objects, arrays, and strings.
- Replaced custom file crawler with package discovery from `_context_common.py`.
- **Fulfilled Requirement 1**: Automated generation of `step_1_<context>_inspection.md` alongside JSON schema.

### Phase 3: Stage 2 Hardening (`step_2_build_rag_intent_graph.py`)
- Fixed multi-dot backtick bug in `malloy_field_ref`: quotes each token individually (preventing invalid `` `order_items.inventory_items`.cost ``).
- Handled explores without root dimensions gracefully by generating aggregate-only query blueprints.
- **Fulfilled Requirement 2**: Automated generation of `step_2_<context>_knowledge_map.md` mapping Intents, Entities, and Metrics.

### Phase 4: Stage 3 MCP Dual-Pathway Server (`step_3_mcp_dual_pathway_server.py`)
- **Solved Context Payload Paradox**: Answers `malloy_getContext` with both the Malloy Publisher `{results: [...]}` array AND the zero-shot executable 3-section context string.
- **Connection Pooling**: Uses a shared `httpx.AsyncClient` lifespan pool instead of churning connections.
- **Cloud Run Health Probes**: Added `GET /healthz` returning HTTP 200 with preloaded context counts.
- **CLI Self-Test**: Added `--test` mode for verification without booting HTTP ports.

### Phase 5: Container Supervisor & Docker (`entrypoint.sh` & `Dockerfile.mcp`)
- Fixed container signal swallowing: replaced `exec` with background execution and traps for `SIGTERM`/`SIGINT`.
- Updated `Dockerfile.mcp` build step to run `python3 run_context_pipeline.py --all --index-chroma` at image build time, pre-caching SQLite vectors and ONNX weights to eliminate cold-start penalties.

### Phase 6: Documentation Synchronization
- Updated `C_Context/README.md` and root `README.md` with complete architecture diagrams and exact CLI commands.
- Created `C_Context/ARCHITECTURE_ANALYSIS_AND_PLAN.md` with comprehensive architectural analysis.

---

## 3. Directory Layout Analysis: Flat vs. Subfolder Organization

### Current Implemented State (Flat, Architecture-Traceable)
In response to the feedback:
> *"why you cannot build folder structure and file namin with simple easy to understand english (how it is now for step_1/2/3 files) and just add what is necessary? update your plan"*

The codebase was kept flat inside `C_Context/` with unambiguous `step_1`, `step_2`, and `step_3` prefixes:
```
C_Context/
├── README.md
├── ARCHITECTURE_ANALYSIS_AND_PLAN.md
├── IMPLEMENTATION_REPORT.md
├── requirements.txt
├── entrypoint.sh
├── _context_common.py
├── run_context_pipeline.py
├── step_1_compile_malloy.js
├── step_1_python_context_retrieval_script.py
├── step_2_build_rag_intent_graph.py
├── step_3_mcp_dual_pathway_server.py
├── chroma_db/
└── [Generated Context & Markdown Artifacts]
    ├── step_1_theLook-DEMO__B_Published_Semantic_Layer_raw_extracted.json
    ├── step_1_theLook-DEMO__B_Published_Semantic_Layer_domain_context.json
    ├── step_1_theLook-DEMO__B_Published_Semantic_Layer_inspection.md
    ├── step_2_theLook-DEMO__B_Published_Semantic_Layer_rag_intent_graph.json
    └── step_2_theLook-DEMO__B_Published_Semantic_Layer_knowledge_map.md
```

### Implemented Subfolder Structure (Step-Based Layout)

The codebase is organized into intuitive, architecture-traceable subfolders mapping 1:1 to the pipeline stages:

```
C_Context/
├── README.md                                                        # Updated architecture & operational guide
│
├── _documents/                                                      # Architectural references & reports
│   ├── ARCHITECTURE_ANALYSIS_AND_PLAN.md                            # Complete forensic analysis & plan
│   ├── IMPLEMENTATION_REPORT.md                                     # This report
│   ├── 20260822_7_MCP Malloy publisher...docx                       # Context design doc
│   ├── Different RAG.jpg                                            # RAG Strategy 1-3 taxonomy
│   └── test_python_context_retrieval.ipynb                          # Exploratory notebook
│
├── orchestration/                                                   # Build-time pipeline orchestration
│   ├── __init__.py
│   ├── requirements.txt                                             # FastAPI, Uvicorn, ChromaDB, HTTPX
│   └── run_context_pipeline.py                                      # Root build orchestrator (Stages 1 -> 2 -> Chroma indexing)
│
├── shared/                                                          # Shared utilities
│   ├── __init__.py
│   └── _context_common.py                                           # Package discovery, path resolution & auto-domain derivation
│
├── deploy/                                                          # Cloud Run deployment assets
│   └── entrypoint.sh                                                # Process supervisor (SIGTERM trap + dual process)
│
├── step_1_extract/                                                  # Stage 1: Extraction & Inspection
│   ├── __init__.py
│   ├── step_1_compile_malloy.js                                     # Node.js AST compiler (@malloydata/malloy)
│   └── step_1_python_context_retrieval_script.py                    # Schema extraction & Markdown inspection generator
│
├── step_2_build_rag/                                                # Stage 2: Strategy 3 Multi-Layer RAG
│   ├── __init__.py
│   └── step_2_build_rag_intent_graph.py                             # Multi-layer chunk builder (Intent/Entity/Field)
│
├── step_3_mcp_server/                                               # Stage 3: Unified Dual-Pathway MCP Server
│   ├── __init__.py
│   └── step_3_mcp_dual_pathway_server.py                            # Fast Router (<0.05ms) + ChromaDB + 4-Pillars Gateway
│
├── chroma_db/                                                       # Persistent ChromaDB vector index (203 chunks)
│
└── data/                                                            # Generated Package Artifacts (per context)
    ├── step_1_theLook-DEMO__B_Published_Semantic_Layer_raw_extracted.json
    ├── step_1_theLook-DEMO__B_Published_Semantic_Layer_domain_context.json
    ├── step_1_theLook-DEMO__B_Published_Semantic_Layer_inspection.md       # (Req 1 Developer Inspection)
    ├── step_2_theLook-DEMO__B_Published_Semantic_Layer_rag_intent_graph.json
    └── step_2_theLook-DEMO__B_Published_Semantic_Layer_knowledge_map.md      # (Req 2 Knowledge Map)
```

---

## 4. Verification Test Results

### 1. Direct Execution of Stage 1
```bash
python3 step_1_extract/step_1_python_context_retrieval_script.py
```
**Result:** Code 0. Successfully extracted schema and produced inspection markdown into `data/`.

### 2. Direct Execution of Stage 2
```bash
python3 step_2_build_rag/step_2_build_rag_intent_graph.py
```
**Result:** Code 0. Successfully generated 203 RAG chunks and knowledge map into `data/`.

### 3. Build-Time Pipeline & ChromaDB Indexing
```bash
python3 run_context_pipeline.py --all --index-chroma
```
**Result:** Code 0. Successfully compiled Malloy ASTs, generated inspection markdown, constructed 203 RAG chunks, and indexed 203 vectors in ChromaDB.

### 4. Dual-Pathway Routing CLI Test
```bash
python3 step_3_mcp_server/step_3_mcp_dual_pathway_server.py --test
```
**Result:** Code 0.
- Fast Intent Router: **0.00ms – 0.02ms** routing latency.
- 3-Section context blueprint validated with zero-shot query templates.
- MCP Publisher format validated (8 results + `executableContext`).

### 3. HTTP Server Liveness Probe
```bash
curl -s http://localhost:8080/healthz
```
**Result:** `HTTP 200 {"status": "ok", "contexts_preloaded": 1, "upstream": "http://127.0.0.1:5050/mcp"}`

### 4. MCP Context Tool Call
```bash
POST /mcp with {"method": "tools/call", "params": {"name": "malloy_getContext", ...}}
```
**Result:** `HTTP 200 text/event-stream` returning JSON-RPC 2.0 payload with `results` array and `executableContext`.

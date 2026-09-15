"""
================================================================================
MALLOY CONTEXT / RAG PIPELINE ORCHESTRATOR (dev-time, multi-package)
================================================================================

Drives the 3-stage context pipeline for one or every published Malloy package
registered in `publisher.config.json`:

    Stage 1  step_1_python_context_retrieval_script.py
             compile a package's published explores -> step_1_<ctx>_raw_extracted.json
             (+ step_1_<ctx>_domain_context.json, auto-derived then editable)
    Stage 2  step_2_build_rag_intent_graph.py
             ontology + domain context -> step_2_<ctx>_rag_intent_graph.json
    Stage 3  step_3_mcp_dual_pathway_server.py
             in-memory router pre-loaded from the per-context intent graph

This is purely a *build-time* convenience that automates running the three steps
in order for each package.  It is not a runtime service and does not ship in the
Docker/MCP image; it only makes sure the per-context JSON artifacts are fresh.

Usage:
    python3 run_context_pipeline.py --all              # all discovered packages
    python3 run_context_pipeline.py --context <id>     # one package
    python3 run_context_pipeline.py --list             # print discovered packages
    python3 run_context_pipeline.py --fresh            # force domain regeneration
================================================================================
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
C_CONTEXT_DIR = os.path.dirname(SCRIPT_DIR)
BASE_DIR = os.path.dirname(C_CONTEXT_DIR)

# ChromaDB library location for the RAG index (shared with step_3_mcp_dual_pathway_server).
CHROMA_DIR = os.environ.get("CHROMA_DIR", os.path.join(C_CONTEXT_DIR, "chroma_db"))
CHROMA_COLLECTION = "malloy_subgraphs"

# Ensure imports of sibling subfolders and shared/ resolve.
if C_CONTEXT_DIR not in sys.path:
    sys.path.insert(0, C_CONTEXT_DIR)
shared_dir = os.path.join(C_CONTEXT_DIR, "shared")
if shared_dir not in sys.path:
    sys.path.insert(0, shared_dir)


def _load_packages(context_id, config_path):
    from _context_common import iter_packages, find_package
    if context_id:
        pkg = find_package(context_id, config_path=config_path)
        if pkg is None:
            print(f"❌ Unknown context id '{context_id}'. Available contexts:",
                  file=sys.stderr)
            for p in iter_packages(config_path=config_path):
                print(f"   - {p['context_id']}", file=sys.stderr)
            sys.exit(1)
        return [pkg]
    return iter_packages(config_path=config_path)


def run_one_package(package: dict, fresh: bool) -> dict:
    """Run Stage 1 -> Stage 2 -> Stage 3 for a single package context."""
    import step_1_extract.step_1_python_context_retrieval_script as step1
    import step_2_build_rag.step_2_build_rag_intent_graph as step2
    import step_3_mcp_server.step_3_mcp_dual_pathway_server as step3
    from _context_common import raw_path, domain_path, rag_path, load_json

    print("\n" + "=" * 72)
    print(f"CONTEXT: {package['context_id']}")
    print(f"  package:  {package['package_name']}  (env: {package['env_name']})")
    print(f"  explores: {[os.path.relpath(f, BASE_DIR) for f in package['explore_files']]}")
    print("=" * 72)

    # ---- Stage 1: extract ontology + ensure domain context ----
    step1.extract_context(package, fresh=fresh)
    raw = raw_path(package)
    if not os.path.exists(raw):
        print(f"❌ Stage 1 produced no schema for '{package['context_id']}'.", file=sys.stderr)
        return {"context_id": package["context_id"], "status": "failed"}

    # ---- Stage 2: build the RAG intent graph ----
    with open(raw, "r", encoding="utf-8") as f:
        ontology = json.load(f)
    rag_file = step2.build_rag_for_package(package, ontology)

    # ---- Stage 3: validate the router pre-load for this context ----
    domain = load_json(domain_path(package)) or {}
    retriever = step3.DualPathwayRetriever(
        rag_file,
        keyword_mappings=domain.get("keyword_mappings"),
        fallback_explore=domain.get("fallback_explore"),
        env_name=package.get("env_name"),
        package_name=package.get("package_name"),
    )
    summary = {
        "context_id": package["context_id"],
        "status": "ok",
        "raw": raw,
        "domain": domain_path(package),
        "rag": rag_file,
        "router": retriever.fast_router,
    }
    return summary


def _safe_metadata(meta: dict) -> dict:
    """ChromaDB metadata only accepts simple values (number/bool/text)."""
    out = {}
    for key, value in (meta or {}).items():
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = value
        elif isinstance(value, (int, float)):
            out[key] = value
        elif isinstance(value, str):
            out[key] = value[:2000]
        elif isinstance(value, (list, tuple)):
            out[key] = ", ".join(str(v) for v in value)[:2000]
        else:
            out[key] = str(value)[:2000]
    return out


def index_chroma(packages: list | None = None, config_path: str = None):
    """Ingest every context's Stage-2 graph into a local ChromaDB library.

    This is the 'build_graph_index' step of the RAG design: it turns the
    step_2_<ctx>_rag_intent_graph.json chunks into searchable vectors so the
    front server can answer context questions by meaning (Path B).
    """
    import chromadb
    from _context_common import iter_packages, rag_path

    packages = packages if packages is not None else iter_packages(config_path=config_path)
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    try:
        client.delete_collection(CHROMA_COLLECTION)
    except Exception:
        pass
    collection = client.get_or_create_collection(CHROMA_COLLECTION)

    total = 0
    for package in packages:
        path = rag_path(package)
        if not os.path.exists(path):
            print(f"ℹ️ No Stage-2 file for {package['context_id']}: {path}")
            continue
        with open(path, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        # Ensure unique IDs for ChromaDB upsert
        seen_ids = set()
        unique_ids = []
        unique_docs = []
        unique_metas = []
        for c in chunks:
            cid = f"{package['context_id']}::{c.get('id')}"
            if cid not in seen_ids:
                seen_ids.add(cid)
                unique_ids.append(cid)
                unique_docs.append(c.get("text") or "")
                unique_metas.append(_safe_metadata(dict((c.get("metadata") or {}), context=package["context_id"])))
        collection.upsert(ids=unique_ids, documents=unique_docs, metadatas=unique_metas)
        total += len(unique_ids)
        print(f"✅ Indexed {len(unique_ids)} chunks for context '{package['context_id']}'")

    print(f"\nTotal chunks in ChromaDB '{CHROMA_COLLECTION}': {total}")
    return total


def prune_orphaned_artifacts(active_packages: list):
    """Dynamically removes context data artifacts for packages no longer in publisher.config.json."""
    active_ids = {p["context_id"] for p in active_packages}
    data_dir = os.path.join(C_CONTEXT_DIR, "data")
    if not os.path.isdir(data_dir):
        return
    for fname in os.listdir(data_dir):
        if not fname.endswith(".json") or not fname.startswith("step_"):
            continue
        if not any(ctx_id in fname for ctx_id in active_ids):
            target = os.path.join(data_dir, fname)
            print(f"🧹 Pruning orphaned artifact: {fname}")
            try:
                os.remove(target)
            except OSError as e:
                print(f"⚠️ Could not remove {target}: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Malloy context/RAG pipeline (per package).")
    parser.add_argument("--all", action="store_true", help="run all discovered packages")
    parser.add_argument("--context", help="run a single context id")
    parser.add_argument("--list", action="store_true", help="list discovered packages and exit")
    parser.add_argument("--fresh", action="store_true",
                        help="force re-generation of domain context files")
    parser.add_argument("--index-chroma", action="store_true",
                        help="(re)build the ChromaDB RAG index from Stage-2 graphs")
    from _context_common import iter_packages, PUBLISHER_CONFIG_PATH

    parser.add_argument("--config", default=PUBLISHER_CONFIG_PATH,
                        help="path to publisher.config.json")
    args = parser.parse_args()

    if args.list:
        print("Discovered packages:")
        for p in iter_packages(config_path=args.config):
            print(f"  - {p['context_id']}  ->  {p['location_dir']} "
                  f"({len(p['explore_files'])} explore file(s))")
        return

    if not args.all and not args.context and not args.index_chroma:
        parser.error("Provide --all or --context <id> (or --list).")

    all_discovered = list(iter_packages(config_path=args.config))
    prune_orphaned_artifacts(all_discovered)

    packages = _load_packages(args.context, args.config)
    if not packages:
        print("❌ No publishable packages found in publisher.config.json.", file=sys.stderr)
        sys.exit(1)

    # ---- Task A: whole-package compile validation (fail the build on any broken .malloy file) ----
    import step_1_extract.step_1_python_context_retrieval_script as step1
    print("")
    print("=" * 72)
    print("VALIDATING PACKAGES (whole-package compile check)")
    print("=" * 72)
    all_ok = True
    for package in packages:
        failures = step1.validate_package(package)
        if failures:
            all_ok = False
            for rel, err in failures:
                print(f"Compile error in {rel}:", file=sys.stderr)
                print(f"   {err}", file=sys.stderr)
        else:
            print(f"OK {package['context_id']}: all .malloy files compile")
    if not all_ok:
        print("Package validation failed - fix the broken .malloy file(s) above.", file=sys.stderr)
        sys.exit(1)

    # Run Stage 1 & Stage 2 for the requested packages
    if args.all or args.context or not args.index_chroma:
        results = []
        for package in packages:
            results.append(run_one_package(package, fresh=args.fresh))

        print("\n" + "=" * 72)
        print("PIPELINE SUMMARY")
        print("=" * 72)
        for r in results:
            print(f"  [{'OK' if r['status'] == 'ok' else 'FAILED'}] {r['context_id']}")

    # Ingest into ChromaDB if requested
    if args.index_chroma:
        index_chroma(packages, config_path=args.config)


if __name__ == "__main__":
    main()

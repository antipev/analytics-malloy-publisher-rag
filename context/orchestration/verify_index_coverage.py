"""
================================================================================
RAG INDEX COVERAGE VERIFIER (build-time / CI / runtime gate, read-only)
================================================================================

`publisher.config.json` decides which Malloy packages are *served*.  The Stage-2
artifact `step_2_<context_id>_rag_intent_graph.json` decides which packages
actually have a RAG context.  When a served package has no Stage-2 graph,
malloy_getContext silently relays the request to the Node Publisher, which
answers with the raw source-level stub (fields only, no 3-section context).
That silent relay is how `jaffle_shop` / `comics` lost their money measures with
no build, no log line and no smoke test complaining.

This script makes that gap loud.  It never writes anything.

Usage:
    python3 verify_index_coverage.py
    python3 verify_index_coverage.py --config workspace/publisher.config.json
    python3 verify_index_coverage.py --require jaffle_shop:Total_Revenue
    python3 verify_index_coverage.py --json
    python3 verify_index_coverage.py --soft        # report only, exit 0

Exit codes:
    0  every served package has a usable Stage-2 graph
    1  at least one served package is missing (or misses a required measure)
================================================================================
"""

import argparse
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
C_CONTEXT_DIR = os.path.dirname(SCRIPT_DIR)
SHARED_DIR = os.path.join(C_CONTEXT_DIR, "shared")
for _path in (C_CONTEXT_DIR, SHARED_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from _context_common import (  # noqa: E402
    PUBLISHER_CONFIG_PATH,
    iter_packages,
    raw_path,
    domain_path,
    rag_path,
    load_json,
)


def _norm(name) -> str:
    """Compare measure names ignoring case, spaces, dots and underscores."""
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def collect_measures(chunks: list) -> dict:
    """Every measure/metric name a Stage-2 graph exposes, keyed by normalized form.

    Reads the field-level nodes (`field_name`) and the per-intent roll-up
    (`canonical_metrics`), which is where qualified names such as
    `order_items.Total_Revenue` live.
    """
    measures = {}
    for chunk in chunks or []:
        if not isinstance(chunk, dict):
            continue
        meta = chunk.get("metadata") or {}
        chunk_type = str(meta.get("chunk_type") or "")
        is_metric_chunk = ("metric" in chunk_type) or ("measure" in chunk_type)
        candidates = []
        if is_metric_chunk:
            candidates.append(meta.get("field_name"))
        else:
            candidates.extend(meta.get("canonical_metrics") or [])
        for name in candidates:
            if isinstance(name, str) and name.strip():
                measures.setdefault(_norm(name), name)
    return measures


def check_package(package: dict, required: dict) -> dict:
    """Assess one served package's RAG readiness."""
    graph_file = rag_path(package)
    present = os.path.exists(graph_file)
    chunks = (load_json(graph_file) or []) if present else []
    measures = collect_measures(chunks) if isinstance(chunks, list) else {}
    wanted = list(required.get(package["package_name"], [])) + list(
        required.get(package["context_id"], []))
    missing_measures = [w for w in wanted if _norm(w) not in measures]

    problems = []
    if not present:
        problems.append(f"missing Stage-2 graph ({os.path.basename(graph_file)})")
    elif not isinstance(chunks, list) or not chunks:
        problems.append("Stage-2 graph is empty or unreadable")
    if missing_measures:
        problems.append("missing required measure(s): " + ", ".join(missing_measures))

    warnings = []
    if present and not os.path.exists(raw_path(package)):
        warnings.append("Stage-1 raw extraction missing")
    if not os.path.exists(domain_path(package)):
        warnings.append("domain context missing (Path A routing quality degraded)")

    return {
        "context_id": package["context_id"],
        "env_name": package["env_name"],
        "package_name": package["package_name"],
        "graph_file": os.path.basename(graph_file),
        "graph_present": present,
        "chunks": len(chunks) if isinstance(chunks, list) else 0,
        "measures": len(measures),
        "required": wanted,
        "missing_measures": missing_measures,
        "problems": problems,
        "warnings": warnings,
        "ok": not problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that every served Malloy package has a Stage-2 RAG graph.")
    parser.add_argument("--config", default=PUBLISHER_CONFIG_PATH,
                        help="path to publisher.config.json")
    parser.add_argument("--require", action="append", default=[], metavar="PKG:MEASURE",
                        help="require a measure in that package's graph; repeatable, "
                             "e.g. --require jaffle_shop:Total_Revenue")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="emit machine-readable JSON")
    parser.add_argument("--soft", action="store_true",
                        help="report problems but still exit 0 (warn-only)")
    parser.add_argument("--quiet", action="store_true", help="only print failures")
    args = parser.parse_args()

    required = {}
    for spec in args.require:
        pkg, _, measure = spec.partition(":")
        if not pkg or not measure:
            parser.error(f"bad --require value '{spec}' (expected PKG:MEASURE)")
        required.setdefault(pkg, []).append(measure)

    packages = list(iter_packages(config_path=args.config))
    if not packages:
        print(f"❌ No publishable packages discovered from {args.config}", file=sys.stderr)
        return 1

    results = [check_package(p, required) for p in packages]
    failures = [r for r in results if not r["ok"]]

    if args.as_json:
        print(json.dumps({"config": os.path.abspath(args.config),
                          "results": results,
                          "ok": not failures}, indent=2))
        return 0 if (not failures or args.soft) else 1

    print("=" * 78)
    print(f"RAG INDEX COVERAGE  ({os.path.abspath(args.config)})")
    print("=" * 78)
    for r in results:
        if r["ok"]:
            if not args.quiet:
                print(f"✅ {r['context_id']:<38} {r['chunks']:>5} chunks  {r['measures']:>4} measures")
        else:
            print(f"❌ {r['context_id']:<38} -> {'; '.join(r['problems'])}", file=sys.stderr)
        for warning in r["warnings"]:
            if not args.quiet:
                print(f"   ⚠️  {r['context_id']}: {warning}")

    print("-" * 78)
    print(f"{len(results) - len(failures)}/{len(results)} served package(s) have a RAG context.")
    if failures and not args.quiet:
        print("Fix with: python3 context/orchestration/run_context_pipeline.py "
              "--all --index-chroma --config workspace/publisher.config.json", file=sys.stderr)

    if failures and args.soft:
        print("⚠️ --soft: reporting only, not failing.", file=sys.stderr)
        return 0
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
================================================================================
DEPLOYED-SERVICE RAG COVERAGE CHECK (stdlib only, safe to run anywhere)
================================================================================

`/api/v0/status` proves the Node Publisher *loaded* a package.  It says nothing
about whether malloy_getContext can answer from a RAG graph.  This script asks
the real question: call malloy_getContext for every package in
publisher.config.json and require a non-empty `executableContext` back.

When a package has no Stage-2 graph the Python MCP gateway relays the call to
the Node Publisher, which returns a raw source stub.  Depending on the upstream
build that stub is empty or only a handful of key fields, so we also assert a
minimum payload size (and any --require measures you pass).

Usage:
    python3 scripts/verify_context_coverage.py --base-url https://...
    python3 scripts/verify_context_coverage.py --base-url https://... \
        --require jaffle_shop:Total_Revenue --require jaffle_shop:Gross_Margin
    python3 scripts/verify_context_coverage.py --base-url https://... --soft

Exit codes: 0 = every served package answers with a real 3-section context.
================================================================================
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

# A genuine 3-section context is kilobytes wide; the relayed stub is tiny.
MIN_CONTEXT_CHARS = int(os.environ.get("MIN_CONTEXT_CHARS", "500"))


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def discover_packages(config_path: str) -> list:
    """Same discovery rules as context/shared/_context_common.iter_packages()."""
    if not os.path.exists(config_path):
        sys.exit(f"config not found: {config_path}")
    with open(config_path, encoding="utf-8") as handle:
        cfg = json.load(handle)
    cfg_dir = os.path.dirname(os.path.abspath(config_path))
    root_dir = os.path.dirname(cfg_dir)
    packages = []
    for env in cfg.get("environments", []):
        env_name = env.get("name", "environment")
        for pkg in env.get("packages", []):
            location = pkg.get("location", "")
            candidates = [location] if os.path.isabs(location) else [
                os.path.normpath(os.path.join(cfg_dir, location)),
                os.path.normpath(os.path.join(root_dir, location)),
            ]
            if not any(os.path.isdir(c) for c in candidates):
                continue
            packages.append({"env": env_name, "package": pkg.get("name", "")})
    return packages


def _parse_body(raw: str) -> dict:
    """Accept plain JSON or an SSE frame (`event: message` / `data: {...}`)."""
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    payload = None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            chunk = line[5:].strip()
            if chunk and chunk != "[DONE]":
                try:
                    payload = json.loads(chunk)
                except Exception:
                    continue
    if payload is None:
        raise ValueError(f"unparseable response: {raw[:300]}")
    return payload


def _walk_for(obj, key: str):
    """Depth-first search for the first string value under `key`."""
    if isinstance(obj, dict):
        value = obj.get(key)
        if isinstance(value, str):
            return value
        for child in obj.values():
            found = _walk_for(child, key)
            if found is not None:
                return found
    elif isinstance(obj, (list, tuple)):
        for child in obj:
            found = _walk_for(child, key)
            if found is not None:
                return found
    elif isinstance(obj, str) and obj.strip()[:1] in "{[":
        try:
            return _walk_for(json.loads(obj), key)
        except Exception:
            return None
    return None


def call_get_context(base_url: str, env: str, package: str, query: str, timeout: float) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "malloy_getContext",
            "arguments": {"environmentName": env, "packageName": package, "query": query},
        },
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/mcp",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return _parse_body(response.read().decode("utf-8", "replace"))


def check(base_url: str, env: str, package: str, query: str, required: list,
          timeout: float) -> dict:
    result = {"env": env, "package": package, "ok": False, "chars": 0,
              "detail": "", "missing_measures": []}
    try:
        doc = call_get_context(base_url, env, package, query, timeout)
    except urllib.error.HTTPError as exc:
        result["detail"] = f"HTTP {exc.code} {exc.reason}"
        return result
    except Exception as exc:  # network, parse, timeout
        result["detail"] = f"{type(exc).__name__}: {exc}"
        return result

    if isinstance(doc, dict) and doc.get("error"):
        result["detail"] = "JSON-RPC error: " + json.dumps(doc["error"])[:200]
        return result

    text = _walk_for(doc, "executableContext") or ""
    result["chars"] = len(text)
    if not text.strip():
        result["detail"] = "empty executableContext (package has no RAG graph)"
        return result
    if len(text) < MIN_CONTEXT_CHARS:
        result["detail"] = f"executableContext suspiciously small ({len(text)} chars)"
        return result

    haystack = _norm(text)
    result["missing_measures"] = [m for m in required if _norm(m) not in haystack]
    if result["missing_measures"]:
        result["detail"] = "executableContext lacks: " + ", ".join(result["missing_measures"])
        return result

    result["ok"] = True
    result["detail"] = "3-section context returned"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Assert malloy_getContext returns real context "
                                                 "for every served package.")
    parser.add_argument("--base-url", default=os.environ.get("SERVICE_URL", ""),
                        help="deployed service URL (or $SERVICE_URL)")
    parser.add_argument("--config", default="workspace/publisher.config.json")
    parser.add_argument("--query", default="gross margin by month",
                        help="probe question sent to malloy_getContext")
    parser.add_argument("--require", action="append", default=[], metavar="PKG:MEASURE",
                        help="measure that must appear in that package's context (repeatable)")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--soft", action="store_true", help="report only, exit 0")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    if not args.base_url:
        parser.error("--base-url is required (or set SERVICE_URL)")

    required = {}
    for spec in args.require:
        pkg, _, measure = spec.partition(":")
        if not pkg or not measure:
            parser.error(f"bad --require value '{spec}' (expected PKG:MEASURE)")
        required.setdefault(pkg, []).append(measure)

    packages = discover_packages(args.config)
    if not packages:
        sys.exit(f"no served packages discovered from {args.config}")

    results = [check(args.base_url, p["env"], p["package"], args.query,
                     required.get(p["package"], []), args.timeout) for p in packages]
    failures = [r for r in results if not r["ok"]]

    if args.as_json:
        print(json.dumps({"base_url": args.base_url, "ok": not failures,
                          "results": results}, indent=2))
        return 0 if (not failures or args.soft) else 1

    print("=" * 78)
    print(f"DEPLOYED RAG CONTEXT COVERAGE  ({args.base_url})")
    print("=" * 78)
    for r in results:
        mark = "\u2705" if r["ok"] else "\u274c"
        print(f"{mark}  {r['env']}/{r['package']:<22} {r['chars']:>7} chars  {r['detail']}")
    print("-" * 78)
    print(f"{len(results) - len(failures)}/{len(results)} served package(s) return a real RAG context.")
    if failures and args.soft:
        print("SOFT MODE: reporting only, not failing the deploy.", file=sys.stderr)
        return 0
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

"""
================================================================================
TASK 1: MALLOY ONTOLOGY EXTRACTION & CONTEXT INSPECTION
================================================================================

OBJECTIVE:
- Discover all .malloy semantic files across directories using dynamic path resolution.
- Delegate AST compilation and lineage resolution to `step_1_compile_malloy.js`.
- Pass proper NODE_PATH environment variables to ensure node modules resolve properly.
- Output context for developer inspection and downstream system use to `C_Context`.
================================================================================
"""

import json
import os
import subprocess
import sys

# Dynamically resolve directories (SCRIPT_DIR is step_1_extract, CONTEXT_DIR is context)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONTEXT_DIR = os.path.dirname(SCRIPT_DIR)
C_CONTEXT_DIR = CONTEXT_DIR
BASE_DIR = os.path.dirname(CONTEXT_DIR)

if CONTEXT_DIR not in sys.path:
    sys.path.insert(0, CONTEXT_DIR)
shared_dir = os.path.join(CONTEXT_DIR, "shared")
if shared_dir not in sys.path:
    sys.path.insert(0, shared_dir)

from _context_common import PUBLISHER_CONFIG_PATH

# Path to the Node.js compiler script inside the same step_1_extract folder
NODE_COMPILER_SCRIPT = os.path.join(SCRIPT_DIR, "step_1_compile_malloy.js")


def compile_malloy_file(filepath: str, config_path: str = PUBLISHER_CONFIG_PATH) -> dict:
    """Executes step_1_compile_malloy.js via Node with NODE_PATH resolving node_modules."""
    # Ensure Node knows where node_modules is located (checks C_Context/ first, then root)
    env = os.environ.copy()
    node_modules_candidates = [
        os.path.join(C_CONTEXT_DIR, "node_modules"),
        os.path.join(BASE_DIR, "node_modules"),
        os.path.join(SCRIPT_DIR, "node_modules"),
    ]
    node_modules_path = next((p for p in node_modules_candidates if os.path.exists(p)), os.path.join(C_CONTEXT_DIR, "node_modules"))
    
    if "NODE_PATH" in env:
        env["NODE_PATH"] = f"{node_modules_path}:{env['NODE_PATH']}"
    else:
        env["NODE_PATH"] = node_modules_path

    node_bin = "node"
    try:
        ver = subprocess.run([node_bin, "-v"], capture_output=True, text=True).stdout.strip()
        major = int(ver.lstrip("v").split(".")[0]) if ver else 0
        if major < 18:
            import glob
            nvm_candidates = sorted(
                glob.glob('/home/*/.nvm/versions/node/*/bin/node') +
                glob.glob(os.path.expanduser('~/.nvm/versions/node/*/bin/node')),
                reverse=True
            )
            if nvm_candidates:
                node_bin = nvm_candidates[0]
    except Exception:
        pass

    cmd = [node_bin, NODE_COMPILER_SCRIPT, filepath, config_path]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=BASE_DIR)

    if result.returncode != 0:
        print(f"⚠️ Compilation error for '{filepath}':\n{result.stderr.strip()}", file=sys.stderr)
        return {}

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"⚠️ Failed to parse compiler JSON output for '{filepath}'", file=sys.stderr)
        return {}


def validate_package(package: dict, config_path: str = PUBLISHER_CONFIG_PATH) -> list:
    """Compile EVERY .malloy file in a package; return [(file, error)] for any failure.

    The Publisher compiles the whole package at runtime, so a single broken file
    (e.g. an ad-hoc query referencing an undefined object) blocks all queries.
    This lets the build fail early on such files instead of at deploy time.
    """
    failures = []
    location_dir = package.get("location_dir")
    if not location_dir or not os.path.isdir(location_dir):
        return failures

    env = os.environ.copy()
    node_modules_candidates = [
        os.path.join(C_CONTEXT_DIR, "node_modules"),
        os.path.join(BASE_DIR, "node_modules"),
        os.path.join(SCRIPT_DIR, "node_modules"),
    ]
    node_modules_path = next((p for p in node_modules_candidates if os.path.exists(p)), os.path.join(C_CONTEXT_DIR, "node_modules"))
    if "NODE_PATH" in env:
        env["NODE_PATH"] = f"{node_modules_path}:{env['NODE_PATH']}"
    else:
        env["NODE_PATH"] = node_modules_path
    node_bin = "node"
    try:
        ver = subprocess.run([node_bin, "-v"], capture_output=True, text=True).stdout.strip()
        major = int(ver.lstrip("v").split(".")[0]) if ver else 0
        if major < 18:
            import glob
            nvm_candidates = sorted(
                glob.glob('/home/*/.nvm/versions/node/*/bin/node') +
                glob.glob(os.path.expanduser('~/.nvm/versions/node/*/bin/node')),
                reverse=True
            )
            if nvm_candidates:
                node_bin = nvm_candidates[0]
    except Exception:
        pass

    for root, _dirs, files in os.walk(location_dir):
        for name in sorted(files):
            if not name.endswith(".malloy"):
                continue
            path = os.path.join(root, name)
            result = subprocess.run([node_bin, NODE_COMPILER_SCRIPT, path, config_path],
                                    capture_output=True, text=True, env=env, cwd=BASE_DIR)
            if result.returncode != 0:
                err = (result.stderr or "").strip()
                try:
                    err = json.loads(err).get("error", err)
                except Exception:
                    pass
                failures.append((os.path.relpath(path, BASE_DIR), err))
    return failures



def generate_inspection_markdown(extracted_models: dict) -> str:
    """
    Builds clean, structured Markdown inspection context from extracted models (Requirement 1).
    """
    markdown_lines = [
        "# Malloy Semantic Ontology Inspection Context",
        "> Auto-generated AST extraction for developer inspection and AI validation.",
        "",
    ]

    for source_name, details in extracted_models.items():
        is_published = details.get("is_published_explore", False)
        rel_file_path = details.get("file", "")
        pub_tag = " `[PUBLISHED EXPLORE]`" if is_published else " `[BASE SOURCE]`"
        pk_str = f" | **Primary Key:** `{details['primary_key']}`" if details.get("primary_key") else ""
        dialect = details.get("dialect", "duckdb")

        markdown_lines.append(f"## EXPLORE: `{source_name}`{pub_tag}")
        markdown_lines.append(f"**File:** `{rel_file_path}` | **Dialect:** `{dialect}`{pk_str}\n")

        direct_fields = details.get("direct_fields", [])
        if direct_fields:
            markdown_lines.append(f"### Direct Fields (Root: `{source_name}`)")
            markdown_lines.append("| Field Name | Type | Category | Description |")
            markdown_lines.append("|---|---|---|---|")
            for field in direct_fields:
                fname = field.get("name")
                ftype = field.get("type")
                category = field.get("category", field.get("expressionType", "dimension"))
                comment = field.get("comment", "").replace("|", "\\|").replace("\n", " ").strip()
                markdown_lines.append(f"| `{fname}` | `{ftype}` | `{category}` | {comment} |")
            markdown_lines.append("")

        joined_entities = details.get("joined_entities", {})
        if joined_entities:
            for entity_name, entity_info in joined_entities.items():
                markdown_lines.append(f"### Joined Entity: `{entity_name}`")
                markdown_lines.append("| Field Name | Type | Category | Description |")
                markdown_lines.append("|---|---|---|---|")
                for field in entity_info.get("fields", []):
                    fname = field.get("name")
                    ftype = field.get("type")
                    category = field.get("category", field.get("expressionType", "dimension"))
                    comment = field.get("comment", "").replace("|", "\\|").replace("\n", " ").strip()
                    markdown_lines.append(f"| `{fname}` | `{ftype}` | `{category}` | {comment} |")
                markdown_lines.append("")

        markdown_lines.append("---\n")

    return "\n".join(markdown_lines)


def extract_and_inspect_malloy_ontology(explore_files: list[str] | None = None, config_path: str = PUBLISHER_CONFIG_PATH):
    """
    Backwards-compatible interface: compiles explores and returns (models_dict, markdown_str).
    """
    from _context_common import get_default_package
    if explore_files is None:
        pkg = get_default_package()
        explore_files = pkg["explore_files"] if pkg else []
    extracted_models = compile_package_explores(explore_files, config_path)
    md_content = generate_inspection_markdown(extracted_models)
    return extracted_models, md_content


# Alias for compatibility
extract_and_flatten_malloy_ontology = extract_and_inspect_malloy_ontology


# ==============================================================================
# GENERIC, PACKAGE-AWARE EXTRACTION (used by run_context_pipeline.py + __main__)
# ==============================================================================
def compile_package_explores(explore_files: list, config_path: str = PUBLISHER_CONFIG_PATH, package_dir: str | None = None) -> dict:
    """
    Compile only a package's *published* explore entry-point files (their `import`
    chain pulls in the underlying source models).
    """
    extracted = {}
    for filepath in explore_files:
        if not os.path.exists(filepath):
            print(f"ℹ️ Explore file not found, skipping: '{filepath}'")
            continue
        if filepath.endswith(".malloynb"):
            continue
        rel_file_path = os.path.relpath(filepath, package_dir) if package_dir else os.path.relpath(filepath, BASE_DIR)
        ast_sources = compile_malloy_file(filepath, config_path)
        explore_base = os.path.splitext(os.path.basename(filepath))[0]
        for source_name, details in ast_sources.items():
            if source_name.endswith("_raw"):
                continue
            is_published = (len(ast_sources) == 1) or (source_name == explore_base)
            extracted[source_name] = {
                "file": rel_file_path,
                "dialect": details.get("dialect", "duckdb"),
                "primary_key": details.get("primary_key"),
                "is_published_explore": is_published,
                "direct_fields": details.get("direct_fields", []),
                "joined_entities": details.get("joined_entities", {}),
                "fields": details.get("fields", []),
            }
    return extracted


def extract_context(package: dict, fresh: bool = False):
    """
    Run Stage 1 for a single package context:
      * compile published explores -> step_1_<ctx>_raw_extracted.json
      * generate inspection markdown -> step_1_<ctx>_inspection.md (Requirement 1)
      * ensure a domain context file -> step_1_<ctx>_domain_context.json
    """
    from _context_common import (
        raw_path,
        domain_path,
        inspection_md_path,
        write_json,
        derive_domain_context,
        load_json,
    )

    print(f"🚀 Extracting Malloy Ontology for context '{package['context_id']}' "
          f"(from {len(package['explore_files'])} published explore file(s))...")
    pkg_dir = package.get("location_dir")
    extracted_data = compile_package_explores(package["explore_files"], PUBLISHER_CONFIG_PATH, package_dir=pkg_dir)

    # OUTPUT 1: per-context raw JSON (schema)
    json_path = raw_path(package)
    write_json(json_path, extracted_data)
    print(f"✅ Generated JSON schema: '{json_path}' ({len(extracted_data)} sources)")

    # OUTPUT 2: per-context inspection Markdown (Requirement 1) - commented out (not needed now)
    # md_path = inspection_md_path(package)
    # markdown_content = generate_inspection_markdown(extracted_data)
    # with open(md_path, "w", encoding="utf-8") as f:
    #     f.write(markdown_content)
    # print(f"✅ Generated Markdown inspection: '{md_path}'")

    # OUTPUT 3: per-context domain context (intents / keywords / group_by)
    d_path = domain_path(package)
    existing = load_json(d_path)
    if existing is not None and not fresh:
        print(f"ℹ️ Domain context already present; keeping curated '{d_path}' "
              f"(delete the file or pass --fresh to auto-regenerate).")
    else:
        domain = derive_domain_context(extracted_data, package=package)
        write_json(d_path, domain)
        print(f"✅ Auto-derived domain context -> '{d_path}' "
              f"({len(domain.get('intents', []))} intents)")
    return json_path, d_path


# ==============================================================================
# EXECUTION & FILE SAVING CONTROL
# ==============================================================================
if __name__ == "__main__":
    import argparse
    from _context_common import get_default_package, find_package

    # Sanity check: Ensure Node script exists before running
    if not os.path.exists(NODE_COMPILER_SCRIPT):
        print(f"❌ Error: Node compiler script missing at '{NODE_COMPILER_SCRIPT}'", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Malloy ontology extraction (Stage 1).")
    parser.add_argument("--context", help="context id to build (default: first discovered package)")
    parser.add_argument("--fresh", action="store_true",
                        help="force re-generation of the domain context file")
    args = parser.parse_args()

    package = find_package(args.context) if args.context else get_default_package()
    if package is None:
        print(f"❌ Unknown context id '{args.context}'. Available: "
              f"{[p['context_id'] for p in __import__('_context_common').iter_packages()]}",
              file=sys.stderr)
        sys.exit(1)
    extract_context(package, fresh=args.fresh)
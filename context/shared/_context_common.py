"""
================================================================================
SHARED HELPERS FOR THE MALLOY CONTEXT / RAG PIPELINE (private, leaf module)
================================================================================

Holds only *generic, package-agnostic* plumbing shared by the three step_*.py
scripts and run_context_pipeline.py.  Nothing here references a specific Malloy
model/package:

  * registry discovery   -> reads publisher.config.json (environments -> packages)
                            plus each package's publisher.json ("explores") to
                            learn which published .malloy entry-points exist.
  * context naming       -> a package becomes a flat context_id used to namespace
                            output files (no sub-folders):
                              step_1_<context_id>_raw_extracted.json
                              step_1_<context_id>_domain_context.json
                              step_2_<context_id>_rag_intent_graph.json
  * domain auto-derivation -> builds a generic starting domain_context (intents,
                            preferred group_by dims, keyword map) straight from an
                            extracted Malloy ontology, so a brand-new package
                            needs no hand-authored config.

It is a *leaf* (imports nothing from step_*.py) so there are no circular imports.
================================================================================
"""

import json
import os
import re
import sys

SHARED_DIR = os.path.dirname(os.path.abspath(__file__))
CONTEXT_DIR = os.path.dirname(SHARED_DIR)
C_CONTEXT_DIR = CONTEXT_DIR
BASE_DIR = os.path.dirname(CONTEXT_DIR)
SCRIPT_DIR = CONTEXT_DIR

# The registry that decides what gets published (manually maintained by humans).
default_cfg_candidates = [
    os.path.join(BASE_DIR, "workspace", "publisher.config.json"),
    os.path.join(BASE_DIR, "publisher.config.json"),
]
PUBLISHER_CONFIG_PATH = os.environ.get(
    "MALLOY_PUBLISHER_CONFIG",
    next((p for p in default_cfg_candidates if os.path.exists(p)), default_cfg_candidates[0])
)


# --- 1) PACKAGE / CONTEXT REGISTRY DISCOVERY --------------------------------
def load_publisher_config(config_path: str = None) -> dict:
    """Load publisher.config.json (empty dict if missing/unparseable)."""
    target = config_path or PUBLISHER_CONFIG_PATH
    if not os.path.exists(target):
        return {"environments": []}
    with open(target, "r", encoding="utf-8") as f:
        return json.load(f)


def _slug(text: str) -> str:
    """Collapse an arbitrary string into a safe, readable filename token."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")


def context_id_for(env: str, package: str) -> str:
    """Canonical, deterministic context id shared by writers and readers.

    Both the artifact writers (iter_packages) and the runtime readers
    (load_context / ChromaRetriever) MUST use this so slugged names can never
    drift from the names actually written to disk / indexed in ChromaDB.
    """
    return f"{_slug(env)}__{_slug(package)}"


def iter_packages(config_path: str = PUBLISHER_CONFIG_PATH) -> list:
    """
    Enumerate every publishable Malloy package into a normalized dict:

        {
          "context_id":     "<env>__<package>"  (unique; used in filenames),
          "env_name":       environment name,
          "package_name":   package name,
          "location_dir":   absolute path of the package folder,
          "publisher_file": absolute path of its publisher.json,
          "explore_files":  [absolute .malloy entry-point files it publishes],
        }

    Published entry points come from each package's own publisher.json
    ("explores": [...], relative to the package folder).  This removes any need
    to hard-code folder names or sniff directory names for "is published".
    """
    cfg = load_publisher_config(config_path)
    packages = []
    for env in cfg.get("environments", []):
        env_name = env.get("name", "environment")
        for pkg in env.get("packages", []):
            pkg_name = pkg.get("name", "")
            location = pkg.get("location", "")
            cfg_dir = os.path.dirname(os.path.abspath(config_path))
            candidate_dirs = [
                os.path.normpath(location if os.path.isabs(location) else os.path.join(cfg_dir, location)),
                os.path.normpath(location if os.path.isabs(location) else os.path.join(BASE_DIR, location)),
            ]
            location_dir = next((d for d in candidate_dirs if os.path.isdir(d)), candidate_dirs[0])
            if not os.path.isdir(location_dir):
                continue
            publisher_file = os.path.join(location_dir, "publisher.json")
            explores = []
            if os.path.exists(publisher_file):
                with open(publisher_file, "r", encoding="utf-8") as f:
                    try:
                        explores = json.load(f).get("explores", [])
                    except json.JSONDecodeError:
                        explores = []
            explore_files = [
                os.path.normpath(os.path.join(location_dir, e)) for e in explores
                if os.path.exists(os.path.join(location_dir, e))
            ]
            context_id = context_id_for(env_name, pkg_name)
            packages.append({
                "context_id": context_id,
                "env_name": env_name,
                "package_name": pkg_name,
                "location_dir": location_dir,
                "publisher_file": publisher_file,
                "explore_files": explore_files,
            })
    return packages


def get_default_package(config_path: str = PUBLISHER_CONFIG_PATH) -> dict:
    """Return the package a step_*.py should use when run standalone.

    Uses the first discovered package.  With several packages, prefer running
    run_context_pipeline.py --context <id> | --all instead.
    """
    packages = iter_packages(config_path)
    if not packages:
        print("❌ No publishable packages found in publisher.config.json.", file=sys.stderr)
        sys.exit(1)
    if len(packages) > 1:
        print(f"ℹ️ Multiple packages found; standalone run uses '{packages[0]['context_id']}'. "
              f"Use run_context_pipeline.py --context <id> | --all for all.", file=sys.stderr)
    return packages[0]


def find_package(context_id: str, config_path: str = PUBLISHER_CONFIG_PATH) -> dict:
    """Return the package matching a context_id, or None."""
    for pkg in iter_packages(config_path):
        if pkg["context_id"] == context_id:
            return pkg
    return None


# --- 2) PER-CONTEXT ARTIFACT PATHS (data/ subfolder) --------------------------
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)


def raw_path(package: dict) -> str:
    """Per-context Stage-1 raw extraction file (schema)."""
    return os.path.join(DATA_DIR, f"step_1_{package['context_id']}_raw_extracted.json")


def domain_path(package: dict) -> str:
    """Per-context Stage-1 domain context (intents / keywords / group_by)."""
    return os.path.join(DATA_DIR, f"step_1_{package['context_id']}_domain_context.json")


def rag_path(package: dict) -> str:
    """Per-context Stage-2 RAG intent/knowledge-graph file."""
    return os.path.join(DATA_DIR, f"step_2_{package['context_id']}_rag_intent_graph.json")


def inspection_md_path(package: dict) -> str:
    """Per-context Stage-1 inspection Markdown file (Requirement 1)."""
    return os.path.join(DATA_DIR, f"step_1_{package['context_id']}_inspection.md")


def knowledge_map_md_path(package: dict) -> str:
    """Per-context Stage-2 knowledge map Markdown file (Requirement 2)."""
    return os.path.join(DATA_DIR, f"step_2_{package['context_id']}_knowledge_map.md")


# --- 3) JSON HELPERS ---------------------------------------------------------
def write_json(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def load_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default
# --- 4) GENERIC DOMAIN-CONTEXT AUTO-DERIVATION --------------------------------
# Words that are structurally meaningless for intent routing or grouping.
_TECHNICAL_DIM_TOKENS = {
    "id", "ids", "key", "keys", "fk", "pk", "uuid", "guid",
    "geom", "geo", "latitude", "longitude", "lat", "lon",
    "postal", "zip", "code", "email", "url", "uri", "ip", "address",
    "street", "name", "fullname",
    "date", "time", "at", "timestamp", "created", "updated", "birth",
    "sequence", "number", "num", "qty",
}

_STOP_TOKENS = {
    "the", "and", "for", "with", "from", "this", "that", "per", "of", "in", "on",
    "all", "any", "its", "our", "their", "were", "was", "has", "have", "been",
    "id", "ids", "total", "average", "avg", "sum", "num", "number",
}


def _split_tokens(text: str) -> list:
    """Tokenize an identifier or sentence into meaningful lowercase words."""
    if not text:
        return []
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))
    s = re.sub(r"[_\-\./\\]+", " ", s)
    words = re.findall(r"[A-Za-z][A-Za-z0-9]*", s)
    return [w.lower() for w in words if w.lower() not in _STOP_TOKENS and len(w) >= 3]


def _field_category(field: dict) -> str:
    return field.get("category") or field.get("expressionType") or "dimension"


def _parts(name) -> list:
    """Split an identifier into lowercase parts (keeps short tokens)."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name))
    return [p for p in re.split(r"[_\-\./\\ ]+", s.lower()) if p]


def _looks_technical_dim(dim_name: str) -> bool:
    parts = _parts(dim_name)
    return bool(parts) and (any(p in _TECHNICAL_DIM_TOKENS for p in parts)
                            or any(p.endswith("id") for p in parts))


def _humanize(identifier: str) -> str:
    words = _split_tokens(identifier)
    return " ".join(w.capitalize() for w in words) if words else identifier


def _preferred_group_by(published_models: dict) -> list:
    """Pick non-technical root-level (non-dotted) dimensions for templates."""
    ordered = []
    for det in published_models.values():
        for f in det.get("direct_fields", []):
            name = f.get("name", "")
            if "." in name or _field_category(f) != "dimension":
                continue
            if _looks_technical_dim(name):
                continue
            if name not in ordered:
                ordered.append(name)
    return ordered


def derive_domain_context(ontology: dict, package: dict | None = None) -> dict:
    """
    Build a *generic starting* domain context directly from an extracted Malloy
    ontology (no hard-coded model knowledge).

    Intents/routing keywords cannot be perfectly inferred from schema alone, so
    this is a deterministic, editable starting point: it emits one overview
    intent per published explore plus one intent per joined entity, and derives
    metric_patterns/keywords from the actual field names + comments.

    A human (or AI) may refine the resulting JSON afterwards without touching
    any Python.  New packages can be used immediately from this auto output.
    """
    published = {k: v for k, v in ontology.items() if v.get("is_published_explore")}
    sources = published if published else ontology
    fallback_explore = next(iter(sources), None)

    preferred = _preferred_group_by(sources)
    intents: list = []
    keyword_mappings: dict = {}

    def register(intent_id: str, patterns: list):
        if not intent_id:
            return
        for tok in patterns:
            keyword_mappings.setdefault(tok, intent_id)

    for source_name, det in sources.items():
        file_path = det.get("file", "")
        direct_fields = det.get("direct_fields", [])
        joined_entities = det.get("joined_entities", {})

        # 1. First, register each entity's OWN name tokens with top priority to prevent collisions
        for entity_name in joined_entities.keys():
            intent_id = f"intent_{entity_name}"
            name_parts = _parts(entity_name)
            name_phrase = " ".join(name_parts)
            # Register full phrase and individual parts
            register(intent_id, [name_phrase] + name_parts)
            # Also register singular forms if plural
            singular_parts = [p[:-1] if p.endswith("s") and len(p) > 3 else p for p in name_parts]
            register(intent_id, [" ".join(singular_parts)] + singular_parts)

        # 2. Overview intent for root-level (cross-entity) measures
        direct_measures = [f for f in direct_fields if _field_category(f) == "measure"]
        if direct_measures:
            root_tokens = []
            for f in direct_measures:
                root_tokens += _split_tokens(f["name"])
            overview_id = f"intent_{source_name}_overview"
            register(overview_id, root_tokens)
            intents.append({
                "intent_id": overview_id,
                "intent_name": f"{_humanize(source_name)} Core Metrics",
                "description": "Core cross-cutting measures and calculations defined at the "
                               f"root of explore '{source_name}' (file {file_path}).",
                "entity_filters": list(joined_entities.keys()),
                "metric_patterns": sorted(set(root_tokens)),
            })

        # 3. One intent per joined entity for field-derived tokens
        for entity_name, entity_info in joined_entities.items():
            fields = entity_info.get("fields", [])
            measures = [f for f in fields if _field_category(f) == "measure"]
            dims = [f for f in fields if _field_category(f) == "dimension"]
            if not measures and not dims:
                continue
            tokens = []
            for f in measures + dims:
                tokens += _split_tokens(f["name"])
            intent_id = f"intent_{entity_name}"
            if intent_id in [i["intent_id"] for i in intents]:
                continue
            register(intent_id, tokens)
            docs = [f.get("comment", "") for f in (measures + dims) if f.get("comment")]
            snippet = docs[0] if docs else f"Measures and dimensions of the '{entity_name}' entity."
            if len(snippet) > 220:
                snippet = snippet[:220].rsplit(" ", 1)[0] + "…"
            intents.append({
                "intent_id": intent_id,
                "intent_name": f"{_humanize(entity_name)} Analysis",
                "description": snippet,
                "entity_filters": [entity_name, source_name],
                "metric_patterns": sorted(set(tokens)),
            })

    published_file = sources[fallback_explore].get("file", "") if fallback_explore and fallback_explore in sources else ""
    pkg_desc = (package.get("description") if package else "") or (f"Malloy semantic layer for explore '{fallback_explore}'" if fallback_explore else "")

    return {
        "context_source": "auto-derived (editable)",
        "published_file": published_file,
        "package_description": pkg_desc,
        "preferred_group_by": preferred,
        "fallback_explore": fallback_explore,
        "intents": intents,
        "keyword_mappings": keyword_mappings,
    }



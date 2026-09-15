"""
================================================================================
TASK 2: VECTOR DB / RAG INGESTION READINESS - INTENT & GRAPH INDEXING
================================================================================

OBJECTIVE:
- Process Task 1 extracted ontology (step_1_malloy_raw_extracted.json) into modular,
  high-precision chunks optimized for Vector Databases (Qdrant, Pinecone, ChromaDB, pgvector).
- Implement Strategy 3: Dynamic Context Builder / Knowledge Graph Indexing.
- Index business intents, entity graph nodes, and metric/field definitions.
- Attach complete metadata tags (source_name, parent_source, file_name,
  is_published_explore, intent_name, chunk_type, entity_type, dialect) for
  filtered semantic retrieval.
================================================================================
"""

import json
import os
import sys
from typing import Dict, List, Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
C_CONTEXT_DIR = os.path.dirname(SCRIPT_DIR)
BASE_DIR = os.path.dirname(C_CONTEXT_DIR)

if C_CONTEXT_DIR not in sys.path:
    sys.path.insert(0, C_CONTEXT_DIR)
shared_dir = os.path.join(C_CONTEXT_DIR, "shared")
if shared_dir not in sys.path:
    sys.path.insert(0, shared_dir)


def classify_field_category(field: dict) -> str:
    """Returns 'measure' or 'dimension' for a field."""
    return field.get("category") or field.get("expressionType") or "dimension"

import re as _re

IDENT_RE = _re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def malloy_field_ref(name: str) -> str:
    """Returns a Malloy-safe field reference, quoting individual segments if needed."""
    if not name:
        return ""
    segments = str(name).split(".")
    quoted = [s if IDENT_RE.match(s) else f"`{s}`" for s in segments]
    return ".".join(quoted)


def build_query_template(source_name: str, group_by: str | None, metric_names: list) -> str:
    """PILLAR 2: Builds a zero-shot executable Malloy query reference pattern.

    Uses only canonical (fully-qualified) field paths so the returned Malloy
    compiles on the first attempt from the root explore.
    """
    lines = ["# Zero-Shot Executable Malloy Reference Pattern:"]
    lines.append(f"run: {source_name} -> {{")
    if group_by:
        lines.append(f"  group_by: {malloy_field_ref(group_by)}")
    if metric_names:
        lines.append("  aggregate:")
        for metric in metric_names:
            lines.append(f"    {malloy_field_ref(metric)}")
    lines.append("}")
    return "\n".join(lines)


def pick_group_by_dimension(root_dims: list, preferred_group_by: list | None = None) -> str | None:
    """PILLAR 1: Picks a root-level (non-dotted) dimension for a valid group_by.

    Uses the caller-provided preferred dimensions (from the per-context domain
    context); otherwise falls back to the first root-level dimension, or None.
    """
    candidates = [d["name"] for d in root_dims if "." not in d.get("name", "")]
    for preferred in (preferred_group_by or []):
        if preferred in candidates:
            return preferred
    return candidates[0] if candidates else None



def generate_intent_graph_chunks(
    extracted_models: dict,
    intents: list | None = None,
    preferred_group_by: list | None = None,
) -> list[dict]:
    """
    Generates a multi-layer Intent / Knowledge Graph indexing structure for Vector DBs.

    Layers:
    1. Business Intent Nodes (Intent -> Explore + Entities + Key Metrics)
    2. Entity Graph Nodes (Root & Joined Entities)
    3. Metric & Field Nodes (High-precision measures & key dimensions)

    `intents` and `preferred_group_by` are supplied by the per-context domain
    context (step_1 output / run_context_pipeline.py).  When `intents` is None a
    generic, schema-derived intent set is auto-generated so the function remains
    callable without any model-specific knowledge.
    """
    rag_chunks = []

    # Filter published explores vs base models
    published_models = {k: v for k, v in extracted_models.items() if v.get("is_published_explore")}
    target_models = published_models if published_models else extracted_models

    # --------------------------------------------------------------------------
    # LAYER 1: BUSINESS INTENT NODES (Domain-Level Intent Vectorization)
    # --------------------------------------------------------------------------
    if intents is None:
        from _context_common import derive_domain_context
        intents = derive_domain_context(extracted_models).get("intents", [])
    intents_definition = intents or []

    for source_name, details in target_models.items():
        file_path = details.get("file", "")
        dialect = details.get("dialect", "duckdb")
        primary_key = details.get("primary_key", "")
        is_published = details.get("is_published_explore", False)
        direct_fields = details.get("direct_fields", [])
        joined_entities = details.get("joined_entities", {})

        # Root-level dimensions (used to pick a valid, non-dotted group_by key)
        root_dims = [f for f in direct_fields if classify_field_category(f) == "dimension"]

        # Build Layer 1 Chunks for each defined intent
        for intent in intents_definition:
            matching_metrics = []
            matching_dimensions = []

            # Gather matching root fields
            for f in direct_fields:
                cat = classify_field_category(f)
                name_lower = f["name"].lower()
                comment_lower = f.get("comment", "").lower()
                if any(p in name_lower or p in comment_lower for p in intent["metric_patterns"]):
                    if cat == "measure":
                        matching_metrics.append(f)
                    else:
                        matching_dimensions.append(f)

            # Gather matching joined fields
            relevant_entities = []
            for entity_name, entity_info in joined_entities.items():
                if entity_name in intent["entity_filters"]:
                    relevant_entities.append(entity_name)
                    for f in entity_info.get("fields", []):
                        cat = classify_field_category(f)
                        name_lower = f["name"].lower()
                        comment_lower = f.get("comment", "").lower()
                        if any(p in name_lower or p in comment_lower for p in intent["metric_patterns"]):
                            if cat == "measure":
                                matching_metrics.append(f)
                            else:
                                matching_dimensions.append(f)

            if matching_metrics or matching_dimensions or relevant_entities:
                # PILLAR 1: Canonical fully-qualified field paths (root = bare, joined = dotted)
                canonical_metrics = [m["name"] for m in matching_metrics]
                canonical_dimensions = [d["name"] for d in matching_dimensions]

                metrics_text = "\n".join([
                    f"  * `{m['name']}` ({m['type']}): {m.get('comment', '')}" for m in matching_metrics
                ]) if matching_metrics else "  * (None direct)"

                dims_text = "\n".join([
                    f"  * `{d['name']}` ({d['type']}): {d.get('comment', '')}" for d in matching_dimensions[:15]
                ]) if matching_dimensions else "  * (None direct)"

                # PILLAR 2: Zero-shot executable Malloy reference pattern injected into the chunk
                executable_template = build_query_template(
                    source_name,
                    pick_group_by_dimension(root_dims, preferred_group_by),
                    canonical_metrics[:10],
                ) if canonical_metrics else ""

                text_content = (
                    f"BUSINESS INTENT: {intent['intent_name']}\n"
                    f"Intent ID: {intent['intent_id']}\n"
                    f"Description: {intent['description']}\n"
                    f"Required Explore: {source_name}\n"
                    f"Relevant Joined Entities: {', '.join(relevant_entities)}\n"
                    f"File: {file_path} | Dialect: {dialect} | Primary Key: {primary_key}\n\n"
                    f"Key Measures & Metrics:\n{metrics_text}\n\n"
                    f"Key Dimensions:\n{dims_text}"
                )
                if executable_template:
                    text_content += "\n\n" + executable_template

                rag_chunks.append({
                    "id": f"intent__{source_name}__{intent['intent_id']}",
                    "text": text_content,
                    "metadata": {
                        "chunk_type": "business_intent",
                        "intent_id": intent["intent_id"],
                        "intent_name": intent["intent_name"],
                        "source_name": source_name,
                        "parent_source": source_name,
                        "file_name": file_path,
                        "is_published_explore": is_published,
                        "dialect": dialect,
                        "relevant_entities": relevant_entities,
                        "metrics_count": len(matching_metrics),
                        "dimensions_count": len(matching_dimensions),
                        "canonical_metrics": canonical_metrics,
                        "canonical_dimensions": canonical_dimensions,
                        "executable_template": executable_template
                    }
                })

        # --------------------------------------------------------------------------
        # LAYER 2: ENTITY GRAPH NODE CHUNKS (Root Explore + Joined Entity Nodes)
        # --------------------------------------------------------------------------
        # 2a. Root Entity Node Chunk
        if direct_fields:
            measures = [f for f in direct_fields if classify_field_category(f) == "measure"]
            dimensions = [f for f in direct_fields if classify_field_category(f) == "dimension"]

            root_fields_summary = "\n".join([
                f"- `{f['name']}` [{classify_field_category(f)}] ({f['type']}): {f.get('comment', '')}"
                for f in direct_fields
            ])

            # PILLAR 2: Executable reference for root measures
            root_template = build_query_template(
                source_name,
                pick_group_by_dimension(dimensions, preferred_group_by),
                [m["name"] for m in measures][:10],
            ) if measures else ""

            root_node_text = (
                f"GRAPH NODE: Root Explore `{source_name}`\n"
                f"File: {file_path} | Dialect: {dialect} | Primary Key: {primary_key}\n"
                f"Is Published Explore: {is_published}\n"
                f"Direct Measures Count: {len(measures)} | Direct Dimensions Count: {len(dimensions)}\n"
                f"Joined Entities Available: {', '.join(joined_entities.keys())}\n\n"
                f"Fields:\n{root_fields_summary}"
            )
            if root_template:
                root_node_text += "\n\n" + root_template

            rag_chunks.append({
                "id": f"node_root__{source_name}",
                "text": root_node_text,
                "metadata": {
                    "chunk_type": "entity_graph_node",
                    "entity_type": "root",
                    "source_name": source_name,
                    "parent_source": source_name,
                    "joined_entity": None,
                    "file_name": file_path,
                    "is_published_explore": is_published,
                    "dialect": dialect,
                    "measures_count": len(measures),
                    "dimensions_count": len(dimensions)
                }
            })

        # 2b. Joined Entity Node Chunks
        for entity_name, entity_info in joined_entities.items():
            entity_fields = entity_info.get("fields", [])
            measures = [f for f in entity_fields if classify_field_category(f) == "measure"]
            dimensions = [f for f in entity_fields if classify_field_category(f) == "dimension"]

            entity_fields_summary = "\n".join([
                f"- `{f['name']}` [{classify_field_category(f)}] ({f['type']}): {f.get('comment', '')}"
                for f in entity_fields
            ])

            # PILLAR 1 + 2: joined-entity measures are already namespaced (order_items.Total_Revenue);
            # template groups from a root dimension and aggregates the canonical dotted measures.
            entity_template = build_query_template(
                source_name,
                pick_group_by_dimension(root_dims, preferred_group_by),
                [m["name"] for m in measures][:10],
            ) if measures else ""

            entity_node_text = (
                f"GRAPH NODE: Joined Entity `{entity_name}` in Explore `{source_name}`\n"
                f"Parent Explore: {source_name}\n"
                f"File: {file_path} | Dialect: {dialect}\n"
                f"Total Fields: {len(entity_fields)} (Measures: {len(measures)}, Dimensions: {len(dimensions)})\n\n"
                f"Joined Entity Fields:\n{entity_fields_summary}"
            )
            if entity_template:
                entity_node_text += "\n\n" + entity_template

            rag_chunks.append({
                "id": f"node_join__{source_name}__{entity_name}",
                "text": entity_node_text,
                "metadata": {
                    "chunk_type": "entity_graph_node",
                    "entity_type": "join",
                    "source_name": source_name,
                    "parent_source": source_name,
                    "joined_entity": entity_name,
                    "file_name": file_path,
                    "is_published_explore": is_published,
                    "dialect": dialect,
                    "measures_count": len(measures),
                    "dimensions_count": len(dimensions)
                }
            })

        # --------------------------------------------------------------------------
        # LAYER 3: FIELD & METRIC NODE CHUNKS (High-Precision Measure Nodes)
        # --------------------------------------------------------------------------
        all_explore_fields = direct_fields + [
            f for ef in joined_entities.values() for f in ef.get("fields", [])
        ]

        for field in all_explore_fields:
            category = classify_field_category(field)
            # Index all measures and dimensions as first-class nodes for maximum retrieval precision
            if category in ("measure", "dimension"):
                field_name = field["name"]
                entity_owner = field_name.split(".")[0] if "." in field_name else source_name

                field_node_text = (
                    f"FIELD DEFINITION: `{field_name}`\n"
                    f"Explore: {source_name} | Entity: {entity_owner}\n"
                    f"Category: {category} | Data Type: {field['type']}\n"
                    f"Description: {field.get('comment', 'No description provided')}\n"
                    f"File: {file_path}"
                )

                rag_chunks.append({
                    "id": f"field_node__{source_name}__{field_name.replace('.', '_')}",
                    "text": field_node_text,
                    "metadata": {
                        "chunk_type": "field_metric_node",
                        "field_name": field_name,
                        "field_category": category,
                        "field_type": field["type"],
                        "source_name": source_name,
                        "parent_source": source_name,
                        "entity_name": entity_owner,
                        "file_name": file_path,
                        "is_published_explore": is_published,
                        "dialect": dialect
                    }
                })

    return rag_chunks


def generate_intent_knowledge_map_markdown(rag_chunks: list[dict]) -> str:
    """Generates human-readable Markdown documenting the RAG Intent Knowledge Graph."""
    md_lines = ["# Malloy Intent Knowledge Graph & RAG Indexing Map\n"]
    
    intent_chunks = [c for c in rag_chunks if c["metadata"]["chunk_type"] == "business_intent"]
    entity_chunks = [c for c in rag_chunks if c["metadata"]["chunk_type"] == "entity_graph_node"]
    field_chunks = [c for c in rag_chunks if c["metadata"]["chunk_type"] == "field_metric_node"]

    md_lines.append(f"**Total Vector RAG Chunks:** `{len(rag_chunks)}` | "
                    f"**Intent Nodes:** `{len(intent_chunks)}` | "
                    f"**Entity Nodes:** `{len(entity_chunks)}` | "
                    f"**Metric Nodes:** `{len(field_chunks)}` \n")

    md_lines.append("## 1. Business Intent Nodes\n")
    md_lines.append("| Intent ID | Intent Name | Target Explore | Relevant Entities | Metrics Count |")
    md_lines.append("|---|---|---|---|---|")
    for c in intent_chunks:
        meta = c["metadata"]
        entities = ", ".join([f"`{e}`" for e in meta.get("relevant_entities", [])])
        md_lines.append(f"| `{meta['intent_id']}` | **{meta['intent_name']}** | `{meta['source_name']}` | {entities} | `{meta['metrics_count']}` |")

    md_lines.append("\n## 2. Entity Knowledge Graph Nodes\n")
    md_lines.append("| Node ID | Entity Type | Source Name | Joined Entity | Measures | Dimensions |")
    md_lines.append("|---|---|---|---|---|---|")
    for c in entity_chunks:
        meta = c["metadata"]
        joined = f"`{meta['joined_entity']}`" if meta.get("joined_entity") else "*(Root)*"
        md_lines.append(f"| `{c['id']}` | `{meta['entity_type']}` | `{meta['source_name']}` | {joined} | `{meta['measures_count']}` | `{meta['dimensions_count']}` |")

    md_lines.append("\n---\n")
    return "\n".join(md_lines)


def build_rag_for_package(package: dict, extracted_ontology: dict) -> str:
    """Run Stage 2 for one package context: read its domain context + ontology
    and write the per-context RAG intent graph JSON file and Markdown Knowledge Map.
    Returns the output JSON path."""
    from _context_common import (
        domain_path,
        rag_path,
        knowledge_map_md_path,
        load_json,
        write_json,
    )

    domain = load_json(domain_path(package)) or {}
    intents = domain.get("intents")
    preferred = domain.get("preferred_group_by")
    print(f"🚀 Processing ontology into Intent Knowledge Graph RAG Chunks "
          f"({package['context_id']})...")
    rag_chunks = generate_intent_graph_chunks(
        extracted_ontology,
        intents=intents,
        preferred_group_by=preferred,
    )

    # OUTPUT 1: per-context RAG JSON
    out_json = rag_path(package)
    write_json(out_json, rag_chunks)
    print(f"✅ Generated {len(rag_chunks)} RAG chunks in '{out_json}'")

    # OUTPUT 2: per-context Markdown Knowledge Map (Requirement 2) - commented out (not needed now)
    # out_md = knowledge_map_md_path(package)
    # md_map = generate_intent_knowledge_map_markdown(rag_chunks)
    # with open(out_md, "w", encoding="utf-8") as f:
    #     f.write(md_map)
    # print(f"✅ Generated RAG Knowledge Map in '{out_md}'")

    return out_json


if __name__ == "__main__":
    from _context_common import get_default_package, raw_path
    package = get_default_package()
    inp = raw_path(package)
    if not os.path.exists(inp):
        print(f"❌ Error: Stage 1 output missing at '{inp}'. "
              f"Run step_1 (or run_context_pipeline.py) first.", file=sys.stderr)
        sys.exit(1)

    with open(inp, "r", encoding="utf-8") as f:
        extracted_ontology = json.load(f)

    build_rag_for_package(package, extracted_ontology)

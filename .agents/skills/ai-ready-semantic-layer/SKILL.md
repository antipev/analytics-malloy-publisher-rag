---
name: ai-ready-semantic-layer
description: Structured methodology for documenting Malloy semantic models (dimensions, measures, ontology headers) so AI agents can accurately interpret them via MCP.
---

# Building AI-Ready Malloy Semantic Layers

This skill provides a structured methodology for documenting Malloy models to ensure they are fully interpretable by AI agents (like Antigravity, Claude, or Gemini) accessing them via MCP.

## The Core Concept: Semantic Ontology
An "AI-Ready" Malloy file is more than just code; it is a **self-describing ontology**. It maps out what things are and how they connect in the real world. By using specific commenting conventions and structural headers, you provide the **Context** that agents need to understand the relationship between data grains and dimensions.

## Semantic Hints: Dimensions vs. Measures
Distinguishing between grouping fields and aggregations is critical for AI precision.
- **`@dimension`**: Used for fields intended for `group_by`, `where`, or as join keys.
- **`@measure`**: Used for pre-baked aggregations.
- **Instruction to AI:** Always prefer a namespaced `@measure` (e.g., `users.Total_Users`) over a manual count of an `@dimension` to ensure correct grain and filtering logic is applied.

## Documentation Workflow

### 1. The Ontology Header & Business Navigation
Always start the primary "Explore" file with a documentation block that defines the architectural pattern and provides a navigation guide for business questions.
- **Key Terms:** Use `@ontology`, `@context`.
- **Navigation Guide:** Map common business questions (e.g., Customers, Sales, Inventory) to specific namespaces.
- **Semantic Rules:** Explicitly tell the AI to prioritize measures over manual calculations.

### 2. Precise Wording (No Paraphrasing)
When documenting sources, dimensions, and measures, **always use the exact verbatim wording** from the source's `#(doc)` tags.

### 3. Block Comments for Field Discovery
Use comprehensive block comments placed outside of source code enclosures/curly braces (at the beginning or end of the file). Do not place AI documentation comments inside source definition brackets `{ ... }`, as brackets are strictly reserved for executable Malloy code.
- Use `@dimension` and `@measure` tags for **every single field**.
- This acts as a functional contract for the AI agent.

### 4. Namespace Documentation
For every joined source, provide a namespace block that summarizes its role and key fields using verbatim descriptions, placed completely outside any source definition brackets.
- **Syntax:** 
  ```malloy
  /* 
   * @namespace [source_name]
   * @description [Verbatim Purpose from #(doc)]
   * @dimension [field_name]: [Verbatim Definition]
   * @measure [measure_name]: [Verbatim Definition]
   */
  ```

## Code Integrity & Comment Placement Safety
To ensure the model remains fully valid and executable:
- **No Comments in Brackets:** Never put AI documentation comments inside the curly braces of a source definition block.
- **File Placement:** Keep all AI metadata blocks at the top or at the very end of the file, entirely separate from the active Malloy code declarations.
- **No Accidental Syntax Modification:** Never introduce opening or closing curly braces (`{}`) solely to wrap comments, as this breaks or alters the source's structure.

---
name: malloy-query-best-practices
description: Best practices for querying the unified star schema in Malloy, specifically for the ecommerce_explore source. Use when generating Malloy queries to analyze transactions, web behavior, or product data.
---

# Malloy Query Best Practices

This skill provides architectural rules and patterns for generating accurate Malloy queries against the `ecommerce_explore` source.

## Core Rules

### 1. Primary Data Source
Always initiate queries using the `ecommerce_explore` source. This is the main semantic entry point that integrates transactions, web behavior, and product data.
- **Example:** `run: ecommerce_explore -> { ... }`

### 2. Explicit Pathing (Namespace)
Always use explicit pathing for measures and dimensions. This makes the query readable and ensures Malloy uses the correct join path.
- **Correct:** `order_items.Total_Revenue`
- **Avoid:** `Total_Revenue` (even if it's the only one, explicit is better).

### 3. Intra-Source Consistency Rule
If a measure and a dimension are available within the same joined source (e.g., `order_items`), always use the dimension from that specific source rather than the top-level dimension.
- **The Logic:** Coupling dimensions and measures from the same source (like `order_items.User_Country` with `order_items.Total_Revenue`) ensures that the grouping occurs at the exact grain where the transaction exists, avoiding potential "fan-out" or null issues from unrelated stages in the bridge model.
- **Correct (Country split for Revenue):**
  ```malloy
  group_by: order_items.User_Country
  aggregate: order_items.Total_Revenue
  ```
- **Sub-optimal:**
  ```malloy
  group_by: User_Country  // Using the top-level pick dimension
  aggregate: order_items.Total_Revenue
  ```
- **Exception — cross-source / bridge measures:** When a query combines measures from different sources (e.g., `order_items.Total_Revenue` + `bridge_model.Total_Gross_Margin` + `events.Count`), no single fact's dimension is correct; group by the BRIDGE common dimension instead (`bridge_model.User_Country`, or the top-level `User_Country`):
  ```malloy
  group_by: bridge_model.User_Country
  aggregate: bridge_model.Total_Gross_Margin, order_items.Total_Revenue
  ```

### 4. Filtering and Aggregation
When filtering by time, use the specific timestamp relevant to the measure's grain.
- **Example (Revenue for 2026):**
  ```malloy
  where: order_items.Created_at.year = 2026
  aggregate: order_items.Total_Revenue
  ```

## Query Patterns

### Basic Aggregation Pattern
```malloy
run: ecommerce_explore -> {
  group_by: [source].[dimension]
  aggregate: [source].[measure]
}
```

### Time-Based Analysis Pattern
```malloy
run: ecommerce_explore -> {
  where: [source].[timestamp].year = [year]
  group_by: [source].[timestamp].month
  aggregate: [source].[measure]
}
```

## Available MCP Tools (Malloy Publisher)
You have access to the following Malloy Publisher MCP tools. Always use these to navigate the semantic layer and execute queries:
* `malloy_getContext`: Discover environments/packages, then retrieve the sources, views, dimensions and measures most relevant to a plain-English question. Progressive: no args -> environments; +environmentName -> packages; +query -> fields.
* `malloy_executeQuery`: Run a Malloy query (ad-hoc `query`, or named `queryName`/`sourceName`) against a model.
* `malloy_searchDocs`: Search Malloy language docs (filters, aggregates, joins, nesting).
* `malloy_searchDatabaseSchema`: Find tables/columns in a database connection by description (to model an unmodeled DB).
* `malloy_compile`: Compile a model (authoring).
* `malloy_reloadPackage`: Reload a package after editing.

## Discovery Protocol for Templates & Underlying Sources
If the user asks to find templates, pre-configured queries, available views, or deep details about underlying sources:
1. Call `malloy_getContext` with no arguments to list environments and their packages.
2. Call it again with `environmentName` (and `packageName`) to list what the package exposes.
3. Call it with a plain-English `query` to retrieve the most relevant sources, views, dimensions and measures (with their `#(doc)` descriptions).
4. For a database connection not yet modeled, use `malloy_searchDatabaseSchema` to walk schemas/tables/columns.

## Analytical Execution Protocol
When a user asks an analytical question (e.g., "What is the revenue for X?"), follow these steps:
1. **Ground:** call `malloy_getContext` with the question to confirm exact field names and paths.
2. **Identify the View:** reuse a Named Query / View if one already answers the question.
3. **Execute:** call `malloy_executeQuery` — `queryName`/`sourceName` for a named view, or the `query` parameter for ad-hoc Malloy.
4. **Strict Syntax:** follow the "Primary Data Source" + "Explicit Pathing" + "Intra-Source Consistency" rules at the top of this skill.

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

## Available MCP Tools for Malloy Cloud
You have access to the following Malloy Cloud MCP tools. Always use these to navigate the semantic layer and execute queries:
* `m_malloy_projectList`: Lists all Malloy projects.
* `m_malloy_packageList`: Lists all Malloy packages within a project.
* `m_malloy_packageGet`: Lists resources within a package.
* `m_malloy_modelGetText`: Gets the raw text content of a model file.
* `m_malloy_executeQuery`: Executes a Malloy query (ad-hoc or named) against a model.

## Discovery Protocol for Templates & Underlying Sources
If the user asks to find templates, pre-configured queries, available views, or deep details about underlying sources, execute the following chain of actions:
1. Use `m_malloy_projectList` and `m_malloy_packageList` to explore the available data.
2. Use `m_malloy_modelGetText` to read the primary model file.
3. Extract and list all the **Named Queries** and **Views** defined inside the model, providing a brief explanation of what each one analyzes.
4. **Deep Source Discovery via Import-Proxy:** If source fields or schemas are not fully visible in the primary package manifest, execute an ad-hoc query with an `import` statement targeting the specific `.malloy` file path, combined with `index: *` to extract all available dimensions.
   - *Example:* `import "/app/A_Semantic_Layer/1_sources/products.malloy" run: products_source -> { index: * }`
5. **Measure Verification:** Since `index: *` only discovers dimensions, verify available measures by inspecting referenced dashboard files (`.malloynb`) or executing minimal ad-hoc aggregations based on discovered keys.

## Analytical Execution Protocol
When a user asks an analytical question (e.g., "What is the revenue for X?" or "Show me trends for Y"), follow these steps:
1. **Identify the View:** Check if a pre-existing Named Query or View (discovered via the Discovery Protocol) already answers the question.
2. **Execute:** - If a view exists, use `m_malloy_executeQuery` with the `named_query` parameter.
   - If no view exists, use your Malloy expertise to write a new query and execute it via `m_malloy_executeQuery` using the `query` parameter.
3. **Strict Syntax:** Ensure the generated Malloy code follows the "Primary Data Source" and "Explicit Pathing" rules defined at the top of this skill.

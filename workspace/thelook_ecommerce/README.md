# theLook eCommerce Semantic Package

This directory contains the unified semantic layer for **theLook eCommerce**, organized into a modular 4-layer architecture and configured for publication via **Malloy Publisher**.

---

## Architecture Overview

```text
thelook_ecommerce/
├── publisher.json             # Package manifest allowlisting published explores & dashboards
├── 1_raw_views/               # Layer 1: Parquet files & dialect-agnostic source mappings (config.malloy)
├── 2_refinements/             # Layer 2: Entity staging, primary keys, measures, and #(doc) docstrings
├── 3_explores/                # Layer 3: Dynamic Unified Star Schema (ecommerce_explore.malloy)
├── 4_analysis/                # Layer 4: Dashboards (business_pulse) and ad-hoc analysis
├── public/                    # Served static HTML data apps & reports
└── README.md                  # Package developer guide
```

---

## The 4 Modeling Layers

### 1. `1_raw_views/` — Source Definitions
* Maps physical storage (DuckDB parquet files or BigQuery tables) into raw Malloy sources in `config.malloy`.
* Tables include: `distribution_centers`, `events`, `inventory_items`, `order_items`, `orders`, `products`, `users`, and the `bridge_raw` stage union.

### 2. `2_refinements/` — Entity Refinement & Business Logic
* Cleans, categorizes, and enriches each entity independently.
* Establishes `primary_key`, time dimensions, and business measures.
* Every metric and dimension includes `#(doc)` annotations for AI agents and the visual query explorer.

### 3. `3_explores/` — Dynamic Unified Star Schema (`ecommerce_explore.malloy`)
* Uses a **Bridge Pattern** to integrate disparate transactional facts (orders, web events, users) without Cartesian explosion.
* Defines common dimensions across entities (`User_Country`, `User_Age`, `User_Traffic_Source`, etc.).
* Exposes `ecommerce_explore` via `compose(...)`, unifying all business domains under a single coherent explore.

### 4. `4_analysis/` — Dashboards & Analysis
* **`dashboards/business_pulse.dashboard.malloynb`**: Visual executive KPI dashboard with trendlines, order category breakdowns, and traffic source attribution.
* **`adhoc/random_queries.malloy`**: Developer scratchpad and query validation scripts.

---

## Publishing Configuration (`publisher.json`)

Malloy Publisher uses the `explores` array in `publisher.json` as an explicit allowlist. Any `.malloy` file not listed here remains private to the package:

```json
{
  "name": "thelook_ecommerce",
  "version": "1.0.0",
  "description": "theLook eCommerce Unified Star Schema Semantic Layer — Orders, inventory, web events, and customer analytics.",
  "explores": [
    "3_explores/ecommerce_explore.malloy"
  ]
}
```

# Handover: Root-Scoped Indexes, Global Routing Indexes, and Lossy Folder Summaries

## Goal

Design a local document indexing/search system where:

* SQLite is the global source of truth.
* Full FTS and vector indexes remain scoped by folder root or index scope.
* A lightweight global search layer helps route queries to the most likely roots/scopes.
* Summaries are intentionally lossy and used for routing, not final proof.
* The system avoids blindly parsing or searching huge folder trees when a cheaper plan can guide the work.

Core rule:

```text
Summaries route.
Samples support.
Deep indexes prove.
SQLite remembers everything.
```

## Core architecture

```text
SQLite
  global truth:
    source roots
    folders
    files
    parsed objects
    chunks
    tables
    images/captions
    metadata
    summary nodes
    index registry
    query usage

Root-scoped full indexes
  fts/<profile>/<scope_id>/
  semantic/<profile>/<scope_id>.lancedb/

Global representative indexes
  fts/global_representatives/
  semantic/global_representatives.lancedb/

Optional materialized collection indexes
  fts/collections/<collection_id>/
  semantic/collections/<collection_id>.lancedb/
```

SQLite is authoritative. FTS and LanceDB indexes are replaceable physical plans.

## Key terms

| Term                  | Meaning                                                               |
| --------------------- | --------------------------------------------------------------------- |
| Source root           | User-approved logical boundary, for example `D:/Work` or `D:/Private` |
| Index scope           | Physical indexing unit, usually folder-root scoped                    |
| Query collection      | Logical query scope that may span multiple roots or scopes            |
| Representative object | Summary/sample/manifest used to route search deeper                   |

Source roots should mostly be user-approved. Index scopes can be suggested automatically.

## Root discovery and scan planning

When the user submits a folder, do not immediately parse everything.

First run a cheap inventory scan:

```text
count files
count parseable files
estimate bytes
detect file types
detect excluded/generated folders
detect project markers
detect archives
detect likely document clusters
estimate parse cost
suggest index scopes
```

Thresholds should trigger planning/review, not automatic splitting.

Useful safeguards:

```yaml
safeguards:
  max_parseable_files_without_review: 5000
  max_bytes_without_review: 10737418240  # 10 GiB
  max_estimated_parse_seconds_without_review: 3600
  max_depth: 20
  follow_symlinks: false
  require_review_for_archives: true
  require_review_for_many_roots: true
```

Common excludes:

```yaml
exclude:
  - "**/.git/**"
  - "**/node_modules/**"
  - "**/.venv/**"
  - "**/__pycache__/**"
  - "**/dist/**"
  - "**/build/**"
  - "**/.cache/**"
```

## Split for ingestion, merge for retrieval

```text
Split for ingestion.
Merge for repeated retrieval.
Keep catalog as truth.
Treat indexes as replaceable physical plans.
```

Root-scoped indexes are good for incremental refresh, parallel indexing, fault isolation, and privacy boundaries.

Many split indexes are bad for broad repeated queries because they require fanout:

```text
search root A
search root B
search root C
merge top-k
normalize scores
hydrate results
deduplicate
```

For occasional broad search, virtual fanout is acceptable.

For repeated broad search, create a materialized collection index.

## Global representative indexes

Keep one lightweight global FTS and one lightweight global vector index.

These global indexes should not contain every chunk. They should contain representatives:

```text
root summaries
folder summaries
document summaries
cluster summaries
archive manifests
rare keyword bags
important filenames/path tokens
selected medoid chunks
selected exemplar chunks
negative summaries
```

Purpose:

```text
query -> global representative index -> likely roots/scopes -> deep root-scoped indexes
```

The global representative index is a map, not the territory.

## Multi-resolution search

Recommended levels:

```text
L0: root representatives
L1: major folder representatives
L2: document/archive representatives
L3: cluster representatives
L4: real chunks/tables/images inside root-scoped indexes
```

Search loop:

```text
1. Search global representatives.
2. Pick likely roots/folders/clusters.
3. Search deep root-scoped indexes only for those candidates.
4. If evidence is good, answer.
5. If weak, widen:
   - more representative hits
   - sibling folders
   - parent folders
   - more roots
   - larger top-k
6. If still weak, fall back to broader fanout or ask the user to narrow.
```

Routing can be imperfect because the search loop can widen.

## Lossy folder summaries

Use destructive summaries as routing summaries.

Better internal name:

```text
lossy routing summary
```

A folder summary should not summarize 100% of chunks. It should summarize a selected evidence pack.

Bad use:

```text
The summary did not mention X, therefore X is not there.
```

Good use:

```text
The summary did not route to X strongly, so widen search.
```

## Folder summary input pack

Use stratified destructive sampling, not pure random sampling.

For each folder/root, build a summary input pack from:

```text
folder name/path tokens
child folder names
file type histogram
top filenames
rare keywords
extracted entities
document titles/headings
cluster medoids
a few random chunks
large/central documents
recent documents
user-marked valuable items
archive manifests
negative/generated-folder detection
```

Suggested sampling mix:

```text
40% cluster medoids / centroid-nearest chunks
20% rare-term or entity-rich chunks
15% important filenames / titles / headings
15% random reservoir sample
10% recent or modified files
```

For generated folders:

```text
build, dist, node_modules, .venv:
  generate tiny negative summary or exclude by default
```

For archives:

```text
archives/backups:
  summarize manifest first
  unpack/index deeper only if opted in or strongly hit by query
```

## Folder summary should rank above random chunks

High-level search priority:

```text
1. path/name/metadata exact match
2. folder/root lossy summaries
3. child summaries
4. representative chunks
5. random samples
6. deep root-scoped FTS/LanceDB
7. broad fallback
```

A folder summary is a compressed map of many signals. A random chunk is only an accidental window.

## Summary node schema

Suggested SQLite table:

```sql
CREATE TABLE summary_nodes (
  id TEXT PRIMARY KEY,
  parent_id TEXT,
  root_id TEXT NOT NULL,
  scope_id TEXT,
  folder_path TEXT,
  level INTEGER NOT NULL,
  kind TEXT NOT NULL,
  summary_text TEXT NOT NULL,
  keywords_json TEXT,
  entities_json TEXT,
  source_object_ids_json TEXT,
  sample_policy TEXT,
  coverage_estimate REAL,
  confidence REAL,
  folder_score REAL,
  content_hash TEXT,
  created_at TEXT,
  updated_at TEXT
);
```

Useful `kind` values:

```text
root_summary
folder_summary
child_folder_rollup
document_summary
cluster_summary
sample_summary
archive_manifest_summary
negative_summary
```

Important metadata:

```text
coverage_estimate:
  e.g. summary based on 80 sampled chunks out of 12,430

confidence:
  high when folder is coherent
  low when heterogeneous or mostly binary/generated

source_object_ids:
  exact chunks/docs used to create the summary

sample_policy:
  how the representative pack was selected
```

## Query routing algorithm

```text
search(query, scope="all"):

  coarse_hits = search_global_representatives(query, top_k=50)

  candidate_roots = group_by_root(coarse_hits)
  candidate_scopes = group_by_scope(coarse_hits)

  deep_results = search_root_indexes(candidate_scopes, top_k=20 each)

  if good_enough(deep_results):
      return answer

  widen:
      search more representatives
      include sibling scopes
      include parent scopes
      include next roots
      increase per-root top_k

  if still weak:
      fallback to broader fanout
```

Initial budget example:

```yaml
search_budget:
  initial_roots: 5
  initial_scopes_per_root: 8
  deep_top_k_per_scope: 20
  widen_roots_step: 5
  max_roots: 30
  max_deep_queries: 100
```

## Final rule set

```text
Source roots are user-approved boundaries.
Index scopes are physical performance units.
Global representatives route queries.
Root-scoped indexes retrieve evidence.
Collection indexes optimize repeated broad scopes.
SQLite is the durable truth.
Lossy summaries guide search but never prove absence.
```

## Implementation order

```text
1. Inventory scan and safeguard planning
2. Root/scope candidate scoring
3. Root-scoped FTS/LanceDB indexing
4. Summary node table in SQLite
5. Lossy folder/root summaries from stratified samples
6. Global representative FTS index
7. Global representative LanceDB index
8. Multi-resolution query router
9. Widening loop and confidence logic
10. Query usage tracking
11. Materialized collection index promotion
```

Minimal useful version:

```text
SQLite + root indexes + folder summaries + global representative FTS
```

Then add LanceDB representatives, widening logic, and materialized collections later.

## One-sentence principle

Use lossy global summaries as a cheap map, root-scoped indexes as the evidence layer, and materialized collection indexes only when repeated query behavior proves that a broader physical index is worth it.
::: 

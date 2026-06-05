# Dependencies

This page documents the Python dependencies declared in
[pyproject.toml](../pyproject.toml). Dependency groups are intentionally split
so lightweight CLI and catalog work can be reviewed before installing Docling,
Tantivy, LanceDB, or embedding stacks.

## Runtime And Optional Dependencies

| Dependency | Group | Description | Why selected | Closest alternatives |
| --- | --- | --- | --- | --- |
| `hatchling` | build-system | Build backend for packaging the Python project. | Selected because it is a lightweight modern PEP 517 backend and supports simple `src/` package builds with forced-included contract files. | `setuptools`, `flit_core`, `pdm-backend`. |
| `orjson` | base | Fast JSON serialization/deserialization library. | Selected for structured JSON/JSONL command output where speed and deterministic byte output matter for large reports. | Python `json` for zero dependency; `ujson` for another fast JSON option. |
| `pydantic` | base | Data validation and typed model library. | Selected for manifest, config, command output, and catalog-row validation once runtime behavior is implemented. | `dataclasses` plus manual validation; `attrs` plus `cattrs`; `msgspec`. |
| `PyYAML` | base | YAML parser and emitter. | Selected because repo contracts and config files are YAML (`catalog.yaml`, `config/*.yaml`, `store_templates.yaml`). | `ruamel.yaml` for round-trip editing; TOML/JSON if YAML is later narrowed. |
| `rich` | base | Terminal formatting and diagnostics library. | Selected for future human-readable diagnostics while keeping JSON/JSONL as the machine interface. | Plain stdout/stderr; `textual` for full TUI workflows. |
| `typer` | base | CLI framework built on Click and type hints. | Selected as the intended ergonomic command framework after the current stdlib scaffold is reviewed. | `argparse` for zero dependency; `click` for lower-level control. |
| `zstandard` | base | Zstandard compression bindings. | Selected for compressed Docling artifacts and blob storage with better speed/ratio tradeoffs than gzip. | `gzip` from stdlib; `lz4` for faster/lower-ratio compression. |
| `docling` | `docling` extra | Document conversion and structural parsing library. | Selected because the project is centered on preserving Docling parse artifacts and normalized document objects. | Marker, Unstructured, Apache Tika, direct PDF/DOCX parsers. |
| `tantivy` | `fts` extra | Python bindings for the Tantivy full-text search engine. | Selected for owned local BM25/FTS index islands with explicit schema and lifecycle control. | SQLite FTS5, Whoosh, OpenSearch, LanceDB native FTS. |
| `lancedb` | `semantic` extra | Embedded vector database backed by Lance/Arrow data. | Selected for local semantic index islands with vector search and scope-level store management. | Qdrant local/server, Chroma, FAISS, sqlite-vec. |
| `numpy` | `semantic` extra | Array and numerical computing library. | Selected because vector embeddings and LanceDB integrations commonly operate on NumPy arrays. | Python lists for tiny tests; PyTorch tensors when using heavy models. |
| `pyarrow` | `semantic` extra | Apache Arrow data library. | Selected because LanceDB uses Arrow-compatible tabular/vector data under the hood. | Polars/DuckDB for analytics, but not a LanceDB replacement. |
| `fastembed` | `embeddings` extra | Lightweight local embedding runtime from Qdrant. | Selected as the first practical local embedding option for folder-scale indexing without a heavyweight transformer stack. | SentenceTransformers, OpenAI embeddings, model2vec. |
| `sentence-transformers` | `heavy-embeddings` extra | Transformer embedding model library. | Selected as an optional higher-quality local embedding path when dependency weight and runtime cost are acceptable. | FastEmbed for lighter local use; OpenAI or other remote embedding APIs if policy permits. |

## Development Dependencies

| Dependency | Group | Description | Why selected | Closest alternatives |
| --- | --- | --- | --- | --- |
| `pytest` | dev | Python test runner. | Selected as the default test harness for CLI, catalog, and fixture-driven behavior. | `unittest` from stdlib; `nose2`. |
| `ruff` | dev | Fast Python linter and formatter. | Selected to keep style and static checks fast enough for frequent CLI iteration. | `black` plus `flake8`; `pylint`; `pyright` for type-focused checks. |

## Extra Groups

| Extra | Contains | Intended use |
| --- | --- | --- |
| `docling` | `docling` | Enable document parsing features. |
| `fts` | `tantivy` | Enable local full-text index islands. |
| `semantic` | `lancedb`, `numpy`, `pyarrow` | Enable local vector store islands. |
| `embeddings` | `fastembed` | Enable the default lightweight local embedding path. |
| `heavy-embeddings` | `sentence-transformers` | Enable heavier local embedding models. |
| `all` | Docling, FTS, semantic, and embedding packages | Enable the practical full local stack for integration testing. |

The current CLI scaffold intentionally uses only the Python standard library at
runtime. The dependencies above define the intended package contract for later
implementation phases.

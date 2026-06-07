# Model Runtime Plan

This repo separates Python packages, model weights, local model services, and
retrieval stores.

- Python packages are declared in `pyproject.toml`.
- Model profiles are configuration, not catalog tables.
- Model weights are local-only by default and may be downloaded on first use by
  Docling, RapidOCR, FastEmbed, SentenceTransformers, or a local model service.
- Remote hosted model calls are not a default path for this repo.
- Planned local REST model access is limited to OpenAI-compatible local servers
  and Ollama.

## Current Policy

| Rule | Binding Direction |
| --- | --- |
| Local first | Parsing, OCR, embeddings, reranking, and future generation/enrichment use local Python libraries or local services by default. |
| No implicit remote calls | Hosted APIs are not used unless a future caller explicitly adds policy and configuration for them. |
| No implicit huge pulls | The CLI should report missing large models and let the user install them deliberately. |
| Config over flags | Stable model defaults live in `config/parser.yaml` and `config/embeddings.yaml`; CLI flags override only narrow execution choices. |
| Catalog stays lean | Model profiles, provider settings, and model caches are not SQLite catalog tables. |

## Model Surfaces

| Surface | Task | Current Status | Default | Weight Location | Python Dependency | Runtime Style |
| --- | --- | --- | --- | --- | --- | --- |
| Docling parse profile | Text extraction, PDF/DOCX/HTML/Markdown conversion, structure extraction | Implemented | `docling_ocr` for omitted `--profile` | Docling/RapidOCR caches and package-managed model paths | `docling` | Python API |
| Docling OCR | OCR for scanned or low-text PDFs | Implemented through Docling profile | `docling_ocr` | RapidOCR/Docling model cache | `docling`, RapidOCR transitive deps | Python API |
| Docling table/layout models | Layout and table structure extraction | Implemented when enabled by profile | Enabled in `docling_ocr` and `docling_default` | Docling model cache/package cache | `docling` | Python API |
| Docling picture classification/description | Figure classification and visual description | Planned, disabled by current profiles | Disabled | Docling/vision model cache or local REST service | `docling`; future local service deps | Python API or local REST |
| FTS ranking | Lexical BM25 retrieval | Implemented | `text_default_en` | No model weights | `tantivy` | Native library via Python binding |
| Embeddings | Chunk and query vectors for semantic search | Implemented | `fastembed_bge_small_en_v1_5` | `.documents-manager/models/fastembed/` | `fastembed`, `numpy` | Python API |
| Vector store | Semantic nearest-neighbor retrieval | Implemented | Semantic store per folder root | `.documents-manager/semantic/<embedding_profile>/<scope_id>.lancedb/` | `lancedb`, `pyarrow` | Embedded DB |
| Hybrid fusion | Merge FTS and semantic results | Implemented | RRF, no model | No model weights | Existing FTS + semantic deps | In-process formula |
| Reranking | Reorder top hybrid candidates | Partially implemented | Disabled | Ollama model store for optional Ollama mode; future FastEmbed or SentenceTransformers cache | Ollama outside uv; future `fastembed` or `sentence-transformers` | Local REST or Python API |
| Local REST enrichment | Future local LLM/VLM use for captions, summaries, or extraction | Planned | Disabled | Service-managed local model store | Client dependency if needed | OpenAI-compatible local REST or Ollama |

## Install Profiles

| Install Profile | Command | Enables | Model Weights |
| --- | --- | --- | --- |
| Base/catalog | `uv pip install -e .` | Catalog, scan, result files, config parsing | None |
| Docling | `uv pip install -e ".[docling]"` | Parse and OCR profiles | Docling/RapidOCR may download or initialize weights on first OCR/layout run |
| FTS | `uv pip install -e ".[fts]"` | Tantivy BM25 indexes and text search | None |
| Semantic | `uv pip install -e ".[semantic,embeddings]"` | LanceDB vector stores and FastEmbed embeddings | FastEmbed downloads configured embedding model on first use |
| Heavy local models | `uv pip install -e ".[heavy-embeddings]"` | SentenceTransformers embeddings/rerankers | Hugging Face/SentenceTransformers cache |
| Full local stack | `uv pip install -e ".[all]"` | Practical integration stack | All enabled model families may download weights on first use |

## Current Profiles

### Docling Parser Profiles

| Profile | Tier | OCR | Table Structure | Picture Classification | Picture Description | Use When | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `docling_fast_text` | Small / fastest | Off | Off | Off | Off | Text-heavy PDFs, Markdown, HTML, DOCX, and quick tests | Implemented |
| `docling_default` | Medium / balanced | Auto | On | On | Off | General parsing when OCR need is uncertain | Implemented |
| `docling_ocr` | Medium / OCR-first | On | On | On | Off | Scanned PDFs or documents where text extraction may be poor | Implemented and default |
| `docling_visual_enriched` | Large / visual enrichment | On | On | On | Local VLM captions | Figures, diagrams, chart descriptions, or visual search enrichment | Planned |
| `docling_table_heavy` | Large / structure-first | Auto or On | On with stricter table settings | Optional | Off | Dense financial statements, forms, or reports where tables dominate | Planned |

### Docling Runtime Controls

| Setting | Default | Purpose | CLI Override |
| --- | --- | --- | --- |
| `docling_threads_default` | `2` | Limit CPU inference parallelism on Windows/laptop runs | `--docling-threads` |
| `pdf_batch_size_default` | `1` | Keep OCR/layout batches conservative | `--batch-size` |
| `pdf_queue_max_size_default` | `8` | Bound queued PDF pipeline work | `--queue-size` |
| `document_timeout_seconds_default` | `300` | Stop individual documents that hang too long | `--document-timeout` |
| `max_num_pages_default` | `null` | Optional page-count safeguard | `--max-pages` |
| `max_file_size_bytes_default` | `null` | Optional file-size safeguard | `--max-file-size` |

## Embeddings

Profiles live in `config/embeddings.yaml`.

| Profile | Provider | Model | Dimension | Tier | Use Case | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `fastembed_bge_small_en_v1_5` | FastEmbed | `BAAI/bge-small-en-v1.5` | 384 | Fast / strong small | Default folder-scale semantic indexing | Implemented |
| `model2vec_potion_base_32m` | Model2Vec | `minishlab/potion-base-32M` | TBD | Static fastest | Very cheap draft embedding or low-resource tests | Planned |
| `sentence_transformers_bge_base_en_v1_5` | SentenceTransformers | `BAAI/bge-base-en-v1.5` | 768 | Higher quality / slower | Smaller or higher-value corpora where quality beats speed | Planned |

## Reranking Plan

Hybrid V1 uses rank fusion first, without a reranker:

```text
rrf_score = 1 / (k + fts_rank) + 1 / (k + semantic_rank)
```

Use `k = 60` unless tests show a better local default.

Reranking is local-only and opt-in.

| Mode | Candidate | Dependency | Input | Output | Pros | Tradeoff | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `none` | No reranker | None | FTS + semantic ranks | RRF score | Fast, deterministic, no extra model | Less precise top ordering | Implemented default |
| `fastembed` | FastEmbed reranker if available in installed version | `fastembed` | Query plus top candidate texts | Rerank score | Reuses lighter local stack | Model availability/version must be checked | Planned |
| `sentence_transformers` | Cross-encoder reranker | `sentence-transformers` | Query plus top candidate texts | Rerank score | Usually stronger top-k ordering | Heavier dependency and slower CPU runs | Planned |
| `local_rest_openai_compatible` | Local OpenAI-compatible rerank or score endpoint | Local service | Query plus candidates | Rerank score or ordered candidates | Keeps model outside Python process | Needs explicit local service config | Planned |
| `ollama` | Ollama local model ranking prompt | Ollama outside uv | Query plus top candidates | Ordered candidate IDs | Easy local model manager | Slower and less deterministic for scoring | Implemented optional, never default |

Remote hosted reranking is intentionally excluded from the default roadmap.

## Local REST Model Access

Local REST support is planned for enrichment and reranking cases where running a
model inside the Python process is not ideal.

| Provider Type | Example Endpoint Shape | Supported Purpose | Default? | Notes |
| --- | --- | --- | --- | --- |
| OpenAI-compatible local server | `http://localhost:<port>/v1/...` | Future local reranking, captions, summaries, extraction | No | Only local endpoints are in scope by default. Hosted OpenAI-compatible providers require explicit future policy. |
| Ollama | `http://localhost:11434/...` | Optional hybrid reranking; future local VLM/LLM enrichment | No | The CLI checks local endpoint shape and reports missing model configuration; it does not silently pull large models. |
| Direct Transformers service | Custom local service | Experimental local VLM/LLM serving | No | Prefer OpenAI-compatible local REST or Ollama before custom protocols. |

## Task Matrix

| Task | Preferred Current Path | Local Alternatives | Planned Extensions | Not Default |
| --- | --- | --- | --- | --- |
| Text extraction | Docling Python API | Direct PDF/DOCX parsers for diagnostics | More complete Docling object normalization | Hosted conversion APIs |
| OCR | Docling OCR profile | RapidOCR settings through Docling | Profile-specific OCR tiers | Cloud OCR by default |
| Table extraction | Docling table structure | Manual table parsers for specific formats | Table-heavy parsing profile | Storing all Docling JSON nodes in SQL |
| FTS | Tantivy BM25 | SQLite FTS5 as fallback candidate | Hybrid search | OpenSearch by default |
| Semantic retrieval | FastEmbed + LanceDB | SentenceTransformers + LanceDB | Multiple embedding profiles per scope | Remote embedding APIs |
| Hybrid ranking | RRF formula | Weighted score normalization | Optional local rerankers | Remote reranking |
| Captioning / figure enrichment | Not enabled | Docling picture description if local model is configured | Local REST VLM via Ollama/OpenAI-compatible server | Hosted VLM by default |

## Cache Locations

| Cache | Location | Owner | Notes |
| --- | --- | --- | --- |
| Workspace storage root | `.documents-manager/` | This CLI | Generated storage under the caller workspace. |
| SQLite catalog | `.documents-manager/catalog/catalog.sqlite` | This CLI | Current-state metadata and registry rows. |
| FastEmbed models | `.documents-manager/models/fastembed/` | This CLI/FastEmbed | Used by semantic indexing and semantic search. |
| Semantic stores | `.documents-manager/semantic/<embedding_profile>/<scope_id>.lancedb/` | This CLI | One store per folder root and embedding profile. |
| FTS indexes | `.documents-manager/fts/<fts_profile>/<scope_id>/` | This CLI | One FTS island per folder root and FTS profile. |
| Docling/RapidOCR model caches | Package or library cache locations | Docling/RapidOCR | May vary by dependency version and platform. |
| Hugging Face cache | User HF cache unless overridden by dependency | FastEmbed/SentenceTransformers | Windows may warn about disabled symlink optimization. |
| Ollama models | Ollama-managed model store | Ollama | Planned local service path; installs outside uv. |

## Selection Guidance

| Situation | Recommended Choice | Reason |
| --- | --- | --- |
| First parse of unknown PDFs | `docling_ocr` | Most robust default for scanned or mixed PDFs. |
| Fast smoke test | `docling_fast_text` | Avoids OCR/table cost while testing plumbing. |
| First semantic index | `fastembed_bge_small_en_v1_5` | Already implemented, 384-dimensional, fast enough for folder roots. |
| Higher-quality semantic pass | `sentence_transformers_bge_base_en_v1_5` | Planned heavier local profile for selected corpora. |
| First hybrid search | `documents-manager search hybrid "<query>"` with RRF and no reranker | Stable, explainable, no model dependency. |
| Local LLM rerank trial | `documents-manager search hybrid "<query>" --rerank ollama --ollama-model <model>` | Keeps reranking opt-in and local-only. |
| Better top-10 ordering | Local reranker after RRF candidate collection | Limits model cost to a small candidate set. |
| Visual figure understanding | Local REST VLM or Docling picture description profile | Keep heavy vision models outside default parse path. |

## Open Model Decisions

| Decision | Current Proposal | Status |
| --- | --- | --- |
| Hybrid V1 ranking | Reciprocal Rank Fusion over FTS and semantic ranks | Implemented |
| Reranker default | No reranker by default; optional local Ollama available, `fastembed` and `sentence_transformers` still planned | Partially implemented |
| Local REST protocol | OpenAI-compatible local endpoint first, Ollama also planned | Planned |
| Remote providers | Not part of default policy | Excluded unless future caller policy explicitly adds them |
| Docling visual profile | Add only after base object extraction and search are stable | Planned |
| Multiple embeddings per scope | Registry can support multiple `embedding_profile` stores; default remains one | Planned |

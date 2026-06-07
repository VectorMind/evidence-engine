# Models

Every model this engine uses, in one table. Sizes are approximate on-disk
weights. **Access** says how the model runs:

- **Native** — loaded in-process through a Python library installed as a
  `pyproject.toml` extra. Weights download once to a local cache on first use.
- **External** — served by a separate local process (Ollama or an
  OpenAI-compatible local server) that the CLI calls over local REST. The CLI
  never pulls these automatically; it reports what is missing.

No model runs as a hosted/remote call by default.

## Model Table

| Task | Model | Size | Access | Library / Service | Status | Usage |
| --- | --- | --- | --- | --- | --- | --- |
| **OCR** | RapidOCR (PP-OCRv4 mobile) | ~15 MB | Native | `docling` (RapidOCR) | Implemented | Reads text from scanned or low-text PDFs and images. On by default in `docling_ocr`. |
| **Layout** | Docling layout model | ~150 MB | Native | `docling` | Implemented | Detects page regions (headings, paragraphs, lists, figures) so structure survives parsing. |
| **Tables** | Docling TableFormer | ~200 MB | Native | `docling` | Implemented | Recovers table cell structure into typed table objects. |
| **Picture description (VLM)** | local VLM, see VLM list below | 0.5–11 B | External | Ollama / OpenAI-compatible local server | Planned (`docling_visual_enriched`) | Captions figures, diagrams, and charts for visual search enrichment. |
| **Embeddings (default)** | `BAAI/bge-small-en-v1.5` | ~130 MB · 384-dim | Native | `fastembed` | Implemented | Default chunk + query vectors for folder-scale semantic search. |
| **Embeddings (draft)** | `minishlab/potion-base-32M` | ~120 MB · static | Native | `model2vec` | Planned | Very high-throughput cheap draft embedding for low-resource tests. |
| **Embeddings (quality)** | `BAAI/bge-base-en-v1.5` | ~440 MB · 768-dim | Native | `sentence-transformers` | Planned | Higher-quality, slower pass for smaller or higher-value corpora. |
| **Lexical ranking** | BM25 (no weights) | — | Native | `tantivy` | Implemented | Full-text scoring for `search text`. Not a learned model. |
| **Hybrid fusion** | RRF (no weights) | — | Native | in-process | Implemented | Merges text + semantic ranks (`rrf = Σ 1/(k+rank)`, `k=60`). Not a learned model. |
| **Reranking** | cross-encoder, e.g. `ms-marco-MiniLM-L-6-v2` | ~90 MB | Native | `fastembed` / `sentence-transformers` | Planned | Reorders the top hybrid candidates for sharper top-k. |
| **Reranking (external)** | any local Ollama / REST model | varies | External | Ollama / local REST | Optional, never default | Same role as above when run as a local service instead of in-process. |

## VLM Candidates (picture description / visual enrichment)

Run through Ollama when available, otherwise direct Transformers. None are
pulled automatically. Listed smallest to largest.

| Model | Size | Tier | Usage |
| --- | --- | --- | --- |
| SmolVLM2 | 0.5 B | Laptop | Cheap captions and simple object hints. |
| Granite Vision 3.2 | 2 B | Laptop / light station | Docling-aligned picture descriptions and structured observations. |
| Qwen2.5-VL | 3 B | Station | General captions and object/label candidates. |
| MiniCPM-V 2.6 | 8 B | Station | Stronger visual understanding and OCR-like tasks. |
| InternVL3 / Llama 3.2 Vision | 8–11 B | Station stress | Upper-bound quality test on 8 GB GPU / 32 GB RAM. |

## Defaults and Policy

- Stable model choices live in [config/parser.yaml](../config/parser.yaml) and
  [config/embeddings.yaml](../config/embeddings.yaml), not in CLI flags and not
  in the SQLite catalog.
- Default parse profile: `docling_ocr`. Default embedding profile:
  `fastembed_bge_small_en_v1_5`. Default reranker: none.
- Weights cache under `.cache/coev/models/` (FastEmbed) or the library's
  own Hugging Face / Docling / Ollama cache.
- The CLI reports missing large models rather than downloading them implicitly.

## Parser Profiles

| Profile | OCR | Tables | Picture description | Use when | Status |
| --- | --- | --- | --- | --- | --- |
| `docling_fast_text` | off | off | off | Text-heavy PDFs, Markdown, HTML, DOCX, quick tests | Implemented |
| `docling_default` | auto | on | off | General parsing when OCR need is uncertain | Implemented |
| `docling_ocr` | on | on | off | Scanned or low-text PDFs (default) | Implemented |
| `docling_visual_enriched` | on | on | local VLM | Figures, diagrams, charts, visual search | Planned |

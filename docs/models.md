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
| **Image embeddings** | SigLIP 2 base | ~400 MB · ~768-dim | Native | open-clip / transformers (torch) | Planned | Visual `search image`: image→image and text→image, one model on laptop + station. |
| **Lexical ranking** | BM25 (no weights) | — | Native | `tantivy` | Implemented | Full-text scoring for `search text`. Not a learned model. |
| **Hybrid fusion** | RRF (no weights) | — | Native | in-process | Implemented | Merges text + semantic ranks (`rrf = Σ 1/(k+rank)`, `k=60`). Not a learned model. |
| **Reranking** | cross-encoder, e.g. `ms-marco-MiniLM-L-6-v2` | ~90 MB | Native | `fastembed` / `sentence-transformers` | Planned | Reorders the top hybrid candidates for sharper top-k. |
| **Reranking (external)** | any local Ollama / REST model | varies | External | Ollama / local REST | Optional, never default | Same role as above when run as a local service instead of in-process. |

## VLM Candidates (picture description / visual enrichment)

Run through Ollama when a model is in its registry, otherwise direct
Transformers. None are pulled automatically. The `Ollama tag` column is the
exact `ollama pull <tag>` name; smallest to largest.

| Model | Size | Tier | Ollama tag | Notes |
| --- | --- | --- | --- | --- |
| Moondream 2 | 1.8 B | Laptop | `moondream` | Smallest Ollama vision model; quick captions and object hints. |
| Granite Vision 3.2 | 2 B | Laptop | `granite3.2-vision` | Docling-aligned picture descriptions and structured observations. |
| Qwen2.5-VL | 3 / 7 B | Laptop / station | `qwen2.5vl:3b`, `qwen2.5vl:7b` | General captions and object/label candidates. |
| Gemma 3 (multimodal) | 4 B | Laptop | `gemma3:4b` | Strong small general-purpose multimodal. |
| LLaVA-Phi3 | 3.8 B | Laptop | `llava-phi3` | Compact LLaVA variant. |
| MiniCPM-V 2.6 | 8 B | Station | `minicpm-v` | Stronger visual understanding and OCR-like tasks. |
| Llama 3.2 Vision | 11 B | Station | `llama3.2-vision` | Upper-bound quality on 8 GB GPU / 32 GB RAM. |
| SmolVLM2 | 0.25–2.2 B | Laptop | — | **Not in the Ollama registry.** Run via Hugging Face Transformers or llama.cpp directly. |

SmolVLM2 is not packaged by Ollama, so it cannot be `ollama pull`ed. For an
Ollama-only laptop path, the smallest option is `moondream`, then
`granite3.2-vision`.

## Image Embeddings (visual search)

`search image` uses **SigLIP 2 base** as a single model across tiers: the same
weights run on laptop (CPU, slower) and station (GPU, fast) — only device and
batch size change. It gives **image→image** (the primary use) and **text→image**
in the same vector space. Embedding an image is fast (~tens of ms), unlike VLM
captioning, so this is the scalable backbone for media findability.

DINOv2 was considered for stronger pure-visual recall but dropped because it has
no text tower (no text→image) and would need a second per-tier model.

Dependency note: SigLIP 2 runs through `open-clip` / `transformers`, which pull
**torch**. To keep the default laptop install lean (FastEmbed/ONNX, no torch),
these live in a dedicated opt-in extra rather than the `laptop` default.

### Captioning cost (measured)

On a CPU-bound dev laptop, `granite3.2-vision` captioning runs ~90–150 s per
image, and **downscaling the input barely changes it** — the cost is model
generation, not image size. So `media describe` is opt-in and selective
(`--limit`), never a default bulk pass: ~345 photos would take hours. Bulk
description needs a GPU, a smaller/faster model (try `moondream`), or a
background batch. `media describe` still downscales to `--max-edge 1024` by
default to cap memory and keep OCR-grade text legible.

## Defaults and Policy

- Stable model choices live in [config/parser.yaml](../config/parser.yaml) and
  [config/embeddings.yaml](../config/embeddings.yaml), not in CLI flags and not
  in the SQLite catalog.
- Default parse profile: `docling_ocr`. Default embedding profile:
  `fastembed_bge_small_en_v1_5`. Default reranker: none.
- Weights cache under `.cache/even/models/` (FastEmbed) or the library's
  own Hugging Face / Docling / Ollama cache.
- The CLI reports missing large models rather than downloading them implicitly.

## Parser Profiles

| Profile | OCR | Tables | Picture description | Use when | Status |
| --- | --- | --- | --- | --- | --- |
| `docling_fast_text` | off | off | off | Text-heavy PDFs, Markdown, HTML, DOCX, quick tests | Implemented |
| `docling_default` | auto | on | off | General parsing when OCR need is uncertain | Implemented |
| `docling_ocr` | on | on | off | Scanned or low-text PDFs (default) | Implemented |
| `docling_visual_enriched` | on | on | local VLM | Figures, diagrams, charts, visual search | Planned |

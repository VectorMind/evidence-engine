# Test Proof: Entity Layer Runtime And Reference Example

Status: Done. All exit criteria verified.

## Automated Tests

```powershell
uv run pytest tests/test_entities.py tests/test_entity_cli.py -q
# 13 passed (test_entities.py) + 6 passed (test_entity_cli.py)

uv run pytest -q
# 90 passed (full suite, no regressions)
```

Coverage highlights:

- `add_entity` validation (`invalid_entity_kind`, `invalid_entity_status`),
  defaults (`entity_status=proposed`, `review_status=unreviewed`).
- `list_entities` filtering by kind.
- `add_alias` requires an existing entity; normalizes lookup text.
- `add_link` refuses a ref that does not resolve (`evidence_ref_not_found`)
  and accepts one that does (built via a real `media inspect` run in the test).
- `review_target` updates the entity's `review_status`; updates a link's
  `link_status` **without changing the referenced evidence row**
  (`resolve_ref` snapshot compared before/after); reports
  `unknown_target_kind` / `target_not_found` for bad input.
- `find_entity_evidence` requires an existing entity.
- `resolve_ref` returns `None` for malformed refs, unknown tables, and a
  wrong dataset prefix.
- CLI contract: argument parsing (`entity add`, mutually-exclusive
  `entity review` decision flags), full add→alias→show round trip through
  `main()`, `entity list --kind` filtering, `entity review --accept`, and
  `entity link` rejecting an unresolvable ref with exit code 1.

## Worked Reference Example (Milestone 1 Confirmed)

Fixture: `tests/fixtures/entities-basic/` — a synthetic organization
("Northwind Salvage") mentioned under two spellings
(`northwind-field-report.pdf`, a hand-built minimal PDF matching the existing
`parse-basic/dummy.pdf` construction) plus a filename-hinted synthetic image
(`northwind_salvage_pier9.png`). Matches all four selection criteria in
`plan.md`: synthetic/redaction-safe, spans two evidence types (document +
media), runs on the `laptop` extra, small enough for one scripted session.

Run from a clean, isolated `EVEN_CACHE` (a scratch directory with no local
`.env`, so it cannot collide with a real workspace):

```powershell
$env:EVEN_CACHE = "<scratch>/.cache"
$fixture = "<repo>/tests/fixtures/entities-basic"

even catalog create
even docs parse $fixture --profile docling_fast_text
even media inspect $fixture
even index scope $fixture
even search text "Northwind Salvage"
```

**Actual result:** `docs parse` parsed 1 document (1 object written);
`media inspect` wrote 1 asset + 1 thumbnail; `search text "Northwind Salvage"`
returned 2 hits, each already carrying a resolvable `ref`:

- `corpus_cache.document_objects.obj_...` — the PDF paragraph mentioning both
  spellings.
- `corpus_cache.media_assets.asset_...` — the image, matched by filename.

Entity workflow, continued in the same cache:

```powershell
even entity add "Northwind Salvage" --kind organization `
  --description "Synthetic salvage vendor for the entity-runtime worked example."
# -> entity_id = ent_...

even entity alias ent_... "N.W. Salvage" --kind abbreviation

even entity find ent_... "Northwind Salvage"
# -> both hits above, each with `ref`

even entity link ent_... corpus_cache.document_objects.obj_... --role mention
even entity link ent_... corpus_cache.media_assets.asset_... --role visual_match

even entity review link_<doc-link> --accept
even entity review link_<image-link> --reject

even entity show ent_...
```

**Actual result:** `entity show` returned the entity plus one alias, two
links, hydrated:

- the `mention` link resolved to the live `document_objects` row
  (`text_preview` containing both spellings), `link_status: accepted`.
- the `visual_match` link resolved to the live `media_assets` row
  (`media_class: image`, thumbnail wired), `link_status: rejected`.

No copies were stored — only the `evidence_ref` string; `evidence` in the
output is populated by reading the live row at `show` time, exactly per the
Reference Contract.

**Cross-modal probe and `--propose`,** after also building the image store
and routing map:

```powershell
even index scope $fixture --image
even index routing $fixture
even entity find ent_... "Northwind Salvage warehouse" --image $fixture/northwind_salvage_pier9.png --propose
```

**Actual result:** `status: ok`, `route_trace` present (confirms the
mid-implementation fix — see `implementation.md`), 2 hits, both proposed as
`link_status: proposed` links with matching open `review_tasks`. The probe's
`counts` showed no additional `image_hits_returned` — expected and noted in
the routing feedback memo: a single-scope fixture gives the visual route
nothing to discriminate among. The `--image` argument itself was accepted and
processed without error, proving the plumbing; the routing feedback memo
records this as a fixture-scale limitation, not a code gap.

## Durability Guarantee

Snapshotted `entities`, `entity_evidence_links`, and `review_tasks` as JSON,
then re-ran `docs parse` (no `--force` flag exists, so a plain re-run),
`index scope --force`, `media inspect`, and `index routing --force` over the
same fixture in the same cache. Re-snapshotted and diffed byte-for-byte.

**Actual result:** identical before and after every re-run — confirmed with
a direct Python diff, not just visual inspection:

```text
entities match: True
links match: True
DURABILITY OK across index routing --force too
```

## Reference-Integrity Guard

`even entity link ent_... corpus_cache.document_objects.missing --role mention`
against the same cache returned `status: failed`,
`error_kind: evidence_ref_not_found`, exit code 1 — confirmed both as a unit
test (`test_add_link_rejects_unresolvable_ref`) and live via the CLI.

## Known Gaps

- The cross-modal probe's scope-selection effect is not observably exercised
  end-to-end by this single-scope worked example (see Routing Feedback Memo
  in `implementation.md`, item 3). Its ranking behavior is covered separately
  by `tests/test_routing.py`.
- No merge/dedupe workflow was built or tested (explicitly out of scope).

# Test Proof

## 2026-06-27

### Focused Regression

Command:

```powershell
uv run pytest tests/test_cli_contract.py tests/test_image_search.py -q
```

Result:

- Passed: 14
- Warnings: LanceDB `table_names()` deprecation warnings only.

### Full Suite

Command:

```powershell
uv run pytest -q
```

Result:

- Passed: 69
- Warnings: LanceDB `table_names()` deprecation warnings only.

### Style

Command:

```powershell
uv run ruff check .
```

Result:

- Passed: all checks.

### Live Catalog Cleanup

Command:

```powershell
python <targeted cleanup script>
```

Result:

- Backed up live catalog to
  `C:\Users\wassi\.even\catalog\catalog.sqlite.bak-20260627T161619Z`.
- Deleted 7 explicitly approved incompatible `image_stores` rows.
- Removed 7 matching `.lancedb` directories.
- Remaining `siglip2_base` image stores: 1.
- Remaining incompatible `siglip2_base` image stores: 0.

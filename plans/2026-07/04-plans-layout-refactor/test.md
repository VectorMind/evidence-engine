# Test Proof - Plans Layout Refactor

## Commands

| Command | Expected | Actual |
| --- | --- | --- |
| `Get-ChildItem -Path plans -Recurse -Directory | ForEach-Object { $_.FullName.Substring((Resolve-Path .).Path.Length + 1) }` | Packet directories appear under `plans/YYYY-MM/DD-<slug>/`. | Pass - all existing packets moved under `plans/2026-06/*` and `plans/2026-07/*`. |
| `rg -n 'plans[/\\][0-9]{4}-[0-9]{2}-[0-9]{2}-[A-Za-z0-9-]+|\\.\\./[0-9]{4}-[0-9]{2}-[0-9]{2}-[A-Za-z0-9-]+|\\./[0-9]{4}-[0-9]{2}-[0-9]{2}-[A-Za-z0-9-]+|\\([0-9]{4}-[0-9]{2}-[0-9]{2}-[A-Za-z0-9-]+/' . -g '!node_modules' -g '!dist' -g '!*venv*'` | No stale internal references to the old flat layout remain. | Pass with intentional exception - remaining hits are historical absolute paths to `C:\\dev\\wassfila\\documents-manager\\plans\\2026-06-05-personal-document-index\\...` in archived proof notes. No in-repo packet references still use the old layout. |
| `rg -n 'plans/YYYY-MM-DD-<slug>|YYYY-MM-DD-<slug>' AGENTS.md WORKFLOW.md plans\README.md README.md` | No workflow docs still prescribe the flat layout. | Pass - no matches. |

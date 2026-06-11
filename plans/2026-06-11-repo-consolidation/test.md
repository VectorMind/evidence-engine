# Test Proof: Repository Consolidation

This is a planning/consolidation packet; proof is document review and
content-migration checks rather than runtime behavior.

## Planned Checks

| Phase | Check |
| --- | --- |
| 1 | Reconciled layer-4 schema parses as YAML; every table from both private catalog.yaml files is either present, merged, or listed in the redundancy mapping; no personal facts (paths, names) appear in the public file. |
| 2 | `docs/models.md` contains the face-model table and benchmark policy; no dependency added to pyproject.toml (`git diff pyproject.toml` empty). |
| 3 | Private knowledge base contains the source maps and real config values; grep the evidence-engine working tree for real path fragments (e.g. user-profile paths) returns only pre-existing occurrences, none added by this packet. |
| 4 | Both private repos show archived status on GitHub and remain private; pointer READMEs in place. |

## Results

Not executed yet — plan awaiting review.

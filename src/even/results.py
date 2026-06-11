"""Structured command result files under the caller workspace root."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
from typing import Any

from even.paths import reports_root, results_root, workspace_root


@dataclass
class CommandRun:
    command: str
    run_id: str
    started_at: str
    result_dir: Path
    result_uri: str

    @classmethod
    def start(cls, command: str) -> "CommandRun":
        now = _utc_now()
        command_slug = _command_slug(command)
        run_name = f"{now.strftime('%H%M%S')}-{command_slug}"
        result_dir = results_root() / now.strftime("%Y.%m") / now.strftime("%d") / run_name
        suffix = 2
        while result_dir.exists():
            result_dir = (
                results_root()
                / now.strftime("%Y.%m")
                / now.strftime("%d")
                / f"{run_name}-{suffix}"
            )
            suffix += 1
        result_dir.mkdir(parents=True, exist_ok=True)
        run = cls(
            command=command,
            run_id=result_dir.name,
            started_at=_iso(now),
            result_dir=result_dir,
            result_uri=_relative_uri(result_dir),
        )
        run.event("started", {"command": command})
        return run

    def event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        event = {
            "run_id": self.run_id,
            "command": self.command,
            "event_type": event_type,
            "created_at": _iso(_utc_now()),
        }
        if payload:
            event.update(payload)
        events_path = self.result_dir / "events.jsonl"
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def finish(self, payload: dict[str, Any], *, write_report: bool = False) -> dict[str, Any]:
        final_payload = dict(payload)
        final_payload["run_id"] = self.run_id
        final_payload["started_at"] = self.started_at
        final_payload["completed_at"] = _iso(_utc_now())
        final_payload["result_uri"] = self.result_uri
        summary_uri = self.result_uri + "/summary.md"
        final_payload["summary_uri"] = summary_uri
        result_path = self.result_dir / "result.json"
        result_path.write_text(
            json.dumps(final_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        summary_text = render_summary_markdown(final_payload)
        (self.result_dir / "summary.md").write_text(summary_text, encoding="utf-8")
        if write_report:
            report_uri = self.write_html_report(final_payload, summary_text)
            final_payload["report_uri"] = report_uri
            result_path.write_text(
                json.dumps(final_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        self.event("completed", {"status": final_payload.get("status", "unknown")})
        return final_payload

    def write_html_report(self, payload: dict[str, Any], summary_text: str) -> str:
        report_dir = reports_root() / Path(self.result_uri).relative_to("results")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "report.html"
        report_path.write_text(
            render_html_report(payload, summary_text),
            encoding="utf-8",
        )
        return _relative_uri(report_path)


def render_console_summary(payload: dict[str, Any]) -> str:
    command = payload.get("command", "command")
    if command == "sources scan":
        return _scan_console_summary(payload)
    if command == "docs parse":
        return _parse_console_summary(payload)
    if command == "index scope":
        return _index_console_summary(payload)
    if command == "search text":
        return _search_console_summary(payload)
    if command == "search semantic":
        return _search_console_summary(payload)
    if command == "search hybrid":
        return _search_console_summary(payload)
    if str(command).startswith("catalog "):
        return _catalog_console_summary(payload)
    if command == "health":
        return _health_console_summary(payload)
    return _generic_console_summary(payload)


def render_summary_markdown(payload: dict[str, Any]) -> str:
    if payload.get("command") == "sources scan":
        return _scan_summary_markdown(payload)
    if payload.get("command") == "docs parse":
        return _parse_summary_markdown(payload)
    if payload.get("command") == "index scope":
        return _index_summary_markdown(payload)
    if payload.get("command") == "search text":
        return _search_summary_markdown(payload)
    if payload.get("command") == "search semantic":
        return _search_summary_markdown(payload)
    if payload.get("command") == "search hybrid":
        return _search_summary_markdown(payload)
    return _generic_summary_markdown(payload)


def render_html_report(payload: dict[str, Any], summary_text: str) -> str:
    if payload.get("command") == "docs parse":
        return _parse_html_report(payload, summary_text)

    title = _report_title(payload)
    counts = payload.get("counts", {})
    statistics = payload.get("statistics", {})
    bars = _bar_chart_html(counts)
    extension_stats = statistics.get("extension_stats", [])
    overview = _html_table(
        [
            ("Status", str(payload.get("status", "unknown"))),
            ("Command", str(payload.get("command", "unknown"))),
            ("Root", str(payload.get("root_label", "n/a"))),
            ("Store policy", str(payload.get("store_policy", "n/a"))),
            ("Files", str(statistics.get("file_count", counts.get("files_matched", 0)))),
            ("Folders", str(statistics.get("folder_count", counts.get("folders_seen", 0)))),
            ("Total size", _format_bytes(statistics.get("total_size_bytes", counts.get("bytes_matched", 0)))),
            ("Average file size", _format_bytes(statistics.get("average_file_size_bytes", 0))),
            ("Result", str(payload.get("result_uri", "n/a"))),
        ]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; color: #1f2933; }}
    main {{ max-width: 1040px; margin: 0 auto; }}
    h1 {{ font-size: 28px; margin-bottom: 4px; }}
    h2 {{ font-size: 18px; margin-top: 28px; }}
    p {{ line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 20px; }}
    th, td {{ border-bottom: 1px solid #d8dee4; padding: 8px 10px; text-align: left; }}
    th {{ background: #f6f8fa; font-weight: 600; }}
    .muted {{ color: #687782; }}
    .bar {{ display: grid; grid-template-columns: 180px 1fr 90px; gap: 10px; align-items: center; margin: 8px 0; }}
    .track {{ height: 14px; background: #eef1f4; border-radius: 4px; overflow: hidden; }}
    .fill {{ height: 100%; background: #2f6f73; }}
    .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px; margin: 14px 0 22px; }}
    .chart {{ border: 1px solid #d8dee4; border-radius: 8px; padding: 16px; }}
    .chart svg {{ display: block; margin: 8px auto 12px; max-width: 230px; }}
    .legend {{ display: grid; gap: 5px; font-size: 13px; }}
    .swatch {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; }}
    code {{ background: #f6f8fa; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
<main>
  <h1>{html.escape(title)}</h1>
  <p class="muted">Generated by even from a structured command result.</p>
  <h2>Overview</h2>
  {overview}
  <h2>Inventory Signals</h2>
  {bars}
  <h2>Extension Mix</h2>
  <div class="charts">
    {_pie_chart_html(extension_stats, "file_count", "By File Count")}
    {_pie_chart_html(extension_stats, "total_size_bytes", "By Total Size")}
  </div>
  {_extension_table_html(extension_stats)}
  <h2>Summary</h2>
  {_markdown_excerpt_html(summary_text)}
</main>
</body>
</html>
"""


def _scan_summary_markdown(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    statistics = payload.get("statistics", {})
    extension_rows = statistics.get("extension_stats", [])[:10]
    lines = [
        f"# Scan Summary: {payload.get('root_label', 'folder')}",
        "",
        _scan_lede(payload),
        "",
        "## Overview",
        "",
        _markdown_table(
            ["Metric", "Value"],
            [
                ("Status", payload.get("status", "unknown")),
                ("Root label", payload.get("root_label", "n/a")),
                ("Store policy", payload.get("store_policy", "n/a")),
                ("Folders", statistics.get("folder_count", _count(counts, "folders_seen"))),
                ("Files", statistics.get("file_count", _count(counts, "files_matched"))),
                ("Total size", _format_bytes(statistics.get("total_size_bytes", _count(counts, "bytes_matched")))),
                ("Average file size", _format_bytes(statistics.get("average_file_size_bytes", 0))),
                ("Minimum file size", _format_bytes(statistics.get("min_file_size_bytes", 0))),
                ("Maximum file size", _format_bytes(statistics.get("max_file_size_bytes", 0))),
                ("Result URI", payload.get("result_uri", "n/a")),
            ],
        ),
        "",
        "## Inventory Changes",
        "",
        _markdown_table(
            ["Change", "Count"],
            [
                ("Created", _count(counts, "items_created")),
                ("Changed", _count(counts, "items_changed")),
                ("Unchanged", _count(counts, "items_unchanged")),
                ("Deleted", _count(counts, "items_deleted")),
                ("Skipped unmatched", _count(counts, "files_skipped_unmatched")),
                ("Failures", _count(counts, "paths_failed")),
            ],
        ),
        "",
    ]
    if extension_rows:
        lines.extend(
            [
                "## Top Extensions",
                "",
                _markdown_table(
                    ["Extension", "Files", "Total Size", "Average Size"],
                    [
                        (
                            row["extension"],
                            row["file_count"],
                            _format_bytes(row["total_size_bytes"]),
                            _format_bytes(row["average_file_size_bytes"]),
                        )
                        for row in extension_rows
                    ],
                ),
                "",
            ]
        )
    if payload.get("status") == "deferred":
        safeguard = payload.get("safeguard", {})
        lines.extend(
            [
                "## Safeguard",
                "",
                f"The scan stopped at `{safeguard.get('kind', 'unknown')}` "
                f"limit `{safeguard.get('limit', 'n/a')}`.",
                "",
            ]
        )
    return "\n".join(lines)


def _generic_summary_markdown(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# Command Summary: {payload.get('command', 'unknown')}",
            "",
            _markdown_table(
                ["Metric", "Value"],
                [
                    ("Status", payload.get("status", "unknown")),
                    ("Command", payload.get("command", "unknown")),
                    ("Result URI", payload.get("result_uri", "n/a")),
                ],
            ),
            "",
        ]
    )


def _parse_summary_markdown(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    lines = [
        f"# Parse Summary: {payload.get('root_label', 'folder')}",
        "",
        _parse_lede(payload),
        "",
        "## Overview",
        "",
        _markdown_table(
            ["Metric", "Value"],
            [
                ("Status", payload.get("status", "unknown")),
                ("Root label", payload.get("root_label", "n/a")),
                ("Parser profile", payload.get("parser_profile", "n/a")),
                ("OCR requested", payload.get("ocr_requested", "n/a")),
                ("Auto scan", payload.get("auto_scan_status", "n/a")),
                ("Planned documents", counts.get("documents_planned", 0)),
                ("Parsed documents", counts.get("documents_parsed", 0)),
                ("Partial documents", counts.get("documents_partial", 0)),
                ("Unchanged documents", counts.get("documents_unchanged", 0)),
                ("Failed documents", counts.get("documents_failed", 0)),
                ("Artifacts written", counts.get("artifacts_written", 0)),
                ("Objects written", counts.get("objects_written", 0)),
                ("Result URI", payload.get("result_uri", "n/a")),
            ],
        ),
        "",
    ]
    failures = payload.get("failures", [])
    if failures:
        lines.extend(
            [
                "## Failure Summary",
                "",
                _markdown_table(
                    ["Error", "Documents"],
                    _failure_summary_rows(failures),
                ),
                "",
                "## Failure Details",
                "",
                _markdown_table(
                    ["Document", "Error", "Category", "Detail", "Suggested Action"],
                    _failure_detail_rows(failures),
                ),
                "",
            ]
        )
        if payload.get("failures_truncated"):
            lines.extend(
                [
                    (
                        f"Only {payload.get('failure_count_returned', len(failures))} "
                        f"of {payload.get('failure_count_total', len(failures))} "
                        "failures are shown."
                    ),
                    "",
                ]
            )
    partials = payload.get("partial_documents", [])
    if partials:
        lines.extend(
            [
                "## Partial Documents",
                "",
                _markdown_table(
                    ["Document", "Docling Status", "Warnings"],
                    _partial_detail_rows(partials),
                ),
                "",
            ]
        )
    elif payload.get("error_kind"):
        lines.extend(
            [
                "## Failure",
                "",
                _markdown_table(
                    ["Field", "Value"],
                    [
                        ("Error kind", payload.get("error_kind")),
                        ("Message", payload.get("message", "")),
                    ],
                ),
                "",
            ]
        )
    return "\n".join(lines)


def _index_summary_markdown(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    backend = payload.get("index_backend", "fts")
    profile_label = "Embedding profile" if backend == "semantic" else "FTS profile"
    profile_value = (
        payload.get("embedding_profile", "n/a")
        if backend == "semantic"
        else payload.get("fts_profile", "n/a")
    )
    location_label = "Store URI" if backend == "semantic" else "Index URI"
    location_value = (
        payload.get("store_uri", "n/a")
        if backend == "semantic"
        else payload.get("index_uri", "n/a")
    )
    lines = [
        f"# Index Summary: {payload.get('root_label', 'folder')}",
        "",
        _index_lede(payload),
        "",
        "## Overview",
        "",
        _markdown_table(
            ["Metric", "Value"],
            [
                ("Status", payload.get("status", "unknown")),
                ("Backend", backend),
                ("Root label", payload.get("root_label", "n/a")),
                (profile_label, profile_value),
                ("Chunk profile", payload.get("chunk_profile", "n/a")),
                ("Index status", payload.get("index_status", "n/a")),
                ("Documents indexed", counts.get("documents_indexed", 0)),
                ("Chunks planned", counts.get("chunks_planned", 0)),
                ("Chunks indexed", counts.get("chunks_indexed", 0)),
                ("Chunks unchanged", counts.get("chunks_unchanged", 0)),
                (location_label, location_value),
                ("Result URI", payload.get("result_uri", "n/a")),
            ],
        ),
        "",
    ]
    if payload.get("error_kind"):
        lines.extend(
            [
                "## Note",
                "",
                _markdown_table(
                    ["Field", "Value"],
                    [
                        ("Error kind", payload.get("error_kind")),
                        ("Message", payload.get("message", "")),
                    ],
                ),
                "",
            ]
        )
    return "\n".join(lines)


def _search_summary_markdown(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    hits = payload.get("hits", [])[:10]
    is_hybrid = payload.get("search_backend") == "hybrid"
    ranking = payload.get("ranking", {})
    rerank = ranking.get("rerank", {})
    overview_rows: list[tuple[str, Any]] = [
        ("Status", payload.get("status", "unknown")),
        ("Query", payload.get("query", "")),
        ("Indexes searched", counts.get("indexes_searched", 0)),
        ("Index failures", counts.get("index_failures", 0)),
        ("Hits returned", counts.get("hits_returned", 0)),
        ("Result URI", payload.get("result_uri", "n/a")),
    ]
    if is_hybrid:
        overview_rows = [
            ("Status", payload.get("status", "unknown")),
            ("Query", payload.get("query", "")),
            ("Fusion", ranking.get("fusion", "rrf")),
            ("RRF k", ranking.get("rrf_k", "n/a")),
            ("Rerank", f"{rerank.get('mode', 'none')} / {rerank.get('status', 'n/a')}"),
            ("FTS indexes", counts.get("fts_indexes_searched", 0)),
            ("Semantic indexes", counts.get("semantic_indexes_searched", 0)),
            ("FTS candidates", counts.get("fts_hits", 0)),
            ("Semantic candidates", counts.get("semantic_hits", 0)),
            ("Fused candidates", counts.get("candidates_fused", 0)),
            ("Hits returned", counts.get("hits_returned", 0)),
            ("Result URI", payload.get("result_uri", "n/a")),
        ]
    lines = [
        f"# Search Summary: {payload.get('query', '')}",
        "",
        _search_lede(payload),
        "",
        "## Overview",
        "",
        _markdown_table(["Metric", "Value"], overview_rows),
        "",
    ]
    if hits:
        headers = ["Score", "Root", "Path", "Title", "Preview"]
        rows: list[tuple[Any, ...]] = [
            (
                f"{float(hit.get('score', 0)):.4f}",
                hit.get("root_label", ""),
                hit.get("relative_path", ""),
                hit.get("title", ""),
                _truncate(hit.get("body_preview", ""), 120),
            )
            for hit in hits
        ]
        if is_hybrid:
            headers = [
                "Score",
                "Backends",
                "FTS Rank",
                "Semantic Rank",
                "Root",
                "Path",
                "Title",
                "Preview",
            ]
            rows = [
                (
                    f"{float(hit.get('score', 0)):.4f}",
                    "+".join(hit.get("matched_backends", [])),
                    hit.get("fts_rank", ""),
                    hit.get("semantic_rank", ""),
                    hit.get("root_label", ""),
                    hit.get("relative_path", ""),
                    hit.get("title", ""),
                    _truncate(hit.get("body_preview", ""), 100),
                )
                for hit in hits
            ]
        lines.extend(
            [
                "## Top Hits",
                "",
                _markdown_table(headers, rows),
                "",
            ]
        )
    return "\n".join(lines)


def _parse_lede(payload: dict[str, Any]) -> str:
    status = payload.get("status", "unknown")
    counts = payload.get("counts", {})
    if status in {"ok", "partial"}:
        return (
            f"The parse run used `{payload.get('parser_profile', 'unknown')}` and "
            f"parsed {counts.get('documents_parsed', 0)} of "
            f"{counts.get('documents_planned', 0)} planned documents."
        )
    if payload.get("error_kind") == "docling_missing":
        return "Docling is not installed, so parsing could not start."
    return f"The parse run finished with status `{status}`."


def _index_lede(payload: dict[str, Any]) -> str:
    status = payload.get("status", "unknown")
    counts = payload.get("counts", {})
    backend = payload.get("index_backend", "fts")
    if status == "ok":
        return (
            f"The {backend} index contains {counts.get('chunks_planned', 0)} chunks "
            f"from {counts.get('documents_indexed', 0)} parsed documents."
        )
    if payload.get("error_kind") == "no_parsed_documents":
        return "No parsed document objects were available to index."
    return f"The index run finished with status `{status}`."


def _search_lede(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    backend = payload.get("search_backend", "FTS")
    if backend == "hybrid":
        return (
            f"The hybrid search fused {counts.get('candidates_fused', 0)} candidates "
            f"from {counts.get('fts_hits', 0)} FTS hits and "
            f"{counts.get('semantic_hits', 0)} semantic hits."
        )
    return (
        f"The search returned {counts.get('hits_returned', 0)} hits across "
        f"{counts.get('indexes_searched', 0)} current {backend} indexes."
    )


def _failure_summary_rows(failures: list[dict[str, Any]]) -> list[tuple[str, Any]]:
    grouped: dict[str, int] = {}
    for failure in failures:
        key = str(failure.get("error_kind", "unknown"))
        grouped[key] = grouped.get(key, 0) + 1
    return sorted(grouped.items())


def _failure_detail_rows(failures: list[dict[str, Any]]) -> list[tuple[str, Any, Any, Any, Any]]:
    rows: list[tuple[str, Any, Any, Any, Any]] = []
    for failure in failures:
        rows.append(
            (
                str(failure.get("relative_path", "n/a")),
                str(failure.get("error_kind", "unknown")),
                str(failure.get("error_category", "unknown")),
                str(
                    failure.get("message")
                    or failure.get("redacted_detail")
                    or failure.get("diagnosis")
                    or ""
                ),
                str(failure.get("suggested_action", "")),
            )
        )
    return rows


def _partial_detail_rows(partials: list[dict[str, Any]]) -> list[tuple[str, Any, Any]]:
    rows: list[tuple[str, Any, Any]] = []
    for partial in partials:
        warnings = partial.get("warnings", [])
        if isinstance(warnings, list):
            warning_text = "; ".join(str(warning) for warning in warnings[:3])
        else:
            warning_text = str(warnings)
        rows.append(
            (
                str(partial.get("relative_path", "n/a")),
                str(partial.get("docling_status", "partial_success")),
                warning_text or "Docling returned partial success.",
            )
        )
    return rows


def _parse_html_report(payload: dict[str, Any], summary_text: str) -> str:
    title = _report_title(payload)
    counts = payload.get("counts", {})
    failures = payload.get("failures", [])
    partials = payload.get("partial_documents", [])
    overview = _html_table(
        [
            ("Status", str(payload.get("status", "unknown"))),
            ("Command", str(payload.get("command", "unknown"))),
            ("Root", str(payload.get("root_label", "n/a"))),
            ("Parser profile", str(payload.get("parser_profile", "n/a"))),
            ("OCR requested", str(payload.get("ocr_requested", "n/a"))),
            ("Planned documents", str(counts.get("documents_planned", 0))),
            ("Parsed documents", str(counts.get("documents_parsed", 0))),
            ("Partial documents", str(counts.get("documents_partial", 0))),
            ("Unchanged documents", str(counts.get("documents_unchanged", 0))),
            ("Failed documents", str(counts.get("documents_failed", 0))),
            ("Result", str(payload.get("result_uri", "n/a"))),
        ]
    )
    failure_summary = (
        _html_data_table(["Error", "Documents"], _failure_summary_rows(failures))
        if failures
        else "<p>No document conversion failures were recorded.</p>"
    )
    failure_details = (
        _html_data_table(
            ["Document", "Error", "Category", "Detail", "Suggested Action"],
            _failure_detail_rows(failures),
        )
        if failures
        else ""
    )
    partial_details = (
        _html_data_table(
            ["Document", "Docling Status", "Warnings"],
            _partial_detail_rows(partials),
        )
        if partials
        else "<p>No partial document conversions were recorded.</p>"
    )
    truncated = ""
    if payload.get("failures_truncated"):
        truncated = (
            f"<p class=\"muted\">Showing {html.escape(str(payload.get('failure_count_returned', len(failures))))} "
            f"of {html.escape(str(payload.get('failure_count_total', len(failures))))} failures.</p>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; color: #1f2933; }}
    main {{ max-width: 1120px; margin: 0 auto; }}
    h1 {{ font-size: 28px; margin-bottom: 4px; }}
    h2 {{ font-size: 18px; margin-top: 28px; }}
    p {{ line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 20px; }}
    th, td {{ border-bottom: 1px solid #d8dee4; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f6f8fa; font-weight: 600; }}
    .muted {{ color: #687782; }}
    code {{ background: #f6f8fa; padding: 2px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
<main>
  <h1>{html.escape(title)}</h1>
  <p class="muted">Generated by even from a structured parse result.</p>
  <h2>Overview</h2>
  {overview}
  <h2>Docling Runtime</h2>
  {_runtime_table_html(payload.get("docling_runtime", {}))}
  <h2>Failure Summary</h2>
  {failure_summary}
  {truncated}
  <h2>Failure Details</h2>
  {failure_details or "<p>No failure details to show.</p>"}
  <h2>Partial Documents</h2>
  {partial_details}
  <h2>Summary</h2>
  {_markdown_excerpt_html(summary_text)}
</main>
</body>
</html>
"""


def _scan_console_summary(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    statistics = payload.get("statistics", {})
    lines = [
        f"sources scan: {payload.get('status', 'unknown')} ({payload.get('root_label', 'folder')})",
        (
            f"files {statistics.get('file_count', _count(counts, 'files_matched'))}, "
            f"folders {statistics.get('folder_count', _count(counts, 'folders_seen'))}, "
            f"size {_format_bytes(statistics.get('total_size_bytes', _count(counts, 'bytes_matched')))}"
        ),
        (
            f"changes created {_count(counts, 'items_created')}, "
            f"changed {_count(counts, 'items_changed')}, "
            f"unchanged {_count(counts, 'items_unchanged')}, "
            f"failed {_count(counts, 'paths_failed')}"
        ),
    ]
    lines.extend(_artifact_links(payload))
    return "\n".join(lines)


def _parse_console_summary(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    lines = [
        f"docs parse: {payload.get('status', 'unknown')} ({payload.get('root_label', 'folder')})",
        (
            f"profile {payload.get('parser_profile', 'n/a')}, "
            f"ocr {payload.get('ocr_requested', 'n/a')}, "
            f"auto scan {payload.get('auto_scan_status', 'n/a')}"
        ),
        (
            f"documents parsed {counts.get('documents_parsed', 0)}/"
            f"{counts.get('documents_planned', 0)}, "
            f"unchanged {counts.get('documents_unchanged', 0)}, "
            f"failed {counts.get('documents_failed', 0)}"
        ),
    ]
    if payload.get("error_kind"):
        lines.append(f"error {payload.get('error_kind')}: {payload.get('message', '')}")
    lines.extend(_artifact_links(payload))
    return "\n".join(lines)


def _index_console_summary(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    backend = payload.get("index_backend", "fts")
    profile = (
        payload.get("embedding_profile", "n/a")
        if backend == "semantic"
        else payload.get("fts_profile", "n/a")
    )
    lines = [
        f"index scope: {payload.get('status', 'unknown')} ({payload.get('root_label', 'folder')})",
        (
            f"backend {backend}, profile {profile}, "
            f"status {payload.get('index_status', 'n/a')}, "
            f"chunks {counts.get('chunks_planned', 0)}, "
            f"documents {counts.get('documents_indexed', 0)}"
        ),
    ]
    if payload.get("store_uri"):
        lines.append(f"store {payload['store_uri']}")
    elif payload.get("index_uri"):
        lines.append(f"index {payload['index_uri']}")
    if payload.get("error_kind"):
        lines.append(f"error {payload.get('error_kind')}: {payload.get('message', '')}")
    lines.extend(_artifact_links(payload))
    return "\n".join(lines)


def _search_console_summary(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    command = payload.get("command", "search text")
    is_hybrid = payload.get("search_backend") == "hybrid"
    lines = [
        f"{command}: {payload.get('status', 'unknown')}",
        (
            f"hits {counts.get('hits_returned', 0)} across "
            f"{counts.get('indexes_searched', 0)} indexes"
        ),
    ]
    if is_hybrid:
        ranking = payload.get("ranking", {})
        rerank = ranking.get("rerank", {})
        lines[1] = (
            f"hits {counts.get('hits_returned', 0)}, "
            f"fused {counts.get('candidates_fused', 0)} candidates "
            f"(fts {counts.get('fts_hits', 0)}, semantic {counts.get('semantic_hits', 0)})"
        )
        lines.append(
            f"ranking {ranking.get('fusion', 'rrf')} k={ranking.get('rrf_k', 'n/a')}, "
            f"rerank {rerank.get('mode', 'none')}/{rerank.get('status', 'n/a')}"
        )
    for index, hit in enumerate(payload.get("hits", [])[:3], start=1):
        title = _truncate(hit.get("title", ""), 42)
        path = _truncate(hit.get("relative_path", ""), 52)
        backend_label = ""
        if is_hybrid:
            backend_label = "+".join(hit.get("matched_backends", [])) + " | "
        lines.append(
            f"{index}. {float(hit.get('score', 0)):.4f} | {backend_label}{path} | {title}"
        )
    if payload.get("message"):
        lines.append(str(payload["message"]))
    lines.extend(_artifact_links(payload))
    return "\n".join(lines)


def _catalog_console_summary(payload: dict[str, Any]) -> str:
    lines = [
        f"{payload.get('command', 'catalog')}: {payload.get('status', 'unknown')}",
        f"catalog {payload.get('catalog_path', 'n/a')}",
    ]
    if "sqlite_user_version" in payload:
        lines.append(f"version {payload.get('sqlite_user_version')}")
    if "table_count" in payload:
        lines.append(f"tables {payload.get('table_count')}")
    return "\n".join(lines)


def _health_console_summary(payload: dict[str, Any]) -> str:
    checks = payload.get("checks", [])
    check_text = ", ".join(
        f"{check.get('name')}={check.get('status')}" for check in checks[:6]
    )
    return "\n".join(
        [
            f"health: {payload.get('status', 'unknown')}",
            f"workspace {payload.get('workspace_root', 'n/a')}",
            f"checks {check_text}" if check_text else "checks n/a",
        ]
    )


def _generic_console_summary(payload: dict[str, Any]) -> str:
    lines = [
        f"{payload.get('command', 'command')}: {payload.get('status', 'unknown')}",
    ]
    if payload.get("message"):
        lines.append(str(payload["message"]))
    lines.extend(_artifact_links(payload))
    return "\n".join(lines)


def _artifact_links(payload: dict[str, Any]) -> list[str]:
    links = []
    if payload.get("result_uri"):
        links.append(f"json {payload['result_uri']}/result.json")
    if payload.get("summary_uri"):
        links.append(f"summary {payload['summary_uri']}")
    if payload.get("report_uri"):
        links.append(f"report {payload['report_uri']}")
    return links


def _scan_lede(payload: dict[str, Any]) -> str:
    counts = payload.get("counts", {})
    statistics = payload.get("statistics", {})
    status = payload.get("status", "unknown")
    if status == "ok":
        return (
            f"The scan completed for `{payload.get('root_label', 'folder')}` with "
            f"{statistics.get('file_count', _count(counts, 'files_matched'))} matching files, "
            f"{_format_bytes(statistics.get('total_size_bytes', _count(counts, 'bytes_matched')))} total size, and "
            f"{_count(counts, 'paths_failed')} path failures."
        )
    if status == "deferred":
        return "The scan was deferred by a configured safeguard before catalog writes."
    return f"The scan finished with status `{status}`."


def _report_title(payload: dict[str, Any]) -> str:
    command = str(payload.get("command", "Command")).title()
    root = payload.get("root_label")
    if root:
        return f"{command} Report - {root}"
    return f"{command} Report"


def _bar_chart_html(counts: dict[str, Any]) -> str:
    keys = [
        "files_matched",
        "folders_seen",
        "items_created",
        "items_changed",
        "items_unchanged",
        "items_deleted",
        "paths_failed",
    ]
    values = [(key, int(counts.get(key, 0) or 0)) for key in keys]
    maximum = max([value for _, value in values] + [1])
    rows = []
    for key, value in values:
        width = int((value / maximum) * 100) if maximum else 0
        label = key.replace("_", " ").title()
        rows.append(
            '<div class="bar">'
            f"<span>{html.escape(label)}</span>"
            '<div class="track">'
            f'<div class="fill" style="width:{width}%"></div>'
            "</div>"
            f"<strong>{value}</strong>"
            "</div>"
        )
    return "\n".join(rows)


def _pie_chart_html(rows: list[dict[str, Any]], metric: str, title: str) -> str:
    slices = _chart_rows(rows, metric)
    if not slices:
        return f'<section class="chart"><h3>{html.escape(title)}</h3><p>No files found.</p></section>'
    total = sum(float(row[metric]) for row in slices)
    radius = 80
    center = 100
    start_angle = -90.0
    paths = []
    legend = []
    colors = [
        "#2f6f73",
        "#8b5cf6",
        "#f59e0b",
        "#ef4444",
        "#2563eb",
        "#10b981",
        "#64748b",
        "#d946ef",
    ]
    for index, row in enumerate(slices):
        value = float(row[metric])
        angle = 360.0 * (value / total) if total else 0
        end_angle = start_angle + angle
        color = colors[index % len(colors)]
        paths.append(_svg_slice(center, center, radius, start_angle, end_angle, color))
        percent = int(round((value / total) * 100)) if total else 0
        value_text = (
            _format_bytes(value) if metric == "total_size_bytes" else str(int(value))
        )
        legend.append(
            "<span>"
            f'<span class="swatch" style="background:{color}"></span>'
            f"{html.escape(str(row['extension']))}: {html.escape(value_text)} ({percent}%)"
            "</span>"
        )
        start_angle = end_angle
    return (
        f'<section class="chart"><h3>{html.escape(title)}</h3>'
        '<svg viewBox="0 0 200 200" role="img">'
        + "".join(paths)
        + "</svg>"
        f'<div class="legend">{"".join(legend)}</div></section>'
    )


def _chart_rows(rows: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    sorted_rows = sorted(rows, key=lambda row: (-float(row.get(metric, 0) or 0), str(row.get("extension", ""))))
    top = [dict(row) for row in sorted_rows[:7] if float(row.get(metric, 0) or 0) > 0]
    rest = sorted_rows[7:]
    other_value = sum(float(row.get(metric, 0) or 0) for row in rest)
    if other_value:
        top.append({"extension": "other", metric: other_value})
    return top


def _svg_slice(
    cx: int, cy: int, radius: int, start_angle: float, end_angle: float, color: str
) -> str:
    if end_angle - start_angle >= 359.99:
        return f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{color}" />'
    start_x, start_y = _polar_to_cartesian(cx, cy, radius, end_angle)
    end_x, end_y = _polar_to_cartesian(cx, cy, radius, start_angle)
    large_arc = 1 if end_angle - start_angle > 180 else 0
    return (
        f'<path d="M {cx} {cy} L {start_x:.3f} {start_y:.3f} '
        f'A {radius} {radius} 0 {large_arc} 0 {end_x:.3f} {end_y:.3f} Z" '
        f'fill="{color}" />'
    )


def _polar_to_cartesian(
    cx: int, cy: int, radius: int, angle_degrees: float
) -> tuple[float, float]:
    import math

    angle_radians = math.radians(angle_degrees)
    return (
        cx + radius * math.cos(angle_radians),
        cy + radius * math.sin(angle_radians),
    )


def _extension_table_html(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>No extension statistics were available.</p>"
    display_rows = rows[:10]
    body = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row['extension']))}</td>"
        f"<td>{int(row['file_count'])}</td>"
        f"<td>{html.escape(_format_bytes(row['total_size_bytes']))}</td>"
        f"<td>{html.escape(_format_bytes(row['average_file_size_bytes']))}</td>"
        "</tr>"
        for row in display_rows
    )
    return (
        "<table><thead><tr><th>Extension</th><th>Files</th>"
        "<th>Total Size</th><th>Average Size</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _markdown_excerpt_html(summary_text: str) -> str:
    paragraphs = []
    for line in summary_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("|") or stripped.startswith("#"):
            continue
        paragraphs.append(f"<p>{html.escape(stripped)}</p>")
        if len(paragraphs) >= 3:
            break
    return "\n".join(paragraphs) or "<p>No narrative summary was available.</p>"


def _html_table(rows: list[tuple[str, str]]) -> str:
    body = "\n".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"
        for label, value in rows
    )
    return f"<table>{body}</table>"


def _html_data_table(headers: list[str], rows: list[tuple[Any, ...]]) -> str:
    header_html = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = "\n".join(
        "<tr>"
        + "".join(f"<td>{html.escape(str(value))}</td>" for value in row)
        + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{body}</tbody></table>"


def _runtime_table_html(runtime: dict[str, Any]) -> str:
    if not runtime:
        return "<p>No runtime settings were recorded.</p>"
    return _html_table(
        [
            (str(key).replace("_", " ").title(), str(value))
            for key, value in sorted(runtime.items())
        ]
    )


def _markdown_table(headers: list[str], rows: list[tuple[str, Any]]) -> str:
    header_line = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    row_lines = [
        "| " + " | ".join(_markdown_cell(value) for value in row) + " |"
        for row in rows
    ]
    return "\n".join([header_line, separator, *row_lines])


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|")


def _count(counts: dict[str, Any], key: str) -> int:
    return int(counts.get(key, 0) or 0)


def _format_bytes(value: Any) -> str:
    if value is None:
        return "n/a"
    size = float(value)
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    unit = units[0]
    for unit in units:
        if abs(size) < 1024 or unit == units[-1]:
            break
        size /= 1024
    if unit == "B":
        return f"{int(size)} {unit}"
    return f"{size:.1f} {unit}"


def _truncate(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _command_slug(command: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", command.lower()).strip("-")
    return slug or "command"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _relative_uri(path: Path) -> str:
    return path.relative_to(workspace_root()).as_posix()

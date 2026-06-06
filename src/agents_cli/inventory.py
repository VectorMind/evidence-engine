"""Folder inventory for source_roots and source_items."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import fnmatch
import hashlib
import mimetypes
import os
from pathlib import Path
import sqlite3
from typing import Any

from agents_cli.catalog import ensure_catalog
from agents_cli.config import load_parser_config
from agents_cli.paths import catalog_path


@dataclass(frozen=True)
class ScanItem:
    source_item_id: str
    parent_source_item_id: str | None
    relative_path: str
    source_uri: str
    item_kind: str
    media_type: str | None
    size_bytes: int | None
    source_mtime: str | None
    source_sha256: str | None


@dataclass(frozen=True)
class ScanOptions:
    max_files: int | None
    max_bytes: int | None
    max_depth: int | None


def scan_folder_to_catalog(path: Path, options: ScanOptions) -> dict[str, Any]:
    """Inventory a folder tree and persist current source rows."""

    root_path = path.expanduser()
    if not root_path.exists():
        return {
            "status": "failed",
            "error_kind": "source_missing",
            "message": "Source folder does not exist.",
        }
    if not root_path.is_dir():
        return {
            "status": "failed",
            "error_kind": "source_not_folder",
            "message": "Source path must be a folder.",
        }

    ensure_report = ensure_catalog()
    if ensure_report["status"] not in {"created", "current", "migrated"}:
        return {
            "status": "failed",
            "error_kind": "catalog_unavailable",
            "catalog_status": ensure_report["status"],
        }

    config = load_parser_config()
    safeguards = config["folder_safeguards"]
    include_globs = safeguards.get("include_globs_default", [])
    exclude_globs = safeguards.get("exclude_globs_default", [])
    follow_symlinks = bool(safeguards.get("follow_symlinks_default", False))
    max_files = options.max_files
    if max_files is None:
        max_files = safeguards.get("max_files_default")
    max_bytes = options.max_bytes
    if max_bytes is None:
        max_bytes = safeguards.get("max_bytes_default")
    max_depth = options.max_depth
    if max_depth is None:
        max_depth = safeguards.get("max_depth_default")

    resolved_root = root_path.resolve()
    now = _iso(_utc_now())
    root_id = _stable_id("root", "folder", _identity_path(resolved_root))
    scope_id = _stable_id("scope", root_id, "root")
    root_label = resolved_root.name or str(resolved_root)

    inventory = _collect_items(
        resolved_root=resolved_root,
        root_id=root_id,
        include_globs=include_globs,
        exclude_globs=exclude_globs,
        follow_symlinks=follow_symlinks,
        max_files=max_files,
        max_bytes=max_bytes,
        max_depth=max_depth,
    )
    if inventory["status"] != "ok":
        return {
            "status": inventory["status"],
            "root_id": root_id,
            "root_label": root_label,
            "scope_id": scope_id,
            "source_uri_redacted": True,
            "safeguard": inventory["safeguard"],
            "counts": inventory["counts"],
            "catalog_ensure": ensure_report["status"],
        }

    write_counts = _write_inventory(
        root_id=root_id,
        root_label=root_label,
        source_uri=str(resolved_root),
        scope_id=scope_id,
        now=now,
        items=inventory["items"],
    )

    return {
        "status": "ok",
        "root_id": root_id,
        "root_label": root_label,
        "scope_id": scope_id,
        "source_kind": "folder",
        "source_uri_redacted": True,
        "scan_mode": config["defaults"].get("scan_mode", "folder_tree"),
        "store_policy": config["defaults"].get("store_policy", "one_per_root"),
        "catalog_ensure": ensure_report["status"],
        "counts": {
            **inventory["counts"],
            **write_counts,
        },
    }


def _collect_items(
    *,
    resolved_root: Path,
    root_id: str,
    include_globs: list[str],
    exclude_globs: list[str],
    follow_symlinks: bool,
    max_files: int | None,
    max_bytes: int | None,
    max_depth: int | None,
) -> dict[str, Any]:
    items: list[ScanItem] = []
    counts = {
        "folders_seen": 0,
        "files_matched": 0,
        "bytes_matched": 0,
        "files_skipped_unmatched": 0,
        "paths_skipped_excluded": 0,
        "paths_skipped_symlink": 0,
        "paths_failed": 0,
    }

    for current_dir, dirnames, filenames in os.walk(
        resolved_root, followlinks=follow_symlinks
    ):
        current_path = Path(current_dir)
        rel_dir = _relative_posix(current_path, resolved_root)
        current_depth = 0 if rel_dir == "." else len(rel_dir.split("/"))
        if max_depth is not None and current_depth > max_depth:
            dirnames[:] = []
            continue

        pruned_dirs: list[str] = []
        for dirname in dirnames:
            child = current_path / dirname
            child_rel = _relative_posix(child, resolved_root)
            child_depth = 0 if child_rel == "." else len(child_rel.split("/"))
            if not follow_symlinks and child.is_symlink():
                counts["paths_skipped_symlink"] += 1
                continue
            if max_depth is not None and child_depth > max_depth:
                counts["paths_skipped_excluded"] += 1
                continue
            if _matches_any(child_rel, exclude_globs):
                counts["paths_skipped_excluded"] += 1
                continue
            pruned_dirs.append(dirname)
        dirnames[:] = pruned_dirs

        folder_item = _folder_item(root_id, current_path, resolved_root)
        if folder_item:
            items.append(folder_item)
            counts["folders_seen"] += 1

        for filename in filenames:
            file_path = current_path / filename
            rel_file = _relative_posix(file_path, resolved_root)
            if not follow_symlinks and file_path.is_symlink():
                counts["paths_skipped_symlink"] += 1
                continue
            if _matches_any(rel_file, exclude_globs):
                counts["paths_skipped_excluded"] += 1
                continue
            if include_globs and not _matches_any(rel_file, include_globs):
                counts["files_skipped_unmatched"] += 1
                continue

            try:
                stat = file_path.stat()
            except OSError:
                counts["paths_failed"] += 1
                continue

            next_file_count = counts["files_matched"] + 1
            next_byte_count = counts["bytes_matched"] + int(stat.st_size)
            if max_files is not None and next_file_count > max_files:
                return {
                    "status": "deferred",
                    "safeguard": {
                        "kind": "max_files",
                        "limit": max_files,
                        "needed_at_least": next_file_count,
                    },
                    "counts": counts,
                }
            if max_bytes is not None and next_byte_count > max_bytes:
                return {
                    "status": "deferred",
                    "safeguard": {
                        "kind": "max_bytes",
                        "limit": max_bytes,
                        "needed_at_least": next_byte_count,
                    },
                    "counts": counts,
                }

            try:
                source_sha256 = _sha256_file(file_path)
            except OSError:
                counts["paths_failed"] += 1
                continue

            counts["files_matched"] = next_file_count
            counts["bytes_matched"] = next_byte_count
            items.append(
                ScanItem(
                    source_item_id=_item_id(root_id, rel_file, "file"),
                    parent_source_item_id=_parent_folder_id(root_id, rel_file),
                    relative_path=rel_file,
                    source_uri=str(file_path),
                    item_kind="file",
                    media_type=_media_type(file_path),
                    size_bytes=int(stat.st_size),
                    source_mtime=_mtime(stat.st_mtime),
                    source_sha256=source_sha256,
                )
            )

    return {"status": "ok", "items": items, "counts": counts}


def _write_inventory(
    *,
    root_id: str,
    root_label: str,
    source_uri: str,
    scope_id: str,
    now: str,
    items: list[ScanItem],
) -> dict[str, int]:
    seen_ids = {item.source_item_id for item in items}
    counts = {
        "items_created": 0,
        "items_changed": 0,
        "items_unchanged": 0,
        "items_deleted": 0,
    }

    ordered_items = sorted(
        items,
        key=lambda item: (
            0 if item.item_kind == "folder" else 1,
            item.relative_path.count("/"),
            item.relative_path,
        ),
    )

    with sqlite3.connect(catalog_path()) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        existing_root = conn.execute(
            'SELECT first_seen_at FROM "source_roots" WHERE root_id = ?', (root_id,)
        ).fetchone()
        if existing_root:
            conn.execute(
                """
                UPDATE "source_roots"
                SET root_label = ?, source_kind = ?, source_uri = ?,
                    policy_profile = ?, last_seen_at = ?
                WHERE root_id = ?
                """,
                (root_label, "folder", source_uri, "default", now, root_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO "source_roots"
                (root_id, root_label, source_kind, source_uri, policy_profile,
                 first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (root_id, root_label, "folder", source_uri, "default", now, now),
            )

        existing_items = {
            row[0]: {
                "size_bytes": row[1],
                "source_mtime": row[2],
                "source_sha256": row[3],
                "item_kind": row[4],
            }
            for row in conn.execute(
                """
                SELECT source_item_id, size_bytes, source_mtime, source_sha256,
                       item_kind
                FROM "source_items"
                WHERE root_id = ?
                """,
                (root_id,),
            ).fetchall()
        }

        for item in ordered_items:
            previous = existing_items.get(item.source_item_id)
            status = _inventory_status(previous, item)
            if status == "current":
                counts["items_created"] += 1
                conn.execute(
                    """
                    INSERT INTO "source_items"
                    (source_item_id, root_id, parent_source_item_id, relative_path,
                     source_uri, item_kind, media_type, size_bytes, source_mtime,
                     source_sha256, inventory_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.source_item_id,
                        root_id,
                        item.parent_source_item_id,
                        item.relative_path,
                        item.source_uri,
                        item.item_kind,
                        item.media_type,
                        item.size_bytes,
                        item.source_mtime,
                        item.source_sha256,
                        status,
                    ),
                )
            else:
                if status == "changed":
                    counts["items_changed"] += 1
                else:
                    counts["items_unchanged"] += 1
                conn.execute(
                    """
                    UPDATE "source_items"
                    SET parent_source_item_id = ?, relative_path = ?,
                        source_uri = ?, item_kind = ?, media_type = ?,
                        size_bytes = ?, source_mtime = ?, source_sha256 = ?,
                        inventory_status = ?
                    WHERE source_item_id = ?
                    """,
                    (
                        item.parent_source_item_id,
                        item.relative_path,
                        item.source_uri,
                        item.item_kind,
                        item.media_type,
                        item.size_bytes,
                        item.source_mtime,
                        item.source_sha256,
                        status,
                        item.source_item_id,
                    ),
                )

        deleted_ids = [
            source_item_id
            for source_item_id in existing_items
            if source_item_id not in seen_ids
        ]
        if deleted_ids:
            conn.executemany(
                'UPDATE "source_items" SET inventory_status = ? WHERE source_item_id = ?',
                [("deleted", source_item_id) for source_item_id in deleted_ids],
            )
            counts["items_deleted"] = len(deleted_ids)

        root_folder_id = _item_id(root_id, ".", "folder")
        conn.execute(
            """
            INSERT INTO "index_scopes"
            (scope_id, root_id, source_item_id, scope_kind, relative_path, status,
             updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope_id) DO UPDATE SET
                root_id = excluded.root_id,
                source_item_id = excluded.source_item_id,
                scope_kind = excluded.scope_kind,
                relative_path = excluded.relative_path,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (scope_id, root_id, root_folder_id, "root", ".", "active", now),
        )
        conn.commit()

    return counts


def _folder_item(root_id: str, folder_path: Path, resolved_root: Path) -> ScanItem | None:
    rel_folder = _relative_posix(folder_path, resolved_root)
    try:
        stat = folder_path.stat()
    except OSError:
        return None
    return ScanItem(
        source_item_id=_item_id(root_id, rel_folder, "folder"),
        parent_source_item_id=None
        if rel_folder == "."
        else _parent_folder_id(root_id, rel_folder),
        relative_path=rel_folder,
        source_uri=str(folder_path),
        item_kind="folder",
        media_type="inode/directory",
        size_bytes=None,
        source_mtime=_mtime(stat.st_mtime),
        source_sha256=None,
    )


def _inventory_status(previous: dict[str, Any] | None, item: ScanItem) -> str:
    if previous is None:
        return "current"
    if (
        previous["size_bytes"] == item.size_bytes
        and previous["source_mtime"] == item.source_mtime
        and previous["source_sha256"] == item.source_sha256
        and previous["item_kind"] == item.item_kind
    ):
        return "unchanged"
    return "changed"


def _matches_any(relative_path: str, patterns: list[str]) -> bool:
    rel = relative_path.replace("\\", "/").strip("/").lower()
    for pattern in patterns:
        normalized = pattern.replace("\\", "/").strip("/").lower()
        variants = {normalized}
        if normalized.startswith("**/"):
            variants.add(normalized[3:])
        if normalized.endswith("/**"):
            variants.add(normalized[:-3])
        if normalized.startswith("**/") and normalized.endswith("/**"):
            variants.add(normalized[3:-3])
        for variant in variants:
            if fnmatch.fnmatchcase(rel, variant):
                return True
    return False


def _relative_posix(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    value = relative.as_posix()
    return value if value else "."


def _parent_folder_id(root_id: str, relative_path: str) -> str:
    parent = Path(relative_path).parent.as_posix()
    if parent in {"", "."}:
        parent = "."
    return _item_id(root_id, parent, "folder")


def _item_id(root_id: str, relative_path: str, kind: str) -> str:
    normalized = relative_path.replace("\\", "/").strip("/") or "."
    return _stable_id("src", root_id, kind, normalized.lower())


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _identity_path(path: Path) -> str:
    return str(path).replace("\\", "/").lower()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _mtime(timestamp: float) -> str:
    return _iso(datetime.fromtimestamp(timestamp, timezone.utc))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")

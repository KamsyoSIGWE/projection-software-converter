from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import zlib
import zipfile
from pathlib import Path
from typing import Any


ZIP_LOCAL_HEADER = b"PK\x03\x04"
ZIP_CENTRAL_DIRECTORY = b"PK\x01\x02"
ZIP_EOCD = b"PK\x05\x06"


def _scan_local_headers(path: str | Path) -> list[dict[str, Any]]:
    data = Path(path).read_bytes()
    pos = 0
    members: list[dict[str, Any]] = []
    while pos + 30 <= len(data) and data[pos : pos + 4] == ZIP_LOCAL_HEADER:
        header = data[pos : pos + 30]
        _sig, ver, flag, method, mtime, mdate, crc, comp, uncomp, nlen, xlen = struct.unpack("<IHHHHHIIIHH", header)
        name = data[pos + 30 : pos + 30 + nlen].decode("utf-8", errors="replace")
        start = pos + 30 + nlen + xlen
        payload = data[start : start + comp]
        content = zlib.decompress(payload, -15) if method == 8 else payload
        members.append(
            {
                "name": name,
                "version_needed": ver,
                "flags": flag,
                "compression": method,
                "mtime": mtime,
                "mdate": mdate,
                "crc32": crc,
                "compressed_size": comp,
                "uncompressed_size": uncomp,
                "extra_length": xlen,
                "content": content,
            }
        )
        pos = start + comp
    return members


def _scan_central_directory(path: str | Path) -> dict[str, Any]:
    data = Path(path).read_bytes()
    eocd_offset = data.rfind(ZIP_EOCD)
    if eocd_offset == -1 or eocd_offset + 22 > len(data):
        return {"entries": [], "eocd": None}
    (
        _sig,
        disk_number,
        start_disk_number,
        entries_on_disk,
        total_entries,
        central_directory_size,
        central_directory_offset,
        comment_length,
    ) = struct.unpack("<IHHHHIIH", data[eocd_offset : eocd_offset + 22])
    entries: list[dict[str, Any]] = []
    pos = central_directory_offset
    while pos + 46 <= len(data) and data[pos : pos + 4] == ZIP_CENTRAL_DIRECTORY:
        (
            _sig,
            ver_made,
            ver_needed,
            flags,
            method,
            mtime,
            mdate,
            crc,
            comp,
            uncomp,
            nlen,
            xlen,
            clen,
            disk_start,
            iattr,
            eattr,
            local_offset,
        ) = struct.unpack("<IHHHHHHIIIHHHHHII", data[pos : pos + 46])
        name = data[pos + 46 : pos + 46 + nlen].decode("utf-8", errors="replace")
        entries.append(
            {
                "name": name,
                "version_made_by": ver_made,
                "version_needed": ver_needed,
                "flags": flags,
                "compression": method,
                "mtime": mtime,
                "mdate": mdate,
                "crc32": crc,
                "compressed_size": comp,
                "uncompressed_size": uncomp,
                "extra_length": xlen,
                "comment_length": clen,
                "disk_number_start": disk_start,
                "internal_attributes": iattr,
                "external_attributes": eattr,
                "local_header_offset": local_offset,
            }
        )
        pos += 46 + nlen + xlen + clen
    return {
        "entries": entries,
        "eocd": {
            "disk_number": disk_number,
            "start_disk_number": start_disk_number,
            "entries_on_disk": entries_on_disk,
            "total_entries": total_entries,
            "central_directory_size": central_directory_size,
            "central_directory_offset": central_directory_offset,
            "comment_length": comment_length,
            "offset": eocd_offset,
        },
    }


def _zipfile_readability(path: str | Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as zf:
            return {"ok": True, "names": zf.namelist()}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _scan_with_7zip(path: str | Path) -> list[dict[str, Any]]:
    exe = shutil.which("7z") or shutil.which("7za")
    if not exe:
        raise FileNotFoundError("7-Zip executable not found")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        completed = subprocess.run([exe, "x", "-y", f"-o{tmp_path}", str(path)], capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "7-Zip extraction failed")
        members: list[dict[str, Any]] = []
        for file_path in sorted(p for p in tmp_path.rglob("*") if p.is_file()):
            members.append(
                {
                    "name": str(file_path.relative_to(tmp_path)).replace("/", "\\"),
                    "version_needed": None,
                    "flags": None,
                    "compression": None,
                    "mtime": None,
                    "mdate": None,
                    "crc32": None,
                    "compressed_size": file_path.stat().st_size,
                    "uncompressed_size": file_path.stat().st_size,
                    "extra_length": None,
                    "content": file_path.read_bytes(),
                }
            )
        return members


def extract_ewsx_members(path: str | Path) -> dict[str, Any]:
    local_error: str | None = None
    try:
        members = _scan_local_headers(path)
        if members:
            return {"container_mode": "local-header", "members": members}
    except Exception as exc:
        local_error = str(exc)

    members = _scan_with_7zip(path)
    return {"container_mode": "7zip-fallback", "members": members, "local_header_error": local_error}


def _blob_summary(value: bytes) -> dict[str, Any]:
    return {
        "length": len(value),
        "sha256": hashlib.sha256(value).hexdigest(),
    }


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        normalized[key] = _blob_summary(value) if isinstance(value, bytes) else value
    return normalized


def _fetch_table_rows(cur: sqlite3.Cursor, table: str) -> list[dict[str, Any]]:
    columns = [row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if not columns:
        return []
    order_column = "rowid" if "rowid" in columns else columns[0]
    rows = [dict(row) for row in cur.execute(f"SELECT * FROM {table} ORDER BY {order_column}").fetchall()]
    return [_normalize_row(row) for row in rows]


def inspect_sqlite_bytes(db_bytes: bytes, include_rows: bool = False) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        tmp.write(db_bytes)
        db_path = Path(tmp.name)
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
        indexes = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name").fetchall()]
        table_info: dict[str, Any] = {}
        for table in tables:
            cols = [{"name": row[1], "type": row[2]} for row in cur.execute(f"PRAGMA table_info({table})").fetchall()]
            row_count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            entry: dict[str, Any] = {"columns": cols, "row_count": row_count}
            if include_rows:
                entry["rows"] = _fetch_table_rows(cur, table)
            table_info[table] = entry
        schema_sql = {
            row["name"]: row["sql"]
            for row in cur.execute("SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name").fetchall()
        }
        info_rows = [dict(row) for row in cur.execute("SELECT * FROM info").fetchall()] if "info" in tables else []
        return {
            "page_size": cur.execute("PRAGMA page_size").fetchone()[0],
            "schema_objects": cur.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0],
            "tables": tables,
            "indexes": indexes,
            "table_info": table_info,
            "schema_sql": schema_sql,
            "info_rows": info_rows,
        }
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)


def inspect_ewsx(path: str | Path) -> dict[str, Any]:
    bundle = extract_ewsx_members(path)
    members = bundle["members"]
    db_member = next((member for member in members if Path(member["name"]).name.lower() == "main.db"), None)
    db_info = inspect_sqlite_bytes(db_member["content"]) if db_member else None
    central_directory = _scan_central_directory(path)
    zipfile_readability = _zipfile_readability(path)
    member_summaries = [
        {k: v for k, v in member.items() if k != "content"}
        for member in members
    ]
    return {
        "path": str(path),
        "container_mode": bundle["container_mode"],
        "local_header_error": bundle.get("local_header_error"),
        "member_count": len(members),
        "members": member_summaries,
        "central_directory": central_directory,
        "zipfile_readability": zipfile_readability,
        "sqlite": db_info,
    }


def _member_metadata_diff(valid_members: list[dict[str, Any]], generated_members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    max_len = max(len(valid_members), len(generated_members))
    for index in range(max_len):
        valid_member = valid_members[index] if index < len(valid_members) else None
        generated_member = generated_members[index] if index < len(generated_members) else None
        if valid_member is None or generated_member is None:
            differences.append({"index": index, "valid": valid_member, "generated": generated_member})
            continue
        valid_meta = {k: v for k, v in valid_member.items() if k not in {"content", "crc32", "compressed_size", "uncompressed_size"}}
        generated_meta = {k: v for k, v in generated_member.items() if k not in {"content", "crc32", "compressed_size", "uncompressed_size"}}
        if valid_meta != generated_meta:
            differences.append({"index": index, "valid": valid_meta, "generated": generated_meta})
    return differences


def _row_differences(valid_rows: list[dict[str, Any]], generated_rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    max_len = max(len(valid_rows), len(generated_rows))
    for index in range(max_len):
        valid_row = valid_rows[index] if index < len(valid_rows) else None
        generated_row = generated_rows[index] if index < len(generated_rows) else None
        if valid_row != generated_row:
            differences.append({"index": index, "valid": valid_row, "generated": generated_row})
            if len(differences) >= limit:
                break
    return differences


def schema_diff_sqlite(valid_db_bytes: bytes, generated_db_bytes: bytes, include_rows: bool = True) -> dict[str, Any]:
    valid = inspect_sqlite_bytes(valid_db_bytes, include_rows=include_rows)
    generated = inspect_sqlite_bytes(generated_db_bytes, include_rows=include_rows)
    valid_tables = set(valid["tables"])
    generated_tables = set(generated["tables"])
    diffs: dict[str, Any] = {
        "missing_tables": sorted(valid_tables - generated_tables),
        "extra_tables": sorted(generated_tables - valid_tables),
        "table_diffs": {},
        "row_differences": {},
    }
    for table in sorted(valid_tables & generated_tables):
        valid_cols = valid["table_info"][table]["columns"]
        generated_cols = generated["table_info"][table]["columns"]
        valid_rows = valid["table_info"][table]["row_count"]
        generated_rows = generated["table_info"][table]["row_count"]
        if valid_cols != generated_cols or valid_rows != generated_rows:
            diffs["table_diffs"][table] = {
                "valid_columns": valid_cols,
                "generated_columns": generated_cols,
                "valid_row_count": valid_rows,
                "generated_row_count": generated_rows,
            }
        if include_rows:
            valid_table_rows = valid["table_info"][table].get("rows", [])
            generated_table_rows = generated["table_info"][table].get("rows", [])
            table_row_differences = _row_differences(valid_table_rows, generated_table_rows)
            if table_row_differences:
                diffs["row_differences"][table] = table_row_differences
    return diffs


def diff_ewsx(valid_path: str | Path, generated_path: str | Path) -> dict[str, Any]:
    valid = inspect_ewsx(valid_path)
    generated = inspect_ewsx(generated_path)
    valid_member_names = [member["name"] for member in valid["members"]]
    generated_member_names = [member["name"] for member in generated["members"]]
    valid_db = extract_ewsx_members(valid_path)["members"]
    generated_db = extract_ewsx_members(generated_path)["members"]
    valid_main = next(member["content"] for member in valid_db if Path(member["name"]).name.lower() == "main.db")
    generated_main = next(member["content"] for member in generated_db if Path(member["name"]).name.lower() == "main.db")
    return {
        "container": {
            "valid_mode": valid["container_mode"],
            "generated_mode": generated["container_mode"],
            "valid_member_count": valid["member_count"],
            "generated_member_count": generated["member_count"],
            "valid_members": valid_member_names,
            "generated_members": generated_member_names,
            "member_metadata_differences": _member_metadata_diff(valid_db, generated_db),
            "valid_zipfile_readable": valid["zipfile_readability"],
            "generated_zipfile_readable": generated["zipfile_readability"],
            "valid_central_directory": valid["central_directory"],
            "generated_central_directory": generated["central_directory"],
        },
        "sqlite": schema_diff_sqlite(valid_main, generated_main, include_rows=True),
        "valid_info_rows": (valid["sqlite"] or {}).get("info_rows", []),
        "generated_info_rows": (generated["sqlite"] or {}).get("info_rows", []),
    }


def dump_ewsx_report(path: str | Path, output_json: str | Path) -> None:
    Path(output_json).write_text(json.dumps(inspect_ewsx(path), indent=2), encoding="utf-8")

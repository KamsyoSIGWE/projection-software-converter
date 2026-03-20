from __future__ import annotations

import json
import os
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import ConversionRequest, ConversionResult


@dataclass
class AgendaItem:
    index: int
    kind: str
    source_manifest: str
    title: str
    original_path: str
    bundled_member: str
    packaged_name: str
    flow_type: int | None = None
    auto_advance: int | None = None
    interval: int | None = None


KEY_PATTERN = re.compile(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)')
TRAILING_COMMA_PATTERN = re.compile(r',\s*([}\]])')
SAFE_CHARS = re.compile(r"[^A-Za-z0-9._ ()-]+")
JSON_KEY_PATTERN = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)":')

VPAGD_STATIC_FILES = {
    "Version.json": "2",
    "RootStyle.json": '{Header:{FontSize:50,Bold:1,Italic:0,Underlined:0,CaseType:0,TextAlignment:1,VerticalAlignment:0,ShowChords:0,ChordSystem:1,ShowSlashChord:1,ShowBibleVerseNumbers:1,ShowSingleBibleVerseNumber:0,Wrap:0,BibleVerseNewLine:0,ExtendToNextVerses:0,MaxLineCount:0,MaxCharacterCount:0,Transition:1,Duration:400,Template:""},Body:{FontName:"Candara",FontSize:70,Bold:1,Italic:0,Underlined:0,CaseType:0,TextAlignment:2,VerticalAlignment:0,ShowChords:0,ChordSystem:1,ShowSlashChord:1,ShowBibleVerseNumbers:1,ShowSingleBibleVerseNumber:0,Wrap:0,BibleVerseNewLine:0,ExtendToNextVerses:0,MaxLineCount:0,MaxCharacterCount:0,Transition:1,Duration:400,FontStyle:{Fill:{Color:"FFFFFFFF"},Stroke:{Color:"FFFFD700"}},Template:""},Footer:{FontSize:50,Bold:1,Italic:0,Underlined:0,CaseType:0,TextAlignment:2,VerticalAlignment:2,ShowChords:0,ChordSystem:1,ShowSlashChord:1,ShowBibleVerseNumbers:1,ShowSingleBibleVerseNumber:0,Wrap:0,BibleVerseNewLine:0,ExtendToNextVerses:0,MaxLineCount:0,MaxCharacterCount:0,Transition:1,Duration:400,Template:""},Chords:{FontSize:110,Bold:0,Italic:0,Underlined:0,CaseType:0,TextAlignment:0,VerticalAlignment:1,ShowChords:0,ChordSystem:1,ShowSlashChord:1,ShowBibleVerseNumbers:1,ShowSingleBibleVerseNumber:0,Wrap:0,BibleVerseNewLine:0,ExtendToNextVerses:0,MaxLineCount:0,MaxCharacterCount:0,Transition:1,Duration:400,Template:""},Background:{Brush:{Color:"FF000000"},Volume:100,Stretch:3,IsMuted:0,StartPosition:0,EndPosition:0,VideoDuration:0,IsLooping:1,Transition:1,Duration:400,Luminosity:0,HeaderRect:"200,200,9600,700",BodyRect:"200,200,9600,8900",FooterRect:"200,9100,9600,700"}}',
    "SongBookStyle.json": '{Header:{Template:""},Body:{Transition:3},Footer:{Template:"[SongTitle] ([SongBookAbbreviation] [SongID])\\r\\n[SiteLicense]"}}',
    "BibleStyle.json": '{Header:{FontSize:65,Italic:1,Underlined:1,TextAlignment:2,VerticalAlignment:1,FontStyle:{Fill:{Color:"FFFFD700"},Stroke:{Color:"FFFFD700"}},Template:"[BibleBookName] [BibleChapterID]:[BibleVerseID]"},Body:{FontSize:90,TextAlignment:2,VerticalAlignment:1,ShowBibleVerseNumbers:1,ShowSingleBibleVerseNumber:0,BibleVerseNewLine:0,MaxLineCount:1},Footer:{Template:"[BibleDescription]\\r\\n[SiteLicense]"},Chords:{FontSize:100},Background:{Image:"Scripture BG 2.jpg",Stretch:2,StartPosition:0,EndPosition:8728,VideoDuration:94000000,Transition:1}}',
    "ImageStyle.json": "{}",
    "VideoStyle.json": "{Background:{Stretch:2,IsLooping:0}}",
    "PowerPointStyle.json": "{}",
    "PdfStyle.json": "{}",
    "AudioStyle.json": "{}",
    "WordStyle.json": "{}",
    "ExcelStyle.json": "{}",
    "WebSiteStyle.json": "{}",
}


def escape_unescaped_control_chars(text: str) -> str:
    parts: list[str] = []
    in_string = False
    escaped = False

    for ch in text:
        if in_string:
            if escaped:
                parts.append(ch)
                escaped = False
                continue
            if ch == "\\":
                parts.append(ch)
                escaped = True
                continue
            if ch == '"':
                parts.append(ch)
                in_string = False
                continue
            if ch == "\n":
                parts.append(r"\n")
                continue
            if ch == "\r":
                parts.append(r"\r")
                continue
            if ch == "\t":
                parts.append(r"\t")
                continue
            if ord(ch) < 32:
                parts.append(f"\\u{ord(ch):04x}")
                continue
            parts.append(ch)
            continue

        parts.append(ch)
        if ch == '"':
            in_string = True

    return "".join(parts)


def relaxed_json_to_python(text: str) -> Any:
    normalized = text.strip()
    normalized = KEY_PATTERN.sub(r'\1"\2"\3', normalized)
    normalized = TRAILING_COMMA_PATTERN.sub(r"\1", normalized)
    normalized = escape_unescaped_control_chars(normalized)
    try:
        return json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse relaxed JSON: {exc}") from exc


MANIFEST_KIND_PREFIXES = {
    "Image_": "image",
    "Video_": "video",
    "Audio_": "audio",
    "Pdf_": "pdf",
    "PowerPoint_": "ppt",
    "Word_": "doc",
    "Excel_": "sheet",
    "WebSite_": "website",
}


def detect_manifest_kind(name: str) -> str:
    for prefix, kind in MANIFEST_KIND_PREFIXES.items():
        if name.startswith(prefix):
            return kind
    return "unknown"


def sanitize_filename(name: str) -> str:
    cleaned = SAFE_CHARS.sub("_", name).strip().strip(".")
    return cleaned or "media"


def unique_name(existing: set[str], preferred: str) -> str:
    if preferred not in existing:
        existing.add(preferred)
        return preferred
    stem = Path(preferred).stem
    suffix = Path(preferred).suffix
    index = 2
    while True:
        candidate = f"{stem}__{index}{suffix}"
        if candidate not in existing:
            existing.add(candidate)
            return candidate
        index += 1


def synthetic_windows_path(title: str, ext: str, kind: str) -> str:
    folder = {
        "image": r"C:\VideoPsalmToFreeShow\Images",
        "video": r"C:\VideoPsalmToFreeShow\Videos",
        "audio": r"C:\VideoPsalmToFreeShow\Audio",
    }.get(kind, r"C:\VideoPsalmToFreeShow\Assets")
    return rf"{folder}\{sanitize_filename(title)}{ext}"


def freeshow_import_path(packaged_name: str) -> str:
    home = Path(os.path.expanduser("~"))
    return str(home / "Documents" / "FreeShow" / "Imports" / "Projects" / packaged_name)


def packaged_media_name(display_title: str, ext: str, index: int) -> str:
    stem = sanitize_filename(display_title)
    token = abs(hash((display_title.lower(), ext.lower(), index))) % 10_000_000_000
    return f"{stem}__i{token}{ext}"


def collect_agenda_properties(zf: zipfile.ZipFile) -> list[dict[str, Any]]:
    if "AgendaItemProperties.json" not in zf.namelist():
        return []
    data = relaxed_json_to_python(zf.read("AgendaItemProperties.json").decode("utf-8", "ignore"))
    items = data.get("Items", []) if isinstance(data, dict) else []
    return items if isinstance(items, list) else []


def parse_manifests(zf: zipfile.ZipFile) -> list[tuple[str, dict[str, Any]]]:
    members = [name for name in zf.namelist() if name.endswith(".json") and re.match(r"^[A-Za-z]+_\d+\.json$", Path(name).name)]
    parsed: list[tuple[str, dict[str, Any]]] = []
    for member in members:
        raw = zf.read(member).decode("utf-8", "ignore")
        data = relaxed_json_to_python(raw)
        if isinstance(data, dict):
            parsed.append((member, data))
    return parsed


def find_bundled_member(zf: zipfile.ZipFile, original_path: str) -> str | None:
    original_basename = Path(original_path.replace("\\", "/")).name
    lower_name_map = {Path(name).name.lower(): name for name in zf.namelist() if not name.endswith("/")}
    if original_basename.lower() in lower_name_map:
        return lower_name_map[original_basename.lower()]
    for member in zf.namelist():
        low = member.lower()
        if low.endswith("/" + original_basename.lower()) or low == original_basename.lower():
            return member
    return None


def extract_agenda_items(vpagd_path: str | Path) -> list[AgendaItem]:
    path = Path(vpagd_path)
    if not zipfile.is_zipfile(path):
        raise ValueError(f"Not a valid ZIP-based .vpagd file: {path}")

    with zipfile.ZipFile(path) as zf:
        props = collect_agenda_properties(zf)
        manifests = parse_manifests(zf)
        taken_packaged_names: set[str] = set()
        items: list[AgendaItem] = []
        for idx, (member, data) in enumerate(manifests):
            kind = detect_manifest_kind(Path(member).name)
            original_path = str(data.get("FileName", "")).strip()
            title = str(data.get("Text") or Path(original_path.replace("\\", "/")).stem or Path(member).stem)
            bundled = find_bundled_member(zf, original_path)
            if bundled is None:
                continue
            ext = Path(bundled).suffix or Path(original_path).suffix or ""
            if not original_path:
                original_path = synthetic_windows_path(title, ext, kind)
            packaged_name = unique_name(taken_packaged_names, packaged_media_name(title, ext, idx))
            prop = props[idx] if idx < len(props) and isinstance(props[idx], dict) else {}
            items.append(
                AgendaItem(
                    index=idx,
                    kind=kind,
                    source_manifest=member,
                    title=title,
                    original_path=original_path,
                    bundled_member=bundled,
                    packaged_name=packaged_name,
                    flow_type=prop.get("FlowType"),
                    auto_advance=prop.get("AutoAdvance"),
                    interval=prop.get("Interval"),
                )
            )
        return items


def _project_manifest(project_name: str, items: list[AgendaItem], created_ms: int | None = None) -> dict[str, Any]:
    now_ms = int(created_ms or time.time() * 1000)
    project_items: list[dict[str, Any]] = []
    files: list[str] = []
    media: dict[str, Any] = {}

    for item in items:
        import_path = freeshow_import_path(item.packaged_name)
        if item.kind in {"image", "video", "audio"}:
            project_items.append({"name": item.title, "id": import_path, "type": item.kind, "index": item.index})
            files.append(import_path)
            if item.kind in {"video", "audio"}:
                media[import_path] = {"tracks": []}
        else:
            project_items.append(
                {
                    "id": f"section_{item.index}",
                    "type": "section",
                    "name": item.title,
                    "notes": f"Unmapped VideoPsalm item from {item.source_manifest}",
                    "index": item.index,
                }
            )

    manifest: dict[str, Any] = {
        "project": {
            "name": project_name,
            "created": now_ms,
            "parent": "/",
            "shows": project_items,
            "modified": now_ms,
            "used": now_ms,
            "id": f"{abs(hash(project_name)) % 10_000_000_000:x}",
        },
        "parentFolder": "",
        "shows": {},
        "files": files,
    }
    if media:
        manifest["media"] = media
    return manifest


def _project_zip_members(zf: zipfile.ZipFile) -> list[str]:
    return [name for name in zf.namelist() if name != "data.json" and not name.endswith("/")]


def extract_project_media_items(project_path: str | Path) -> list[AgendaItem]:
    path = Path(project_path)
    if not zipfile.is_zipfile(path):
        raise ValueError(f"Not a valid ZIP-based .project file: {path}")

    with zipfile.ZipFile(path) as zf:
        if "data.json" not in zf.namelist():
            raise ValueError(f"Missing data.json in project: {path}")
        data = json.loads(zf.read("data.json").decode("utf-8"))
        project = data.get("project", {})
        shows = project.get("shows", []) if isinstance(project, dict) else []
        files = data.get("files", []) if isinstance(data.get("files"), list) else []
        zip_members = _project_zip_members(zf)
        file_member_map = {file_id: member for file_id, member in zip(files, zip_members)}

        items: list[AgendaItem] = []
        taken_packaged_names: set[str] = set()
        for fallback_index, show in enumerate(shows):
            if not isinstance(show, dict):
                continue
            kind = str(show.get("type") or "").strip().lower()
            if kind not in {"image", "video", "audio"}:
                continue
            original_path = str(show.get("id") or "").strip()
            if not original_path:
                continue
            bundled = file_member_map.get(original_path)
            if bundled is None:
                original_name = Path(original_path.replace("\\", "/")).name.lower()
                for member in zip_members:
                    if Path(member).name.lower() == original_name:
                        bundled = member
                        break
            if bundled is None:
                continue
            title = str(show.get("name") or Path(original_path.replace("\\", "/")).stem or Path(bundled).stem)
            ext = Path(bundled).suffix or Path(original_path).suffix or ""
            packaged_name = unique_name(taken_packaged_names, Path(bundled).name or packaged_media_name(title, ext, fallback_index))
            index = int(show.get("index", fallback_index)) if str(show.get("index", "")).strip() else fallback_index
            items.append(
                AgendaItem(
                    index=index,
                    kind=kind,
                    source_manifest="data.json",
                    title=title,
                    original_path=original_path,
                    bundled_member=bundled,
                    packaged_name=packaged_name,
                    flow_type=0 if kind in {"video", "audio"} else 2,
                    auto_advance=0,
                    interval=5000,
                )
            )
    return sorted(items, key=lambda item: item.index)


def python_to_relaxed_json(value: Any) -> str:
    compact = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return JSON_KEY_PATTERN.sub(r"\1:", compact)


def videosalm_packaged_member(original_path: str, packaged_name: str) -> str:
    windows_path = original_path.replace("/", "\\")
    path = Path(windows_path)
    parts = list(path.parts)
    if parts and parts[0].endswith("\\"):
        parts = parts[1:]
    cleaned = [part.rstrip("\\") for part in parts if part not in {"\\", "/"}]
    if cleaned:
        return "/".join(cleaned)
    return packaged_name


def videosalm_manifest_name(kind: str, counter: int) -> str:
    prefix = {
        "image": "Image",
        "video": "Video",
        "audio": "Audio",
        "pdf": "Pdf",
        "ppt": "PowerPoint",
        "doc": "Word",
        "sheet": "Excel",
        "website": "WebSite",
    }.get(kind, "Image")
    return f"{prefix}_{counter}.json"


def convert_freeshow_to_videosalm(project_path: str | Path, output_vpagd_path: str | Path, also_json: str | Path | None = None) -> dict[str, Any]:
    source_path = Path(project_path)
    output_path = Path(output_vpagd_path)
    items = extract_project_media_items(source_path)
    agenda_payload = {
        "Items": [
            {
                "FlowType": item.flow_type if item.flow_type is not None else (0 if item.kind in {"video", "audio"} else 2),
                "AutoAdvance": item.auto_advance if item.auto_advance is not None else 0,
                "Interval": item.interval if item.interval is not None else 5000,
                "VerseOrderIndex": -1,
            }
            for item in items
        ]
    }
    debug_manifest = {"project_name": source_path.stem, "item_count": len(items), "items": [item.__dict__ for item in items]}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source_path) as zin, zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, contents in VPAGD_STATIC_FILES.items():
            zout.writestr(name, contents)

        kind_counters: dict[str, int] = {}
        for item in items:
            kind_index = kind_counters.get(item.kind, 0)
            kind_counters[item.kind] = kind_index + 1
            manifest_name = videosalm_manifest_name(item.kind, kind_index)
            manifest_payload = {"FileName": item.original_path, "Text": item.title}
            zout.writestr(manifest_name, python_to_relaxed_json(manifest_payload))

        written_media_members: set[str] = set()
        for item in items:
            target_member = videosalm_packaged_member(item.original_path, item.packaged_name)
            if target_member in written_media_members:
                continue
            with zin.open(item.bundled_member) as src:
                zout.writestr(target_member, src.read())
            written_media_members.add(target_member)

        zout.writestr("AgendaItemProperties.json", python_to_relaxed_json(agenda_payload))

    if also_json is not None:
        debug_path = Path(also_json)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(json.dumps(debug_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return debug_manifest


def convert_videosalm_to_freeshow(vpagd_path: str | Path, output_project_path: str | Path, also_json: str | Path | None = None) -> dict[str, Any]:
    source_path = Path(vpagd_path)
    output_path = Path(output_project_path)
    items = extract_agenda_items(source_path)
    manifest = _project_manifest(source_path.stem, items)

    temp_root = Path.cwd() / ".videosalm_to_freeshow_build"
    tmp = temp_root / sanitize_filename(output_path.stem)
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(source_path) as zin:
            for item in items:
                target_path = tmp / item.packaged_name
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zin.open(item.bundled_member) as src, open(target_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)

        data_json = tmp / "data.json"
        data_json.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in items:
                file_path = tmp / item.packaged_name
                if file_path.is_file():
                    zout.write(file_path, arcname=item.packaged_name)
            zout.write(data_json, arcname="data.json")
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
        if temp_root.exists() and not any(temp_root.iterdir()):
            temp_root.rmdir()

    if also_json is not None:
        debug_path = Path(also_json)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return manifest


def convert_videosalm_request(request: ConversionRequest) -> ConversionResult:
    manifest = convert_videosalm_to_freeshow(request.input_path, request.output_path, request.debug_manifest_path)
    item_count = len(manifest.get("project", {}).get("shows", []))
    return ConversionResult(output_path=request.output_path, item_count=item_count, details=manifest)


def convert_freeshow_request(request: ConversionRequest) -> ConversionResult:
    manifest = convert_freeshow_to_videosalm(request.input_path, request.output_path, request.debug_manifest_path)
    item_count = int(manifest.get("item_count", 0))
    return ConversionResult(output_path=request.output_path, item_count=item_count, details=manifest)

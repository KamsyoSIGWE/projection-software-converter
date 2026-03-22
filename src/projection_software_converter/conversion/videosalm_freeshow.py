from __future__ import annotations

import base64
import json
import os
import re
import shutil
import time
import uuid
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


@dataclass
class SongAgendaItem:
    index: int
    title: str
    verses: list[str]
    background_kind: str | None = None
    background_original_path: str = ""
    background_bundled_member: str = ""


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


def _find_project_member_by_path(zf: zipfile.ZipFile, import_path: str) -> str | None:
    basename = Path(str(import_path)).name.lower()
    for name in zf.namelist():
        if name.endswith("/"):
            continue
        if Path(name).name.lower() == basename:
            return name
    return None


def _freeshow_text_lines(slide: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in slide.get("items", []):
        if not isinstance(item, dict):
            continue
        for line in item.get("lines", []):
            if not isinstance(line, dict):
                continue
            text_parts: list[str] = []
            for segment in line.get("text", []):
                if not isinstance(segment, dict):
                    continue
                value = str(segment.get("value") or "")
                if value:
                    text_parts.append(value)
            text = "".join(text_parts).strip()
            if text:
                lines.append(text)
    return lines


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


def extract_project_song_items(project_path: str | Path) -> list[SongAgendaItem]:
    path = Path(project_path)
    if not zipfile.is_zipfile(path):
        raise ValueError(f"Not a valid ZIP-based .project file: {path}")

    with zipfile.ZipFile(path) as zf:
        if "data.json" not in zf.namelist():
            raise ValueError(f"Missing data.json in project: {path}")
        data = json.loads(zf.read("data.json").decode("utf-8"))
        project = data.get("project", {})
        project_shows = project.get("shows", []) if isinstance(project, dict) else []
        named_shows = data.get("shows", {}) if isinstance(data.get("shows"), dict) else {}

        songs: list[SongAgendaItem] = []
        for fallback_index, entry in enumerate(project_shows):
            if not isinstance(entry, dict) or entry.get("type") is not None:
                continue
            show_id = str(entry.get("id") or "").strip()
            show = named_shows.get(show_id)
            if not isinstance(show, dict):
                continue

            layouts = show.get("layouts", {})
            active_layout = str(show.get("settings", {}).get("activeLayout") or "")
            if not active_layout or active_layout not in layouts:
                active_layout = next(iter(layouts), "")
            if not active_layout:
                continue

            layout = layouts.get(active_layout) or {}
            show_media = show.get("media", {}) if isinstance(show.get("media"), dict) else {}
            slides_by_id = show.get("slides", {}) if isinstance(show.get("slides"), dict) else {}
            verses: list[str] = []
            background_kind: str | None = None
            background_original_path = ""
            background_bundled_member = ""

            for layout_entry in layout.get("slides", []):
                if not isinstance(layout_entry, dict):
                    continue
                slide_id = str(layout_entry.get("id") or "")
                slide = slides_by_id.get(slide_id)
                if not isinstance(slide, dict):
                    continue

                text_lines = _freeshow_text_lines(slide)
                if text_lines:
                    verses.append("\n".join(text_lines))

                if background_bundled_member:
                    continue
                background_id = str(layout_entry.get("background") or "")
                if not background_id or background_id not in show_media:
                    continue
                background_meta = show_media.get(background_id) or {}
                candidate_kind = str(background_meta.get("type") or "").lower()
                original_path = str(background_meta.get("path") or "").strip()
                if candidate_kind not in {"image", "video"} or not original_path:
                    continue
                bundled_member = _find_project_member_by_path(zf, original_path)
                if not bundled_member:
                    continue
                background_kind = candidate_kind
                background_original_path = original_path
                background_bundled_member = bundled_member

            if not verses:
                continue

            index = int(entry.get("index", fallback_index)) if str(entry.get("index", "")).strip() else fallback_index
            songs.append(
                SongAgendaItem(
                    index=index,
                    title=str(show.get("name") or f"Song {len(songs) + 1}").strip() or f"Song {len(songs) + 1}",
                    verses=verses,
                    background_kind=background_kind,
                    background_original_path=background_original_path,
                    background_bundled_member=background_bundled_member,
                )
            )
    return sorted(songs, key=lambda item: item.index)


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


def videosalm_song_background_member(kind: str, packaged_name: str) -> str:
    folder = "Videos" if kind == "video" else "Images"
    return f"{folder}/{packaged_name}"


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


def _videosalm_guid() -> str:
    return base64.b64encode(uuid.uuid4().bytes).decode("ascii").rstrip("=")


def _videosalm_song_payload(song: SongAgendaItem, background_reference: str | None) -> dict[str, Any]:
    style: dict[str, Any] = {"Body": {"FontSize": 95}}
    if background_reference:
        if song.background_kind == "video":
            style["Background"] = {"Video": background_reference, "IsLooping": 1}
        elif song.background_kind == "image":
            style["Background"] = {"Image": background_reference}
    return {
        "Guid": _videosalm_guid(),
        "Verses": [{"Text": verse} for verse in song.verses],
        "Style": style,
        "Text": song.title,
    }


def _videosalm_songbook_payload(title: str) -> dict[str, Any]:
    return {"Songs": [], "Guid": _videosalm_guid(), "Text": title}


def _videosalm_agenda_properties(entry: AgendaItem | SongAgendaItem) -> dict[str, Any]:
    if isinstance(entry, AgendaItem):
        return {
            "FlowType": entry.flow_type if entry.flow_type is not None else (0 if entry.kind in {"video", "audio"} else 2),
            "AutoAdvance": entry.auto_advance if entry.auto_advance is not None else 0,
            "Interval": entry.interval if entry.interval is not None else 5000,
            "VerseOrderIndex": -1,
        }
    return {
        "FlowType": 0,
        "AutoAdvance": 0,
        "Interval": 5000,
        "VerseOrderIndex": -1,
        "HiddenSlides": [],
    }


def convert_freeshow_to_videosalm(project_path: str | Path, output_vpagd_path: str | Path, also_json: str | Path | None = None) -> dict[str, Any]:
    source_path = Path(project_path)
    output_path = Path(output_vpagd_path)
    media_items = extract_project_media_items(source_path)
    song_items = extract_project_song_items(source_path)
    schedule_items: list[AgendaItem | SongAgendaItem] = sorted(
        [*media_items, *song_items],
        key=lambda item: item.index,
    )
    agenda_payload = {"Items": [_videosalm_agenda_properties(item) for item in schedule_items]}
    debug_manifest = {
        "project_name": source_path.stem,
        "item_count": len(schedule_items),
        "media_item_count": len(media_items),
        "song_item_count": len(song_items),
        "items": [item.__dict__ for item in schedule_items],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source_path) as zin, zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, contents in VPAGD_STATIC_FILES.items():
            zout.writestr(name, contents)

        kind_counters: dict[str, int] = {}
        written_media_members: set[str] = set()
        used_background_names: set[str] = set()
        written_song_backgrounds: dict[str, tuple[str, str]] = {}
        song_counter = 0

        for item in schedule_items:
            if isinstance(item, AgendaItem):
                kind_index = kind_counters.get(item.kind, 0)
                kind_counters[item.kind] = kind_index + 1
                manifest_name = videosalm_manifest_name(item.kind, kind_index)
                manifest_payload = {"FileName": item.original_path, "Text": item.title}
                zout.writestr(manifest_name, python_to_relaxed_json(manifest_payload))

                target_member = videosalm_packaged_member(item.original_path, item.packaged_name)
                if target_member in written_media_members:
                    continue
                with zin.open(item.bundled_member) as src:
                    zout.writestr(target_member, src.read())
                written_media_members.add(target_member)
                continue

            background_reference: str | None = None
            if item.background_bundled_member and item.background_kind:
                cached = written_song_backgrounds.get(item.background_bundled_member)
                if cached is None:
                    original_name = Path(item.background_original_path).name or Path(item.background_bundled_member).name
                    preferred_name = unique_name(used_background_names, original_name)
                    target_member = videosalm_song_background_member(item.background_kind, preferred_name)
                    with zin.open(item.background_bundled_member) as src:
                        zout.writestr(target_member, src.read())
                    written_media_members.add(target_member)
                    cached = (target_member, Path(preferred_name).name)
                    written_song_backgrounds[item.background_bundled_member] = cached
                background_reference = cached[1]

            zout.writestr(f"Song_{song_counter}.json", python_to_relaxed_json(_videosalm_song_payload(item, background_reference)))
            zout.writestr(f"SongBook_{song_counter}.json", python_to_relaxed_json(_videosalm_songbook_payload(item.title)))
            song_counter += 1

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

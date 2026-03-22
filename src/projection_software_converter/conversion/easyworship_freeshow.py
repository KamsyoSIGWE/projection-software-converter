from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import re
import shutil
import sqlite3
import struct
import tempfile
import time
import uuid
import zlib
import zipfile
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from PIL import Image

from .base import ConversionRequest, ConversionResult
from .easyworship_inspector import extract_ewsx_members
from .videosalm_freeshow import AgendaItem, _project_manifest, extract_project_media_items, freeshow_import_path, sanitize_filename, unique_name

ZIP_LOCAL_HEADER = b"PK\x03\x04"
ZIP_STORED = 0
ZIP_DEFLATED = 8
EASYWORSHIP_VERSION = "7.4.1.3"
EASYWORSHIP_MIN_VERSION = "6.5.1.0"
EASYWORSHIP_TEMPLATE_ENV = "PSC_EASYWORSHIP_TEMPLATE_EWSX"
EASYWORSHIP_TEMPLATE_VIDEO_DB = "single_video_valid.main.db"
EASYWORSHIP_TEMPLATE_VIDEO_BUNDLE = "single_video_valid.bundle.json"
EASYWORSHIP_TEMPLATE_IMAGE_DB = "single_image_valid.main.db"
EASYWORSHIP_TEMPLATE_IMAGE_BUNDLE = "single_image_valid.bundle.json"
EASYWORSHIP_TEMPLATE_FILES = {
    "video": (EASYWORSHIP_TEMPLATE_VIDEO_DB, EASYWORSHIP_TEMPLATE_VIDEO_BUNDLE),
    "image": (EASYWORSHIP_TEMPLATE_IMAGE_DB, EASYWORSHIP_TEMPLATE_IMAGE_BUNDLE),
}
EASYWORSHIP_MEDIA_PRESENTATION_TYPES = {
    "video": 1,
    "image": 2,
}
DEFAULT_SHAPE_XML = """<?xml version="1.0"?>
<xml>
  <DMLShape xmlns="http://www.stdok.com/2014/presentation/shapes">
    <spPr>
      <xfrm>
        <ext cx="1905000" cy="1905000"/>
      </xfrm>
      <custGeom sdmlFromDMLPreset="defaultRect">
        <defaultRect>
          <avLst>
            <gd name="ewAdj1" fmla="val 0"/>
          </avLst>
          <gdLst>
            <gd name="a" fmla="pin 0 ewAdj1 50000"/>
            <gd name="x1" fmla="*/ ss a 100000"/>
            <gd name="x2" fmla="+- r 0 x1"/>
            <gd name="y2" fmla="+- b 0 x1"/>
            <gd name="il" fmla="*/ x1 29289 100000"/>
            <gd name="ir" fmla="+- r 0 il"/>
            <gd name="ib" fmla="+- b 0 il"/>
          </gdLst>
          <ahLst>
            <ahXY gdRefX="ewAdj1" minX="0" maxX="50000">
              <pos x="x1" y="t"/>
            </ahXY>
          </ahLst>
          <cxnLst>
            <cxn ang="3cd4">
              <pos x="hc" y="t"/>
            </cxn>
            <cxn ang="cd2">
              <pos x="l" y="vc"/>
            </cxn>
            <cxn ang="cd4">
              <pos x="hc" y="b"/>
            </cxn>
            <cxn ang="0">
              <pos x="r" y="vc"/>
            </cxn>
          </cxnLst>
          <rect l="il" t="il" r="ir" b="ib"/>
          <pathLst>
            <path>
              <moveTo>
                <pt x="l" y="x1"/>
              </moveTo>
              <arcTo wR="x1" hR="x1" stAng="cd2" swAng="cd4"/>
              <lnTo>
                <pt x="x2" y="t"/>
              </lnTo>
              <arcTo wR="x1" hR="x1" stAng="3cd4" swAng="cd4"/>
              <lnTo>
                <pt x="r" y="y2"/>
              </lnTo>
              <arcTo wR="x1" hR="x1" stAng="0" swAng="cd4"/>
              <lnTo>
                <pt x="x1" y="b"/>
              </lnTo>
              <arcTo wR="x1" hR="x1" stAng="cd4" swAng="cd4"/>
              <close/>
            </path>
          </pathLst>
        </defaultRect>
      </custGeom>
    </spPr>
  </DMLShape>
</xml>
"""
RTF_FONT_SIZE_PATTERN = re.compile(r"\\fs(\d+)")

MINIMAL_SCHEMA = """
CREATE TABLE info (
  rowid integer PRIMARY KEY NOT NULL UNIQUE,
  version text,
  version_min text
);
CREATE TABLE presentation (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  presentation_uid text,
  presentation_rev_uid text,
  presentation_global_uid text,
  presentation_type integer,
  aspect_ratio text,
  group_level integer,
  order_index integer,
  thumbnail_slide_id integer,
  layout_revision integer DEFAULT 1,
  thumbnail_desired_rev integer DEFAULT 1,
  thumbnail_rev integer DEFAULT 1,
  thumbnail blob,
  auto_theme boolean,
  looping boolean,
  title text,
  author text,
  copyright text,
  administrator text,
  description text,
  tags text,
  reference_number text,
  provider_id integer DEFAULT -1,
  vendor_id integer,
  notes text,
  modified_date integer,
  ready integer DEFAULT 1,
  error_no integer
);
CREATE TABLE slide (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  presentation_id integer NOT NULL,
  title text,
  slide_uid text,
  slide_rev_uid text,
  order_index integer,
  layout_flag integer,
  theme_id integer,
  theme_slide_uid text,
  modified_theme_id integer,
  modified_theme_layout_revision integer,
  layout_revision integer DEFAULT 1,
  thumbnail_desired_rev integer DEFAULT 1,
  thumbnail_rev integer DEFAULT 1,
  thumbnail blob
);
CREATE TABLE slide_property_group (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  link_id integer,
  group_name text
);
CREATE TABLE slide_property (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  group_id integer,
  value_type integer,
  key text,
  value text
);
CREATE TABLE element (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  slide_id integer,
  element_uid text,
  element_type integer,
  element_style_type integer,
  order_index integer,
  x real,
  y real,
  width real,
  height real,
  background_resource_id integer,
  foreground_resource_id integer,
  shape_resource_id integer,
  internal_mute boolean,
  from_master boolean
);
CREATE TABLE element_property_group (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  link_id integer,
  group_name text
);
CREATE TABLE element_property (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  group_id integer,
  value_type integer,
  key text,
  value text
);
CREATE TABLE resource (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_hash integer,
  resource_uid text,
  resource_type integer,
  title text,
  author text,
  copyright text,
  description text,
  tags text
);
CREATE TABLE file (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  file_hash text,
  filename text,
  shared_filename text
);
CREATE TABLE resource_color (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_id integer,
  color integer
);
CREATE TABLE resource_shape (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_id integer,
  shape_data text
);
CREATE TABLE resource_text (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_id integer,
  rtf text
);
CREATE TABLE resource_image (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_id integer,
  file_id integer,
  original_filename text,
  filesize integer,
  modified_date integer,
  width integer,
  height integer
);
CREATE TABLE resource_video (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_id integer,
  file_id integer,
  original_filename text,
  filesize integer,
  modified_date integer,
  start_pos integer DEFAULT -1,
  end_pos integer DEFAULT -1,
  poster_frame_pos integer DEFAULT -1,
  width integer,
  height integer,
  duration integer,
  repeating boolean,
  alpha_channel_mode integer DEFAULT 0,
  video_stream_count integer DEFAULT 0,
  audio_stream_count integer DEFAULT 0,
  video_stream_type integer DEFAULT 0,
  audio_stream_type integer DEFAULT 0,
  audio_stream_profile integer DEFAULT 0
);
CREATE TABLE resource_audio (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_id integer,
  file_id integer,
  original_filename text,
  filesize integer,
  modified_date integer,
  start_pos integer DEFAULT -1,
  end_pos integer DEFAULT -1,
  duration integer,
  repeating boolean,
  video_stream_count integer DEFAULT 0,
  audio_stream_count integer DEFAULT 0,
  video_stream_type integer DEFAULT -1,
  audio_stream_type integer DEFAULT -1,
  audio_stream_profile integer DEFAULT -1
);
CREATE TABLE resource_powerpoint (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_id integer,
  file_id integer,
  original_filename text,
  filesize integer,
  modified_date integer,
  width integer,
  height integer
);
CREATE TABLE resource_web (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_id integer,
  url text,
  remove_scroll_bars boolean
);
CREATE TABLE resource_dvd_disk (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  disk_uid text,
  disk_name text
);
CREATE TABLE resource_dvd (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_id integer,
  resource_dvd_disk_id integer,
  modified_date integer,
  start_pos integer DEFAULT -1,
  end_pos integer DEFAULT -1,
  poster_frame_pos integer DEFAULT -1,
  width integer,
  height integer,
  duration integer,
  repeating boolean,
  clip_title integer,
  clip_chapter integer,
  clip_angle integer,
  clip_audio integer,
  clip_subpicture integer,
  clip_segment_start_pos integer,
  clip_segment_duration integer,
  clip_fps_flag integer,
  thumbnail blob
);
CREATE TABLE resource_dvd_pc (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_id integer,
  segment_bookmark blob,
  clip_bookmark blob,
  bookmark_os_ver integer
);
CREATE TABLE resource_feed (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_id integer,
  feed_type integer,
  modified_date integer,
  thumbnail blob
);
CREATE TABLE resource_feed_pc (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_id integer,
  device_name text,
  device_uid text,
  video_standard integer,
  color_compression text,
  frame_rate integer,
  input_port integer,
  width integer,
  height integer,
  field_dominance integer
);
CREATE TABLE resource_gradient (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_id integer,
  angle integer,
  transparent boolean
);
CREATE TABLE resource_gradient_color (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  resource_id integer,
  color_from integer,
  color_to integer,
  percent_from real,
  percent_to real,
  ramp integer
);
CREATE TABLE presentation_property_group_global (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  link_id integer,
  group_name text
);
CREATE TABLE presentation_property_global (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  group_id integer,
  value_type integer,
  key text,
  value text
);
CREATE TABLE presentation_property_group (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  link_id integer,
  group_name text
);
CREATE TABLE presentation_property (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  group_id integer,
  value_type integer,
  key text,
  value text
);
CREATE TABLE token (
  rowid integer PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
  presentation_id integer,
  uid text,
  token_name text,
  token_type integer,
  token_format text,
  token_interval integer,
  token_time_value integer,
  token_time_value_fixed integer,
  token_allow_overrun boolean,
  token_value text
);
"""

MINIMAL_INDEXES = """
CREATE INDEX presentation_Index01 ON presentation (presentation_uid, presentation_rev_uid);
CREATE INDEX presentation_Index02 ON presentation (provider_id);
CREATE INDEX idx_presentations_group_level_order_index ON presentation (group_level, order_index);
CREATE INDEX idx_slides_presentation_id_order_index ON slide (presentation_id, order_index);
CREATE INDEX slide_property_group_Index01 ON slide_property_group (link_id, group_name);
CREATE INDEX slide_property_Index01 ON slide_property (group_id);
CREATE INDEX element_Index01 ON element (slide_id, order_index);
CREATE INDEX element_property_group_Index01 ON element_property_group (link_id, group_name);
CREATE INDEX element_property_Index01 ON element_property (group_id);
CREATE INDEX resource_Index01 ON resource (resource_hash);
CREATE INDEX resource_Index02 ON resource (resource_uid);
CREATE INDEX file_Index01 ON file (file_hash);
CREATE INDEX resource_color_Index01 ON resource_color (resource_id);
CREATE INDEX resource_shape_Index01 ON resource_shape (resource_id);
CREATE INDEX resource_text_Index01 ON resource_text (resource_id);
CREATE INDEX resource_image_Index01 ON resource_image (resource_id);
CREATE INDEX resource_image_Index02 ON resource_image (file_id);
CREATE INDEX resource_video_Index01 ON resource_video (resource_id);
CREATE INDEX resource_video_Index02 ON resource_video (file_id);
CREATE INDEX resource_audio_Index01 ON resource_audio (resource_id);
CREATE INDEX resource_audio_Index02 ON resource_audio (file_id);
CREATE INDEX resource_powerpoint_Index01 ON resource_powerpoint (resource_id);
CREATE INDEX resource_powerpoint_Index02 ON resource_powerpoint (file_id);
CREATE INDEX resource_web_Index01 ON resource_web (resource_id);
CREATE INDEX resource_dvd_Index01 ON resource_dvd (resource_id);
CREATE INDEX resource_dvd_pc_Index01 ON resource_dvd_pc (resource_id);
CREATE INDEX resource_feed_Index01 ON resource_feed (resource_id);
CREATE INDEX resource_feed_pc_Index01 ON resource_feed_pc (resource_id);
CREATE INDEX resource_gradient_Index01 ON resource_gradient (resource_id);
CREATE INDEX resource_gradient_color_Index01 ON resource_gradient_color (resource_id);
CREATE INDEX presentation_property_group_global_Index01 ON presentation_property_group_global (link_id, group_name);
CREATE INDEX presentation_property_global_Index01 ON presentation_property_global (group_id);
CREATE INDEX presentation_property_group_Index01 ON presentation_property_group (link_id, group_name);
CREATE INDEX presentation_property_Index01 ON presentation_property (group_id);
"""


class BundleMember:
    def __init__(self, name: str, compression: int, data_start: int, compressed_size: int) -> None:
        self.name = name
        self.compression = compression
        self.data_start = data_start
        self.compressed_size = compressed_size


def _scan_bundle_members(path: str | Path) -> list[BundleMember]:
    members: list[BundleMember] = []
    with Path(path).open("rb") as handle:
        position = 0
        while True:
            handle.seek(position)
            header = handle.read(30)
            if len(header) < 30:
                break
            if header[:4] != ZIP_LOCAL_HEADER:
                break
            _sig, _ver, flags, compression, _mtime, _mdate, _crc, compressed_size, _usize, name_len, extra_len = struct.unpack(
                "<IHHHHHIIIHH",
                header,
            )
            if flags & 0x0008:
                raise ValueError("EasyWorship bundle uses a ZIP data descriptor that is not supported yet.")
            name = handle.read(name_len).decode("utf-8", "replace")
            handle.seek(extra_len, 1)
            data_start = handle.tell()
            members.append(BundleMember(name=name, compression=compression, data_start=data_start, compressed_size=compressed_size))
            position = data_start + compressed_size
    if not members:
        raise ValueError(f"Could not find ZIP-style members in {path}")
    return members


def _read_bundle_member(path: str | Path, member: BundleMember) -> bytes:
    with Path(path).open("rb") as handle:
        handle.seek(member.data_start)
        data = handle.read(member.compressed_size)
    if member.compression == ZIP_STORED:
        return data
    if member.compression == ZIP_DEFLATED:
        return zlib.decompress(data, -15)
    raise ValueError(f"Unsupported EasyWorship bundle compression method: {member.compression}")


def _deflate_raw(data: bytes) -> bytes:
    compressor = zlib.compressobj(level=6, wbits=-15)
    return compressor.compress(data) + compressor.flush()


def _write_easyworship_bundle(output_path: Path, members: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        central_directory: list[dict[str, Any]] = []
        for member in members:
            name = str(member["name"])
            payload = bytes(member.get("content", b""))
            compression = int(member.get("compression", ZIP_STORED))
            extra_length = int(member.get("extra_length") or 0)
            encoded_name = name.encode("utf-8")
            compressed = _deflate_raw(payload) if compression == ZIP_DEFLATED else payload
            crc = zlib.crc32(payload) & 0xFFFFFFFF
            local_header_offset = handle.tell()
            header = struct.pack(
                "<IHHHHHIIIHH",
                0x04034B50,
                int(member.get("version_needed") or 20),
                int(member.get("flags") if member.get("flags") is not None else 0x0800),
                compression,
                int(member.get("mtime") or 0),
                int(member.get("mdate") or 0),
                crc,
                len(compressed),
                len(payload),
                len(encoded_name),
                extra_length,
            )
            handle.write(header)
            handle.write(encoded_name)
            if extra_length:
                handle.write(b"\x00" * extra_length)
            handle.write(compressed)
            central_directory.append(
                {
                    "name": name,
                    "version_made_by": int(member.get("version_made_by") or 20),
                    "version_needed": int(member.get("version_needed") or 20),
                    "flags": int(member.get("flags") if member.get("flags") is not None else 0x0800),
                    "compression": compression,
                    "mtime": int(member.get("mtime") or 0),
                    "mdate": int(member.get("mdate") or 0),
                    "crc32": crc,
                    "compressed_size": len(compressed),
                    "uncompressed_size": len(payload),
                    "extra_length": extra_length,
                    "comment_length": int(member.get("comment_length") or 0),
                    "disk_number_start": int(member.get("disk_number_start") or 0),
                    "internal_attributes": int(member.get("internal_attributes") or 0),
                    "external_attributes": int(
                        member.get("external_attributes")
                        if member.get("external_attributes") is not None
                        else (16 if name == "media" else 32)
                    ),
                    "local_header_offset": local_header_offset,
                }
            )
        central_directory_offset = handle.tell()
        for entry in central_directory:
            encoded_name = entry["name"].encode("utf-8")
            central_header = struct.pack(
                "<IHHHHHHIIIHHHHHII",
                0x02014B50,
                entry["version_made_by"],
                entry["version_needed"],
                entry["flags"],
                entry["compression"],
                entry["mtime"],
                entry["mdate"],
                entry["crc32"],
                entry["compressed_size"],
                entry["uncompressed_size"],
                len(encoded_name),
                entry["extra_length"],
                entry["comment_length"],
                entry["disk_number_start"],
                entry["internal_attributes"],
                entry["external_attributes"],
                entry["local_header_offset"],
            )
            handle.write(central_header)
            handle.write(encoded_name)
            if entry["extra_length"]:
                handle.write(b"\x00" * entry["extra_length"])
            if entry["comment_length"]:
                handle.write(b"\x00" * entry["comment_length"])
        central_directory_size = handle.tell() - central_directory_offset
        eocd = struct.pack(
            "<IHHHHIIH",
            0x06054B50,
            0,
            0,
            len(central_directory),
            len(central_directory),
            central_directory_size,
            central_directory_offset,
            0,
        )
        handle.write(eocd)


def _resource_hash(seed: str) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], byteorder="little", signed=True)


def _ew_uid() -> str:
    return f"1-{str(uuid.uuid4()).upper()}"


def _ew_ticks(dt: datetime | None = None) -> int:
    current = dt or datetime.now(UTC)
    epoch = datetime(1, 1, 1, tzinfo=UTC)
    delta = current - epoch
    return int(delta.total_seconds() * 10_000_000)


def _rtf_title(title: str) -> str:
    escaped = title.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    return (
        "{\\rtf1\\ansi\\deff0\\sdeasyworship2\r\n"
        "{\\fonttbl{\\f0 Tahoma;}}\r\n"
        "{\\colortbl ;}\r\n"
        f"{{\\pard\\qc\\qdef\\plain\\fs40{{\\*\\sdfsreal 20}}{{\\*\\sdfsdef 20}}\\sdfsauto {escaped}\\par}}\r\n"
        "}"
    )


def _easyworship_filename(title: str, ext: str, index: int) -> str:
    digest = hashlib.sha1(f"{title.lower()}|{index}|{ext.lower()}".encode("utf-8")).hexdigest()
    token = digest[:6]
    return f"{token}{ext.lower()}"


def _probe_image_size(file_bytes: bytes) -> tuple[int, int]:
    try:
        with Image.open(io.BytesIO(file_bytes)) as image:
            return int(image.width), int(image.height)
    except Exception:
        return 0, 0


def _probe_video_metadata(file_bytes: bytes, suffix: str) -> dict[str, int]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {
            "width": 0,
            "height": 0,
            "duration_ticks": 0,
            "video_stream_count": 0,
            "audio_stream_count": 0,
            "video_stream_type": 0,
            "audio_stream_type": 0,
            "audio_stream_profile": 0,
        }

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".bin") as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise ValueError(completed.stderr.strip() or "ffprobe failed")
        payload = json.loads(completed.stdout or "{}")
        streams = payload.get("streams", [])
        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        first_video = video_streams[0] if video_streams else {}
        first_audio = audio_streams[0] if audio_streams else {}
        duration_seconds = 0.0
        format_info = payload.get("format", {})
        for candidate in (format_info.get("duration"), first_video.get("duration"), first_audio.get("duration")):
            if candidate not in (None, ""):
                try:
                    duration_seconds = float(candidate)
                    break
                except (TypeError, ValueError):
                    continue
        video_codec_map = {
            "h264": 27,
            "hevc": 173,
            "mpeg4": 12,
            "vp9": 167,
        }
        audio_codec_map = {
            "aac": 86018,
            "mp3": 86017,
            "ac3": 86019,
            "pcm_s16le": 65536,
        }
        audio_profile_map = {
            "lc": 2,
            "he-aac": 5,
            "he-aacv2": 29,
        }
        return {
            "width": int(first_video.get("width") or 0),
            "height": int(first_video.get("height") or 0),
            "duration_ticks": int(duration_seconds * 10_000_000),
            "video_stream_count": len(video_streams),
            "audio_stream_count": len(audio_streams),
            "video_stream_type": video_codec_map.get(str(first_video.get("codec_name") or "").lower(), 0),
            "audio_stream_type": audio_codec_map.get(str(first_audio.get("codec_name") or "").lower(), 0),
            "audio_stream_profile": audio_profile_map.get(str(first_audio.get("profile") or "").lower(), 0),
        }
    except Exception:
        return {
            "width": 0,
            "height": 0,
            "duration_ticks": 0,
            "video_stream_count": 0,
            "audio_stream_count": 0,
            "video_stream_type": 0,
            "audio_stream_type": 0,
            "audio_stream_profile": 0,
        }
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


def _embedded_easyworship_template_bundle(kind: str) -> dict[str, Any]:
    if kind not in EASYWORSHIP_TEMPLATE_FILES:
        raise ValueError(f"Unsupported EasyWorship template kind: {kind}")
    template_db, template_bundle = EASYWORSHIP_TEMPLATE_FILES[kind]
    template_dir = resources.files("projection_software_converter.resources").joinpath("easyworship_templates")
    bundle_info = json.loads(template_dir.joinpath(template_bundle).read_text(encoding="utf-8"))
    main_db_bytes = template_dir.joinpath(template_db).read_bytes()
    members: list[dict[str, Any]] = []
    for member in bundle_info.get("members", []):
        members.append(
            {
                **member,
                "content": main_db_bytes if str(member.get("name")).lower() == "main.db" else b"",
            }
        )
    return {
        "container_mode": "embedded-template",
        "template_source": f"package:projection_software_converter.resources/easyworship_templates/{template_bundle}",
        "members": members,
        "source_version": bundle_info.get("source_version"),
        "template_kind": bundle_info.get("template_kind"),
    }


def _load_easyworship_template_bundle(kind: str) -> dict[str, Any]:
    override = os.environ.get(EASYWORSHIP_TEMPLATE_ENV, "").strip()
    if override and kind == "video":
        template_path = Path(override).expanduser()
        if not template_path.exists():
            raise FileNotFoundError(f"EasyWorship template override was not found: {template_path}")
        if template_path.suffix.lower() != ".ewsx":
            raise ValueError(
                f"{EASYWORSHIP_TEMPLATE_ENV} must point to a valid .ewsx file, got: {template_path}"
            )
        bundle = extract_ewsx_members(template_path)
        bundle["template_source"] = str(template_path)
        return bundle
    return _embedded_easyworship_template_bundle(kind)


def _template_media_member(members: list[dict[str, Any]]) -> dict[str, Any]:
    for member in members:
        normalized = str(member.get("name", "")).replace("/", "\\").lower()
        if normalized.startswith("media\\"):
            return member
    raise ValueError("EasyWorship template is missing its packed media member.")


def _template_main_db_bytes(template_bundle: dict[str, Any]) -> bytes:
    template_main_db = next(
        (bytes(member["content"]) for member in template_bundle["members"] if str(member.get("name", "")).lower() == "main.db"),
        None,
    )
    if template_main_db is None:
        raise ValueError("EasyWorship template is missing main.db.")
    return template_main_db


def _media_modified_ticks(original_path: str | None, fallback: int) -> int:
    if not original_path:
        return fallback
    try:
        source_path = Path(original_path)
        if source_path.exists():
            return _ew_ticks(datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC))
    except OSError:
        pass
    return fallback


def _easyworship_original_media_name(item: AgendaItem, title: str, suffix: str) -> str:
    candidate = Path(item.original_path).name if item.original_path else ""
    packaged_name = Path(item.packaged_name).name if item.packaged_name else ""
    if candidate and candidate.lower() != packaged_name.lower():
        return candidate
    if title.lower().endswith(suffix.lower()):
        return title
    return f"{title}{suffix}"


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _fetch_rows(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [_row_to_dict(row) or {} for row in conn.execute(query, params).fetchall()]


def _fetch_rows_by_ids(conn: sqlite3.Connection, table: str, column: str, ids: list[int]) -> list[dict[str, Any]]:
    if not ids:
        return []
    placeholders = ", ".join("?" for _ in ids)
    return _fetch_rows(conn, f"SELECT * FROM {table} WHERE {column} IN ({placeholders}) ORDER BY rowid", tuple(ids))


def _media_table_for_kind(kind: str) -> str:
    return "resource_video" if kind == "video" else "resource_image"


def _item_internal_suffix(item: AgendaItem, fallback_name: str) -> str:
    return (
        Path(item.original_path).suffix
        or Path(item.packaged_name).suffix
        or Path(fallback_name).suffix
        or (".mp4" if item.kind == "video" else ".png")
    ).lower()


def _display_title_for_original(original_filename: str, fallback: str) -> str:
    return Path(original_filename).stem or fallback


def _internal_filename_for_item(template_internal_name: str, item: AgendaItem, position: int, *, keep_template_stem: bool) -> str:
    suffix = _item_internal_suffix(item, template_internal_name)
    if keep_template_stem:
        return f"{Path(template_internal_name).stem}{suffix}"
    title = item.title or Path(item.original_path or item.packaged_name or template_internal_name).stem or "Untitled"
    return _easyworship_filename(title, suffix, position)


def _template_original_media_name(block: dict[str, Any]) -> str:
    original_filename = str(block["media_row"].get("original_filename") or "")
    if block["kind"] == "video":
        original_filename = original_filename.removeprefix("<videos>")
    return Path(original_filename).name


def _media_item_matches_template(
    block: dict[str, Any],
    *,
    title: str,
    original_filename: str,
    internal_filename: str,
    file_bytes: bytes,
) -> bool:
    template_hash = str(block["file_row"].get("file_hash") or "")
    if not template_hash:
        return False
    return (
        title == str(block["presentation_row"].get("title") or "")
        and original_filename == _template_original_media_name(block)
        and internal_filename == str(block.get("template_internal_name") or "")
        and hashlib.sha256(file_bytes).hexdigest() == template_hash
    )


def _invalidate_presentation_thumbnails(
    conn: sqlite3.Connection,
    presentation_id: int,
    *,
    thumbnail_slide_id: int | None = None,
) -> None:
    revision = _ew_ticks()
    if thumbnail_slide_id is None:
        row = conn.execute(
            "SELECT rowid FROM slide WHERE presentation_id = ? ORDER BY order_index, rowid LIMIT 1",
            (presentation_id,),
        ).fetchone()
        thumbnail_slide_id = int(row[0]) if row is not None else None

    conn.execute(
        """
        UPDATE slide
           SET layout_revision = ?,
               thumbnail_desired_rev = ?,
               thumbnail_rev = 0,
               thumbnail = NULL
         WHERE presentation_id = ?
        """,
        (revision, revision, presentation_id),
    )
    conn.execute(
        """
        UPDATE presentation
           SET thumbnail_slide_id = ?,
               layout_revision = ?,
               thumbnail_desired_rev = ?,
               thumbnail_rev = 0,
               thumbnail = NULL,
               modified_date = ?
         WHERE rowid = ?
        """,
        (thumbnail_slide_id, revision, revision, revision, presentation_id),
    )


def _next_rowid(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COALESCE(MAX(rowid), 0) + 1 FROM {table}").fetchone()[0])


def _insert_row(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    columns = list(row.keys())
    placeholders = ", ".join("?" for _ in columns)
    column_list = ", ".join(columns)
    conn.execute(f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})", tuple(row[column] for column in columns))


def _load_template_media_block(template_bundle: dict[str, Any], kind: str) -> dict[str, Any]:
    presentation_type = EASYWORSHIP_MEDIA_PRESENTATION_TYPES[kind]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        tmp.write(_template_main_db_bytes(template_bundle))
        template_db_path = Path(tmp.name)
    try:
        conn = sqlite3.connect(template_db_path)
        conn.row_factory = sqlite3.Row
        presentation_row = _row_to_dict(
            conn.execute(
                "SELECT * FROM presentation WHERE presentation_type = ? ORDER BY rowid LIMIT 1",
                (presentation_type,),
            ).fetchone()
        )
        if presentation_row is None:
            raise ValueError(f"EasyWorship {kind} template is missing its media presentation.")

        slide_rows = _fetch_rows(conn, "SELECT * FROM slide WHERE presentation_id = ? ORDER BY rowid", (presentation_row["rowid"],))
        slide_ids = [int(row["rowid"]) for row in slide_rows]
        element_rows = _fetch_rows_by_ids(conn, "element", "slide_id", slide_ids)
        slide_property_group_rows = _fetch_rows_by_ids(conn, "slide_property_group", "link_id", slide_ids)
        slide_property_group_ids = [int(row["rowid"]) for row in slide_property_group_rows]
        slide_property_rows = _fetch_rows_by_ids(conn, "slide_property", "group_id", slide_property_group_ids)

        element_ids = [int(row["rowid"]) for row in element_rows]
        element_property_group_rows = _fetch_rows_by_ids(conn, "element_property_group", "link_id", element_ids)
        element_property_group_ids = [int(row["rowid"]) for row in element_property_group_rows]
        element_property_rows = _fetch_rows_by_ids(conn, "element_property", "group_id", element_property_group_ids)

        resource_ids = sorted(
            {
                int(resource_id)
                for row in element_rows
                for resource_id in (row["background_resource_id"], row["foreground_resource_id"], row["shape_resource_id"])
                if resource_id is not None
            }
        )
        resource_rows = _fetch_rows_by_ids(conn, "resource", "rowid", resource_ids)
        background_resource_id = next(
            int(row["background_resource_id"])
            for row in element_rows
            if row["element_uid"] == "BACKGROUND" and row["background_resource_id"] is not None
        )
        media_resource_id = next(
            int(row["foreground_resource_id"])
            for row in element_rows
            if row["element_uid"] == "BACKGROUND" and row["foreground_resource_id"] is not None
        )
        title_resource_id = next(
            (
                int(row["foreground_resource_id"])
                for row in element_rows
                if row["element_uid"] == "TITLE" and row["foreground_resource_id"] is not None
            ),
            None,
        )
        cloned_resource_ids = [int(row["rowid"]) for row in resource_rows if int(row["rowid"]) != background_resource_id]
        resource_shape_rows = _fetch_rows_by_ids(conn, "resource_shape", "resource_id", cloned_resource_ids)
        resource_text_rows = _fetch_rows_by_ids(conn, "resource_text", "resource_id", cloned_resource_ids)
        media_table = _media_table_for_kind(kind)
        media_row = _row_to_dict(
            conn.execute(
                f"SELECT * FROM {media_table} WHERE resource_id = ? ORDER BY rowid LIMIT 1",
                (media_resource_id,),
            ).fetchone()
        )
        if media_row is None:
            raise ValueError(f"EasyWorship {kind} template is missing its {media_table} row.")
        file_row = _row_to_dict(conn.execute("SELECT * FROM file WHERE rowid = ?", (media_row["file_id"],)).fetchone())
        if file_row is None:
            raise ValueError(f"EasyWorship {kind} template is missing the file row for its media resource.")
        template_media_member = _template_media_member(template_bundle["members"])
        return {
            "kind": kind,
            "presentation_type": presentation_type,
            "presentation_row": presentation_row,
            "slide_rows": slide_rows,
            "element_rows": element_rows,
            "slide_property_group_rows": slide_property_group_rows,
            "slide_property_rows": slide_property_rows,
            "element_property_group_rows": element_property_group_rows,
            "element_property_rows": element_property_rows,
            "resource_rows": resource_rows,
            "resource_shape_rows": resource_shape_rows,
            "resource_text_rows": resource_text_rows,
            "media_row": media_row,
            "file_row": file_row,
            "media_table": media_table,
            "background_resource_id": background_resource_id,
            "media_resource_id": media_resource_id,
            "title_resource_id": title_resource_id,
            "template_member_name": str(template_media_member["name"]),
            "template_internal_name": Path(str(template_media_member["name"]).replace("\\", "/")).name,
            "base_order_index": int(presentation_row["order_index"] or 0),
        }
    finally:
        conn.close()
        template_db_path.unlink(missing_ok=True)


def _apply_media_item_to_block(
    conn: sqlite3.Connection,
    block: dict[str, Any],
    item: AgendaItem,
    file_bytes: bytes,
    internal_filename: str,
    *,
    order_index: int | None = None,
) -> dict[str, Any]:
    title = item.title or Path(item.original_path or item.packaged_name or internal_filename).stem or "Untitled"
    source_suffix = Path(internal_filename).suffix or _item_internal_suffix(item, internal_filename)
    original_filename = _easyworship_original_media_name(item, title, source_suffix)
    display_title = _display_title_for_original(original_filename, title)
    presentation_rowid = int(block["presentation_row"]["rowid"])
    template_matches = _media_item_matches_template(
        block,
        title=title,
        original_filename=original_filename,
        internal_filename=internal_filename,
        file_bytes=file_bytes,
    )
    media_resource_id = int(block["media_resource_id"])
    media_row = block["media_row"]
    media_rowid = int(media_row["rowid"])
    fallback_modified = int(media_row.get("modified_date") or _ew_ticks())
    modified_ticks = _media_modified_ticks(item.original_path, fallback_modified)

    if order_index is None:
        conn.execute("UPDATE presentation SET title = ? WHERE rowid = ?", (title, presentation_rowid))
    else:
        conn.execute(
            "UPDATE presentation SET title = ?, order_index = ? WHERE rowid = ?",
            (title, order_index, presentation_rowid),
        )
    conn.execute("UPDATE resource SET title = ? WHERE rowid = ?", (title, media_resource_id))
    if block.get("title_resource_id") is not None:
        title_resource_id = int(block["title_resource_id"])
        conn.execute("UPDATE resource SET title = ? WHERE rowid = ?", (display_title, title_resource_id))
        conn.execute("UPDATE resource_text SET rtf = ? WHERE resource_id = ?", (_rtf_title(display_title), title_resource_id))
    conn.execute(
        "UPDATE file SET file_hash = ?, filename = ? WHERE rowid = ?",
        (hashlib.sha256(file_bytes).hexdigest(), internal_filename, int(block["file_row"]["rowid"])),
    )

    if item.kind == "video":
        probe = _probe_video_metadata(file_bytes, source_suffix)
        width = int(probe["width"] or media_row["width"] or 0)
        height = int(probe["height"] or media_row["height"] or 0)
        duration_ticks = int(probe["duration_ticks"] or media_row["duration"] or 0)
        video_stream_count = int(probe["video_stream_count"] or media_row["video_stream_count"] or 0)
        audio_stream_count = int(probe["audio_stream_count"] or media_row["audio_stream_count"] or 0)
        video_stream_type = int(probe["video_stream_type"] or media_row["video_stream_type"] or 0)
        audio_stream_type = int(probe["audio_stream_type"] or media_row["audio_stream_type"] or 0)
        audio_stream_profile = int(probe["audio_stream_profile"] or media_row["audio_stream_profile"] or 0)
        conn.execute(
            """
            UPDATE resource_video
               SET original_filename = ?,
                   filesize = ?,
                   modified_date = ?,
                   width = ?,
                   height = ?,
                   duration = ?,
                   video_stream_count = ?,
                   audio_stream_count = ?,
                   video_stream_type = ?,
                   audio_stream_type = ?,
                   audio_stream_profile = ?
             WHERE rowid = ?
            """,
            (
                f"<videos>{original_filename}",
                len(file_bytes),
                modified_ticks,
                width,
                height,
                duration_ticks,
                video_stream_count,
                audio_stream_count,
                video_stream_type,
                audio_stream_type,
                audio_stream_profile,
                media_rowid,
            ),
        )
    else:
        width = int(media_row["width"] or 0)
        height = int(media_row["height"] or 0)
        conn.execute(
            """
            UPDATE resource_image
               SET original_filename = ?,
                   filesize = ?,
                   modified_date = ?,
                   width = ?,
                   height = ?
             WHERE rowid = ?
            """,
            (
                item.original_path or original_filename,
                len(file_bytes),
                modified_ticks,
                width,
                height,
                media_rowid,
            ),
        )

    if not template_matches:
        _invalidate_presentation_thumbnails(conn, presentation_rowid)

    return {
        "presentation_id": presentation_rowid,
        "schedule_index": int(item.index),
        "title": title,
        "display_title": display_title,
        "filename": internal_filename,
        "kind": item.kind,
        "member_name": f"media\\{internal_filename}",
        "template_member_name": str(block["template_member_name"]),
        "order_index": order_index if order_index is not None else int(block["presentation_row"]["order_index"] or 0),
    }


def _append_media_block_from_template(
    conn: sqlite3.Connection,
    block: dict[str, Any],
    item: AgendaItem,
    file_bytes: bytes,
    internal_filename: str,
    *,
    order_index: int,
) -> dict[str, Any]:
    shared_color_resource_id = conn.execute("SELECT rowid FROM resource WHERE resource_uid = 'COLOR' ORDER BY rowid LIMIT 1").fetchone()
    if shared_color_resource_id is None:
        raise ValueError("EasyWorship database is missing the shared COLOR resource.")
    resource_map = {int(block["background_resource_id"]): int(shared_color_resource_id[0])}
    new_presentation_id = _next_rowid(conn, "presentation")
    new_presentation_uid = _ew_uid()

    presentation_row = dict(block["presentation_row"])
    presentation_row["rowid"] = new_presentation_id
    presentation_row["presentation_uid"] = new_presentation_uid
    presentation_row["presentation_rev_uid"] = _ew_uid()
    presentation_row["order_index"] = order_index
    _insert_row(conn, "presentation", presentation_row)

    slide_map: dict[int, int] = {}
    for row in block["slide_rows"]:
        new_row = dict(row)
        new_rowid = _next_rowid(conn, "slide")
        slide_map[int(row["rowid"])] = new_rowid
        new_row["rowid"] = new_rowid
        new_row["presentation_id"] = new_presentation_id
        new_row["slide_uid"] = _ew_uid()
        new_row["slide_rev_uid"] = _ew_uid()
        _insert_row(conn, "slide", new_row)

    if presentation_row.get("thumbnail_slide_id") is not None:
        conn.execute(
            "UPDATE presentation SET thumbnail_slide_id = ? WHERE rowid = ?",
            (slide_map.get(int(presentation_row["thumbnail_slide_id"])), new_presentation_id),
        )

    cloned_resource_rows = [row for row in block["resource_rows"] if int(row["rowid"]) != int(block["background_resource_id"])]
    for row in cloned_resource_rows:
        new_row = dict(row)
        new_resource_id = _next_rowid(conn, "resource")
        resource_map[int(row["rowid"])] = new_resource_id
        new_row["rowid"] = new_resource_id
        if int(row["rowid"]) == int(block["media_resource_id"]):
            new_uid = new_presentation_uid
        else:
            new_uid = _ew_uid()
        new_row["resource_uid"] = new_uid
        new_row["resource_hash"] = _resource_hash(new_uid)
        _insert_row(conn, "resource", new_row)

    file_map: dict[int, int] = {}
    file_row = dict(block["file_row"])
    new_file_id = _next_rowid(conn, "file")
    file_map[int(file_row["rowid"])] = new_file_id
    file_row["rowid"] = new_file_id
    _insert_row(conn, "file", file_row)

    for row in block["resource_shape_rows"]:
        new_row = dict(row)
        new_row["rowid"] = _next_rowid(conn, "resource_shape")
        new_row["resource_id"] = resource_map[int(row["resource_id"])]
        _insert_row(conn, "resource_shape", new_row)

    for row in block["resource_text_rows"]:
        new_row = dict(row)
        new_row["rowid"] = _next_rowid(conn, "resource_text")
        new_row["resource_id"] = resource_map[int(row["resource_id"])]
        _insert_row(conn, "resource_text", new_row)

    media_row = dict(block["media_row"])
    media_row["rowid"] = _next_rowid(conn, block["media_table"])
    media_row["resource_id"] = resource_map[int(media_row["resource_id"])]
    media_row["file_id"] = file_map[int(media_row["file_id"])]
    _insert_row(conn, block["media_table"], media_row)

    element_map: dict[int, int] = {}
    for row in block["element_rows"]:
        new_row = dict(row)
        new_rowid = _next_rowid(conn, "element")
        element_map[int(row["rowid"])] = new_rowid
        new_row["rowid"] = new_rowid
        new_row["slide_id"] = slide_map[int(row["slide_id"])]
        for key in ("background_resource_id", "foreground_resource_id", "shape_resource_id"):
            value = row[key]
            new_row[key] = resource_map[int(value)] if value is not None else None
        _insert_row(conn, "element", new_row)

    slide_property_group_map: dict[int, int] = {}
    for row in block["slide_property_group_rows"]:
        new_row = dict(row)
        new_rowid = _next_rowid(conn, "slide_property_group")
        slide_property_group_map[int(row["rowid"])] = new_rowid
        new_row["rowid"] = new_rowid
        new_row["link_id"] = slide_map[int(row["link_id"])]
        _insert_row(conn, "slide_property_group", new_row)

    for row in block["slide_property_rows"]:
        new_row = dict(row)
        new_row["rowid"] = _next_rowid(conn, "slide_property")
        new_row["group_id"] = slide_property_group_map[int(row["group_id"])]
        _insert_row(conn, "slide_property", new_row)

    element_property_group_map: dict[int, int] = {}
    for row in block["element_property_group_rows"]:
        new_row = dict(row)
        new_rowid = _next_rowid(conn, "element_property_group")
        element_property_group_map[int(row["rowid"])] = new_rowid
        new_row["rowid"] = new_rowid
        new_row["link_id"] = element_map[int(row["link_id"])]
        _insert_row(conn, "element_property_group", new_row)

    for row in block["element_property_rows"]:
        new_row = dict(row)
        new_row["rowid"] = _next_rowid(conn, "element_property")
        new_row["group_id"] = element_property_group_map[int(row["group_id"])]
        _insert_row(conn, "element_property", new_row)

    cloned_block = {
        **block,
        "presentation_row": {**block["presentation_row"], "rowid": new_presentation_id, "order_index": order_index},
        "media_resource_id": resource_map[int(block["media_resource_id"])],
        "title_resource_id": resource_map.get(int(block["title_resource_id"])) if block.get("title_resource_id") is not None else None,
        "file_row": {**block["file_row"], "rowid": new_file_id},
        "media_row": {**block["media_row"], "rowid": media_row["rowid"]},
    }
    return _apply_media_item_to_block(conn, cloned_block, item, file_bytes, internal_filename, order_index=order_index)


def _build_easyworship_template_database(
    db_path: Path,
    template_bundles: dict[str, dict[str, Any]],
    items: list[AgendaItem],
    media_bytes: dict[str, bytes],
) -> dict[str, Any]:
    base_kind = items[0].kind
    base_bundle = template_bundles[base_kind]
    template_blocks = {kind: _load_template_media_block(bundle, kind) for kind, bundle in template_bundles.items()}

    db_path.write_bytes(_template_main_db_bytes(base_bundle))
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        base_block = template_blocks[base_kind]
        base_order_index = int(base_block["base_order_index"])
        item_manifests: list[dict[str, Any]] = []

        first_internal_filename = _internal_filename_for_item(base_block["template_internal_name"], items[0], 0, keep_template_stem=True)
        first_order_index = None if len(items) == 1 else base_order_index
        item_manifests.append(
            _apply_media_item_to_block(
                conn,
                base_block,
                items[0],
                media_bytes[items[0].bundled_member],
                first_internal_filename,
                order_index=first_order_index,
            )
        )

        for position, item in enumerate(items[1:], start=1):
            block = template_blocks[item.kind]
            internal_filename = _internal_filename_for_item(block["template_internal_name"], item, position, keep_template_stem=False)
            item_manifests.append(
                _append_media_block_from_template(
                    conn,
                    block,
                    item,
                    media_bytes[item.bundled_member],
                    internal_filename,
                    order_index=base_order_index + position,
                )
            )
        conn.commit()
    finally:
        conn.close()

    with sqlite3.connect(db_path) as conn:
        global_row = conn.execute(
            "SELECT rowid FROM presentation WHERE presentation_type = 11 ORDER BY rowid LIMIT 1"
        ).fetchone()

    return {
        "version": EASYWORSHIP_VERSION,
        "template_source": base_bundle.get("template_source"),
        "template_sources": {kind: bundle.get("template_source") for kind, bundle in template_bundles.items()},
        "item_count": len(items),
        "global_presentation_id": int(global_row[0]) if global_row is not None else None,
        "items": item_manifests,
    }


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
            text_parts = []
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


def extract_project_text_shows(project_path: str | Path) -> list[dict[str, Any]]:
    source_path = Path(project_path)
    with zipfile.ZipFile(source_path) as zf:
        data = json.loads(zf.read("data.json"))
        project = data.get("project", {})
        project_shows = project.get("shows", [])
        named_shows = data.get("shows", {})

        text_shows: list[dict[str, Any]] = []
        for entry in project_shows:
            if not isinstance(entry, dict) or entry.get("type") is not None:
                continue
            show_id = str(entry.get("id") or "").strip()
            show = named_shows.get(show_id)
            if not show:
                continue

            layouts = show.get("layouts", {})
            active_layout = str(show.get("settings", {}).get("activeLayout") or "")
            if not active_layout or active_layout not in layouts:
                active_layout = next(iter(layouts), "")
            if not active_layout:
                continue

            layout = layouts.get(active_layout) or {}
            show_media = show.get("media", {}) if isinstance(show.get("media", {}), dict) else {}
            slides_by_id = show.get("slides", {}) if isinstance(show.get("slides", {}), dict) else {}
            slide_payloads: list[dict[str, Any]] = []
            bundled_backgrounds: dict[str, dict[str, Any]] = {}

            for layout_index, layout_entry in enumerate(layout.get("slides", [])):
                if not isinstance(layout_entry, dict):
                    continue
                slide_id = str(layout_entry.get("id") or "")
                slide = slides_by_id.get(slide_id)
                if not isinstance(slide, dict):
                    continue

                text_lines = _freeshow_text_lines(slide)
                if not text_lines:
                    continue

                background_bundled_member: str | None = None
                background_id = str(layout_entry.get("background") or "")
                if background_id and background_id in show_media:
                    background_meta = show_media.get(background_id) or {}
                    background_kind = str(background_meta.get("type") or "").lower()
                    original_path = str(background_meta.get("path") or "").strip()
                    bundled_member = _find_project_member_by_path(zf, original_path) if original_path else None
                    if bundled_member and background_kind in {"image", "video"}:
                        background_bundled_member = bundled_member
                        bundled_backgrounds.setdefault(
                            bundled_member,
                            {
                                "bundled_member": bundled_member,
                                "kind": background_kind,
                                "original_path": original_path,
                                "title": Path(original_path).stem or Path(bundled_member).stem,
                            },
                        )

                slide_title = str(slide.get("group") or text_lines[0]).strip() or f"Slide {layout_index + 1}"
                slide_payloads.append(
                    {
                        "title": slide_title,
                        "lines": text_lines,
                        "background_member": background_bundled_member,
                    }
                )

            if slide_payloads:
                text_shows.append(
                    {
                        "show_id": show_id,
                        "title": str(show.get("name") or f"Song {len(text_shows) + 1}").strip() or f"Song {len(text_shows) + 1}",
                        "schedule_index": int(entry.get("index") or 0),
                        "slides": slide_payloads,
                        "backgrounds": bundled_backgrounds,
                    }
                )

        return text_shows


def _escape_rtf_text(text: str) -> str:
    escaped: list[str] = []
    for char in text:
        if char == "\\":
            escaped.append("\\\\")
        elif char == "{":
            escaped.append("\\{")
        elif char == "}":
            escaped.append("\\}")
        elif char == "\n":
            escaped.append("\\line ")
        elif ord(char) > 127:
            escaped.append(f"\\u{ord(char)}?")
        else:
            escaped.append(char)
    return "".join(escaped)


def _rtf_song_content(lines: list[str]) -> str:
    body = "\\line ".join(_escape_rtf_text(line) for line in lines if line.strip())
    return (
        "{\\rtf1\\ansi\\deff0\\sdeasyworship2\r\n"
        "{\\fonttbl{\\f0 Tahoma;}}\r\n"
        "{\\colortbl ;}\r\n"
        f"{{\\pard\\qc\\qdef\\sdewparatemplatestyle101{{\\*\\sdasfactor 1}}{{\\*\\sdasbaseline 73.5}}\\sdastextstyle101\\plain\\sdewtemplatestyle101\\fs148{{\\*\\sdfsreal 73.5}}{{\\*\\sdfsdef 73.5}}\\sdfsauto {body}\\par}}\r\n"
        "}"
    )


def _rtf_empty_song_copyright() -> str:
    return (
        "{\\rtf1\\ansi\\deff0\\sdeasyworship2\r\n"
        "{\\fonttbl{\\f0 Tahoma;}}\r\n"
        "{\\colortbl ;}\r\n"
        "{\\pard\\sdlistlevel0\\ql\\qdef\\plain\\fs28{\\*\\sdfsreal 14.3999996185303}{\\*\\sdfsdef 14.3999996185303}\\sdfsauto\\par}\r\n"
        "}"
    )


def _unique_easyworship_filename(used_names: set[str], title: str, ext: str, seed: int) -> str:
    attempt = seed
    while True:
        candidate = _easyworship_filename(title, ext, attempt)
        normalized = candidate.lower()
        if normalized not in used_names:
            used_names.add(normalized)
            return candidate
        attempt += 1


def _insert_resource(
    conn: sqlite3.Connection,
    *,
    resource_type: int,
    title: str = "",
    author: str = "",
    copyright_text: str = "",
    description: str = "",
    tags: str = "",
) -> int:
    resource_id = _next_rowid(conn, "resource")
    resource_uid = _ew_uid()
    _insert_row(
        conn,
        "resource",
        {
            "rowid": resource_id,
            "resource_hash": _resource_hash(resource_uid),
            "resource_uid": resource_uid,
            "resource_type": resource_type,
            "title": title,
            "author": author,
            "copyright": copyright_text,
            "description": description,
            "tags": tags,
        },
    )
    return resource_id


def _insert_text_resource(conn: sqlite3.Connection, rtf: str) -> int:
    resource_id = _insert_resource(conn, resource_type=6)
    _insert_row(
        conn,
        "resource_text",
        {
            "rowid": _next_rowid(conn, "resource_text"),
            "resource_id": resource_id,
            "rtf": rtf,
        },
    )
    return resource_id


def _insert_media_resource(
    conn: sqlite3.Connection,
    *,
    kind: str,
    title: str,
    original_path: str,
    internal_filename: str,
    file_bytes: bytes,
) -> dict[str, Any]:
    modified_ticks = _media_modified_ticks(original_path, _ew_ticks())
    file_id = _next_rowid(conn, "file")
    _insert_row(
        conn,
        "file",
        {
            "rowid": file_id,
            "file_hash": hashlib.sha256(file_bytes).hexdigest(),
            "filename": internal_filename,
            "shared_filename": "",
        },
    )

    resource_type = 1 if kind == "video" else 2
    resource_id = _insert_resource(conn, resource_type=resource_type, title=title)
    media_row = {
        "rowid": _next_rowid(conn, _media_table_for_kind(kind)),
        "resource_id": resource_id,
        "file_id": file_id,
        "original_filename": Path(original_path).name if kind == "image" else f"<videos>{Path(original_path).name}",
        "filesize": len(file_bytes),
        "modified_date": modified_ticks,
    }

    if kind == "video":
        probe = _probe_video_metadata(file_bytes, Path(internal_filename).suffix)
        media_row.update(
            {
                "start_pos": -1,
                "end_pos": -1,
                "poster_frame_pos": -1,
                "width": int(probe["width"] or 0),
                "height": int(probe["height"] or 0),
                "duration": int(probe["duration_ticks"] or 0),
                "repeating": 0,
                "alpha_channel_mode": 0,
                "video_stream_count": int(probe["video_stream_count"] or 0),
                "audio_stream_count": int(probe["audio_stream_count"] or 0),
                "video_stream_type": int(probe["video_stream_type"] or 0),
                "audio_stream_type": int(probe["audio_stream_type"] or 0),
                "audio_stream_profile": int(probe["audio_stream_profile"] or 0),
            }
        )
    else:
        width, height = _probe_image_size(file_bytes)
        media_row.update({"width": width, "height": height})

    _insert_row(conn, _media_table_for_kind(kind), media_row)
    return {
        "resource_id": resource_id,
        "file_id": file_id,
        "internal_filename": internal_filename,
    }


def _insert_element_with_groups(
    conn: sqlite3.Connection,
    *,
    slide_id: int,
    element_uid: str,
    element_type: int,
    element_style_type: int,
    order_index: int,
    x: float,
    y: float,
    width: float,
    height: float,
    background_resource_id: int | None,
    foreground_resource_id: int | None,
    shape_resource_id: int | None,
    from_master: int,
    groups: list[tuple[str, list[tuple[int, str, str]]]],
) -> int:
    element_id = _next_rowid(conn, "element")
    _insert_row(
        conn,
        "element",
        {
            "rowid": element_id,
            "slide_id": slide_id,
            "element_uid": element_uid,
            "element_type": element_type,
            "element_style_type": element_style_type,
            "order_index": order_index,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "background_resource_id": background_resource_id,
            "foreground_resource_id": foreground_resource_id,
            "shape_resource_id": shape_resource_id,
            "internal_mute": 0,
            "from_master": from_master,
        },
    )
    for group_name, props in groups:
        group_id = _next_rowid(conn, "element_property_group")
        _insert_row(
            conn,
            "element_property_group",
            {"rowid": group_id, "link_id": element_id, "group_name": group_name},
        )
        for value_type, key, value in props:
            _insert_row(
                conn,
                "element_property",
                {
                    "rowid": _next_rowid(conn, "element_property"),
                    "group_id": group_id,
                    "value_type": value_type,
                    "key": key,
                    "value": value,
                },
            )
    return element_id


def _load_global_song_slide_template(conn: sqlite3.Connection) -> dict[str, Any]:
    global_row = conn.execute(
        "SELECT rowid FROM presentation WHERE presentation_type = 11 ORDER BY rowid LIMIT 1"
    ).fetchone()
    if global_row is None:
        raise ValueError("EasyWorship template database is missing its Global presentation.")
    slide_row = _row_to_dict(
        conn.execute(
            "SELECT * FROM slide WHERE presentation_id = ? AND title = 'Song' ORDER BY rowid LIMIT 1",
            (int(global_row[0]),),
        ).fetchone()
    )
    if slide_row is None:
        raise ValueError("EasyWorship template database is missing the Global Song slide.")
    element_rows = _fetch_rows(conn, "SELECT * FROM element WHERE slide_id = ? ORDER BY order_index, rowid", (int(slide_row["rowid"]),))
    element_ids = [int(row["rowid"]) for row in element_rows]
    property_group_rows = _fetch_rows_by_ids(conn, "element_property_group", "link_id", element_ids)
    property_group_ids = [int(row["rowid"]) for row in property_group_rows]
    property_rows = _fetch_rows_by_ids(conn, "element_property", "group_id", property_group_ids)
    return {
        "slide_row": slide_row,
        "element_rows": element_rows,
        "property_group_rows": property_group_rows,
        "property_rows": property_rows,
    }


def _append_song_presentations(
    conn: sqlite3.Connection,
    text_shows: list[dict[str, Any]],
    media_bytes: dict[str, bytes],
    used_media_names: set[str],
) -> dict[str, Any]:
    if not text_shows:
        return {"songs": [], "bundle_members": []}

    template = _load_global_song_slide_template(conn)
    template_groups_by_element: dict[int, list[dict[str, Any]]] = {}
    for group in template["property_group_rows"]:
        template_groups_by_element.setdefault(int(group["link_id"]), []).append(group)
    template_props_by_group: dict[int, list[dict[str, Any]]] = {}
    for prop in template["property_rows"]:
        template_props_by_group.setdefault(int(prop["group_id"]), []).append(prop)

    background_groups = [
        ("Background", []),
        ("Overrides", [(5, "mofBackground", "1"), (5, "mofForeground", "1")]),
        ("Foreground", [(5, "@changed", "1"), (5, "@mofChanged", "1")]),
    ]

    song_manifests: list[dict[str, Any]] = []
    bundle_members: list[dict[str, Any]] = []
    shared_backgrounds: dict[str, dict[str, Any]] = {}

    for show in text_shows:
        presentation_id = _next_rowid(conn, "presentation")
        presentation_revision = _ew_ticks()
        _insert_row(
            conn,
            "presentation",
            {
                "rowid": presentation_id,
                "presentation_uid": _ew_uid(),
                "presentation_rev_uid": _ew_uid(),
                "presentation_global_uid": None,
                "presentation_type": 6,
                "aspect_ratio": "",
                "group_level": 0,
                "order_index": int(show["schedule_index"]),
                "thumbnail_slide_id": None,
                "layout_revision": presentation_revision,
                "thumbnail_desired_rev": presentation_revision,
                "thumbnail_rev": 0,
                "thumbnail": None,
                "auto_theme": 0,
                "looping": 0,
                "title": str(show["title"]),
                "author": "",
                "copyright": "",
                "administrator": "",
                "description": "",
                "tags": "",
                "reference_number": "",
                "provider_id": 0,
                "vendor_id": None,
                "notes": "",
                "modified_date": presentation_revision,
                "ready": 1,
                "error_no": 0,
            },
        )

        slide_ids: list[int] = []
        for slide_index, slide in enumerate(show["slides"]):
            slide_id = _next_rowid(conn, "slide")
            slide_ids.append(slide_id)
            slide_revision = _ew_ticks()
            _insert_row(
                conn,
                "slide",
                {
                    "rowid": slide_id,
                    "presentation_id": presentation_id,
                    "title": str(slide["title"]),
                    "slide_uid": _ew_uid(),
                    "slide_rev_uid": _ew_uid(),
                    "order_index": slide_index,
                    "layout_flag": int(template["slide_row"]["layout_flag"]),
                    "theme_id": None,
                    "theme_slide_uid": str(template["slide_row"]["theme_slide_uid"] or "MASTER"),
                    "modified_theme_id": None,
                    "modified_theme_layout_revision": None,
                    "layout_revision": slide_revision,
                    "thumbnail_desired_rev": slide_revision,
                    "thumbnail_rev": 0,
                    "thumbnail": None,
                },
            )

            background_resource_id: int | None = None
            background_member = str(slide.get("background_member") or "")
            if background_member:
                background_meta = show["backgrounds"].get(background_member)
                if background_meta and background_member in media_bytes:
                    background_entry = shared_backgrounds.get(background_member)
                    if background_entry is None:
                        background_ext = Path(background_meta["original_path"]).suffix or Path(background_member).suffix or (
                            ".mp4" if background_meta["kind"] == "video" else ".png"
                        )
                        background_internal_name = _unique_easyworship_filename(
                            used_media_names,
                            str(background_meta["title"] or Path(background_member).stem or "background"),
                            background_ext,
                            10_000 + len(shared_backgrounds),
                        )
                        background_entry = _insert_media_resource(
                            conn,
                            kind=str(background_meta["kind"]),
                            title=str(background_meta["title"]),
                            original_path=str(background_meta["original_path"]),
                            internal_filename=background_internal_name,
                            file_bytes=media_bytes[background_member],
                        )
                        background_entry["kind"] = str(background_meta["kind"])
                        background_entry["member_name"] = f"media\\{background_internal_name}"
                        shared_backgrounds[background_member] = background_entry
                        bundle_members.append(
                            {
                                "kind": str(background_meta["kind"]),
                                "name": f"media\\{background_internal_name}",
                                "content": media_bytes[background_member],
                            }
                        )
                    background_resource_id = int(background_entry["resource_id"])

            song_text_resource_id = _insert_text_resource(conn, _rtf_song_content(list(slide["lines"])))
            copyright_resource_id = _insert_text_resource(conn, _rtf_empty_song_copyright())

            for template_element in template["element_rows"]:
                element_uid = str(template_element["element_uid"])
                groups: list[tuple[str, list[tuple[int, str, str]]]] = []
                for group in template_groups_by_element.get(int(template_element["rowid"]), []):
                    props = [
                        (int(prop["value_type"]), str(prop["key"]), str(prop["value"]))
                        for prop in template_props_by_group.get(int(group["rowid"]), [])
                    ]
                    groups.append((str(group["group_name"]), props))

                background_id = template_element["background_resource_id"]
                foreground_id = template_element["foreground_resource_id"]
                element_type = int(template_element["element_type"])
                if element_uid == "BACKGROUND" and background_resource_id is not None:
                    background_id = 1
                    foreground_id = background_resource_id
                    element_type = 1 if shared_backgrounds[background_member]["kind"] == "video" else 2
                    groups = background_groups
                elif element_uid == "CONTENT_SONG":
                    foreground_id = song_text_resource_id
                elif element_uid == "COPYRIGHT":
                    foreground_id = copyright_resource_id

                _insert_element_with_groups(
                    conn,
                    slide_id=slide_id,
                    element_uid=element_uid,
                    element_type=element_type,
                    element_style_type=int(template_element["element_style_type"]),
                    order_index=int(template_element["order_index"]),
                    x=float(template_element["x"]),
                    y=float(template_element["y"]),
                    width=float(template_element["width"]),
                    height=float(template_element["height"]),
                    background_resource_id=int(background_id) if background_id is not None else None,
                    foreground_resource_id=int(foreground_id) if foreground_id is not None else None,
                    shape_resource_id=int(template_element["shape_resource_id"]) if template_element["shape_resource_id"] is not None else None,
                    from_master=int(template_element["from_master"] or 0),
                    groups=groups,
                )

        _invalidate_presentation_thumbnails(conn, presentation_id, thumbnail_slide_id=slide_ids[0] if slide_ids else None)
        song_manifests.append(
            {
                "presentation_id": presentation_id,
                "schedule_index": int(show["schedule_index"]),
                "title": str(show["title"]),
                "slide_count": len(slide_ids),
            }
        )

    return {"songs": song_manifests, "bundle_members": bundle_members}


def _apply_schedule_order_indices(
    conn: sqlite3.Connection,
    entries: list[dict[str, Any]],
    *,
    global_presentation_id: int | None = None,
) -> None:
    ordered_entries = sorted(
        enumerate(entries),
        key=lambda pair: (int(pair[1]["schedule_index"]), pair[0]),
    )
    for order_index, (_original_position, entry) in enumerate(ordered_entries):
        conn.execute(
            "UPDATE presentation SET order_index = ? WHERE rowid = ?",
            (order_index, int(entry["presentation_id"])),
        )
    if global_presentation_id is not None:
        conn.execute(
            "UPDATE presentation SET order_index = ? WHERE rowid = ?",
            (len(ordered_entries), int(global_presentation_id)),
        )


def _find_member_by_name(members: dict[str, BundleMember], filename: str) -> BundleMember | None:
    target = filename.replace("/", "\\").lower()
    for name, member in members.items():
        normalized = name.replace("/", "\\").lower()
        if normalized == target or normalized.endswith("\\" + target):
            return member
    return None


def _freeshow_id(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:11]


def _rtf_to_plain_text(rtf: str) -> str:
    output: list[str] = []
    index = 0
    unicode_skip = 1
    pending_skip = 0

    while index < len(rtf):
        char = rtf[index]
        if pending_skip:
            pending_skip -= 1
            index += 1
            continue
        if char in "{}":
            index += 1
            continue
        if char != "\\":
            output.append(char)
            index += 1
            continue

        index += 1
        if index >= len(rtf):
            break
        control = rtf[index]
        if control in "\\{}":
            output.append(control)
            index += 1
            continue
        if control == "'":
            hex_value = rtf[index + 1 : index + 3]
            try:
                output.append(bytes.fromhex(hex_value).decode("cp1252"))
            except ValueError:
                pass
            index += 3
            continue

        start = index
        while index < len(rtf) and rtf[index].isalpha():
            index += 1
        word = rtf[start:index]

        sign = 1
        if index < len(rtf) and rtf[index] == "-":
            sign = -1
            index += 1
        number_start = index
        while index < len(rtf) and rtf[index].isdigit():
            index += 1
        number = sign * int(rtf[number_start:index]) if number_start != index else None

        if index < len(rtf) and rtf[index] == " ":
            index += 1

        if word in {"par", "line"}:
            output.append("\n")
        elif word == "tab":
            output.append("\t")
        elif word == "u" and number is not None:
            output.append(chr(number if number >= 0 else 65536 + number))
            pending_skip = unicode_skip
        elif word == "uc" and number is not None:
            unicode_skip = max(0, number)

    text = "".join(output)
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _rtf_to_freeshow_lines(rtf: str) -> list[dict[str, Any]]:
    extracted = re.findall(r"\\sdfsauto\s*(.*?)\\par", rtf, flags=re.S)
    if extracted:
        raw_lines = [_rtf_to_plain_text(chunk) for chunk in extracted]
        plain_text = "\n".join(line.strip() for line in raw_lines if line.strip())
    else:
        plain_text = _rtf_to_plain_text(rtf)
    font_size_match = RTF_FONT_SIZE_PATTERN.search(rtf)
    font_size = max(48, int(font_size_match.group(1)) // 2) if font_size_match else 100
    style = f"font-size:{font_size}px;font-family:Tahoma;font-weight:bold;color:#FFFFFF;text-transform:none;"
    lines = []
    for raw_line in plain_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lines.append({"align": "text-align: center", "text": [{"style": style, "value": line}]})
    return lines


def _default_text_item(lines: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "style": "top:120px;left:50px;height:840px;width:1820px;",
        "lines": lines,
        "align": "",
        "auto": True,
        "textFit": "shrinkToFit",
        "specialStyle": {"lineBg": ""},
        "scrolling": {"type": "none"},
        "autoFontSize": 100,
    }


def _empty_easyworship_project_manifest(project_name: str) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    return {
        "project": {
            "name": project_name,
            "created": now_ms,
            "parent": "/",
            "shows": [],
            "modified": now_ms,
            "used": now_ms,
            "id": _freeshow_id(f"project:{project_name}:{now_ms}"),
        },
        "parentFolder": "",
        "shows": {},
        "files": [],
        "media": {},
    }


def _append_media_reference(manifest: dict[str, Any], item: AgendaItem) -> None:
    import_path = freeshow_import_path(item.packaged_name)
    manifest["project"]["shows"].append({"name": item.title, "id": import_path, "type": item.kind, "index": item.index})
    manifest["files"].append(import_path)
    if item.kind in {"video", "audio"}:
        manifest.setdefault("media", {})[import_path] = {"tracks": []}


def _append_text_show_reference(
    manifest: dict[str, Any],
    *,
    show_id: str,
    show_name: str,
    schedule_index: int,
    slide_payloads: list[dict[str, Any]],
    bundled_backgrounds: list[tuple[str, str]],
    category: str = "easyworship",
) -> None:
    active_layout = _freeshow_id(f"layout:{show_id}")
    slides: dict[str, Any] = {}
    layout_slides: list[dict[str, Any]] = []
    local_media: dict[str, Any] = {}
    background_ids: dict[str, str] = {}

    for import_path, _member in bundled_backgrounds:
        background_id = _freeshow_id(f"{show_id}:background:{import_path}")
        background_ids[import_path] = background_id
        local_media[background_id] = {
            "name": Path(import_path).stem,
            "path": import_path,
            "type": "video" if Path(import_path).suffix.lower() in {".mp4", ".mov", ".m4v", ".avi", ".wmv"} else "image",
        }

    for order_index, payload in enumerate(slide_payloads):
        slide_id = _freeshow_id(f"{show_id}:slide:{order_index}")
        slides[slide_id] = {
            "group": payload["group"],
            "color": None,
            "settings": {},
            "notes": "",
            "items": [_default_text_item(payload["lines"])],
            "globalGroup": payload["global_group"],
        }
        layout_entry: dict[str, Any] = {"id": slide_id}
        if payload["background"] is not None:
            layout_entry["background"] = background_ids[payload["background"]]
        layout_slides.append(layout_entry)

    manifest["project"]["shows"].append({"id": show_id, "index": schedule_index})
    manifest["shows"][show_id] = {
        "name": show_name,
        "private": False,
        "category": category,
        "settings": {"activeLayout": active_layout, "template": "default"},
        "timestamps": {"created": int(time.time() * 1000), "modified": None, "used": None},
        "quickAccess": {},
        "meta": {"title": show_name},
        "slides": slides,
        "layouts": {active_layout: {"name": "Default", "notes": "", "slides": layout_slides}},
        "media": local_media,
    }

    for import_path, _member in bundled_backgrounds:
        if import_path not in manifest["files"]:
            manifest["files"].append(import_path)
        manifest.setdefault("media", {}).setdefault(import_path, {"tracks": []})


def _sort_project_schedule(manifest: dict[str, Any]) -> None:
    shows = manifest.get("project", {}).get("shows")
    if not isinstance(shows, list):
        return
    shows.sort(key=lambda entry: int(entry.get("index", 0)))


def extract_easyworship_text_shows(ewsx_path: str | Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    source_path = Path(ewsx_path)
    members = {member.name: member for member in _scan_bundle_members(source_path)}
    main_db = members.get("main.db")
    if main_db is None:
        raise ValueError(f"Missing main.db in EasyWorship export: {source_path}")

    temp_root = Path.cwd() / ".easyworship_db_cache"
    temp_dir = _reset_workspace_dir(temp_root / f"{sanitize_filename(source_path.stem)}_{uuid.uuid4().hex}")
    try:
        db_path = temp_dir / "main.db"
        db_path.write_bytes(_read_bundle_member(source_path, main_db))
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            presentations = conn.execute(
                """
                SELECT rowid, title, order_index
                FROM presentation
                WHERE presentation_type = 6
                ORDER BY order_index, rowid
                """
            ).fetchall()
            slide_rows = conn.execute(
                """
                SELECT
                  p.rowid AS presentation_id,
                  s.rowid AS slide_id,
                  s.order_index AS slide_order,
                  rt.rtf AS content_rtf,
                  f.filename AS background_filename
                FROM presentation p
                JOIN slide s ON s.presentation_id = p.rowid
                LEFT JOIN element content_e ON content_e.slide_id = s.rowid AND content_e.element_uid = 'CONTENT_SONG'
                LEFT JOIN resource_text rt ON rt.resource_id = content_e.foreground_resource_id
                LEFT JOIN element bg_e ON bg_e.slide_id = s.rowid AND bg_e.element_uid = 'BACKGROUND'
                LEFT JOIN resource_image ri ON ri.resource_id = bg_e.foreground_resource_id
                LEFT JOIN resource_video rv ON rv.resource_id = bg_e.foreground_resource_id
                LEFT JOIN file f ON f.rowid = COALESCE(ri.file_id, rv.file_id)
                WHERE p.presentation_type = 6
                ORDER BY p.order_index, s.order_index
                """
            ).fetchall()
        finally:
            conn.close()
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        if temp_root.exists() and not any(temp_root.iterdir()):
            temp_root.rmdir()

    slides_by_presentation: dict[int, list[sqlite3.Row]] = {}
    for row in slide_rows:
        slides_by_presentation.setdefault(int(row["presentation_id"]), []).append(row)

    background_member_map: dict[str, str] = {}
    text_shows: list[dict[str, Any]] = []
    for presentation in presentations:
        show_name = str(presentation["title"] or "EasyWorship Song").strip()
        show_id = _freeshow_id(f"easyworship-show:{presentation['rowid']}:{show_name}")
        slide_payloads: list[dict[str, Any]] = []
        bundled_backgrounds: list[tuple[str, str]] = []

        for row in slides_by_presentation.get(int(presentation["rowid"]), []):
            rtf = str(row["content_rtf"] or "")
            lines = _rtf_to_freeshow_lines(rtf)
            if not lines:
                continue
            background_import_path: str | None = None
            background_filename = str(row["background_filename"] or "").strip()
            if background_filename:
                bundled_member = _find_member_by_name(members, f"media\\{background_filename}") or _find_member_by_name(members, background_filename)
                if bundled_member is not None:
                    packaged_name = Path(background_filename).name
                    background_import_path = freeshow_import_path(packaged_name)
                    background_member_map[background_import_path] = bundled_member.name
                    bundled_backgrounds.append((background_import_path, bundled_member.name))

            first_line = str(lines[0]["text"][0]["value"]).strip()
            slide_payloads.append(
                {
                    "group": first_line[:40],
                    "global_group": "verse",
                    "lines": lines,
                    "background": background_import_path,
                }
            )

        if slide_payloads:
            text_shows.append(
                {
                    "show_id": show_id,
                    "show_name": show_name,
                    "schedule_index": int(presentation["order_index"] or 0),
                    "slides": slide_payloads,
                    "backgrounds": bundled_backgrounds,
                }
            )

    return text_shows, background_member_map


def _reset_workspace_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_easyworship_items(ewsx_path: str | Path) -> list[AgendaItem]:
    source_path = Path(ewsx_path)
    members = {member.name: member for member in _scan_bundle_members(source_path)}
    main_db = members.get("main.db")
    if main_db is None:
        raise ValueError(f"Missing main.db in EasyWorship export: {source_path}")

    temp_root = Path.cwd() / ".easyworship_db_cache"
    temp_dir = _reset_workspace_dir(temp_root / f"{sanitize_filename(source_path.stem)}_{uuid.uuid4().hex}")
    try:
        db_path = temp_dir / "main.db"
        db_path.write_bytes(_read_bundle_member(source_path, main_db))
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT
                  p.rowid AS presentation_id,
                  p.title AS presentation_title,
                  p.order_index AS presentation_order,
                  s.order_index AS slide_order,
                  CASE
                    WHEN rv.file_id IS NOT NULL THEN 'video'
                    WHEN ri.file_id IS NOT NULL THEN 'image'
                    ELSE ''
                  END AS kind,
                  COALESCE(f.filename, '') AS bundled_filename,
                  COALESCE(rv.original_filename, ri.original_filename, '') AS original_filename
                FROM presentation p
                JOIN slide s ON s.presentation_id = p.rowid
                JOIN element e ON e.slide_id = s.rowid AND e.order_index = 0
                LEFT JOIN resource_video rv ON rv.resource_id = e.foreground_resource_id
                LEFT JOIN resource_image ri ON ri.resource_id = e.foreground_resource_id
                LEFT JOIN file f ON f.rowid = COALESCE(rv.file_id, ri.file_id)
                WHERE p.presentation_type IN (1, 2)
                  AND COALESCE(f.filename, '') <> ''
                ORDER BY p.order_index, s.order_index, p.rowid
                """
            ).fetchall()
        finally:
            conn.close()
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        if temp_root.exists() and not any(temp_root.iterdir()):
            temp_root.rmdir()

    items: list[AgendaItem] = []
    taken_names: set[str] = set()
    seen_presentation_ids: set[int] = set()
    for row in rows:
        presentation_id = int(row["presentation_id"])
        if presentation_id in seen_presentation_ids:
            continue
        seen_presentation_ids.add(presentation_id)
        bundled_member = _find_member_by_name(members, f"media\\{row['bundled_filename']}") or _find_member_by_name(members, row["bundled_filename"])
        if bundled_member is None:
            continue
        title = str(row["presentation_title"] or Path(row["bundled_filename"]).stem)
        ext = Path(row["bundled_filename"]).suffix
        items.append(
            AgendaItem(
                index=int(row["presentation_order"] or 0),
                kind=str(row["kind"]),
                source_manifest="main.db",
                title=title,
                original_path=str(row["original_filename"] or f"C:\\EasyWorship\\Media\\{sanitize_filename(title)}{ext}"),
                bundled_member=bundled_member.name,
                packaged_name=unique_name(taken_names, Path(row["bundled_filename"]).name),
                flow_type=0 if row["kind"] == "video" else 2,
                auto_advance=0,
                interval=5000,
            )
        )
    return items


def _write_easyworship_database(db_path: Path, items: list[AgendaItem], media_bytes: dict[str, bytes]) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA page_size=1024")
        conn.executescript(MINIMAL_SCHEMA)
        conn.executescript(MINIMAL_INDEXES)
        conn.execute("INSERT INTO info (rowid, version, version_min) VALUES (1, ?, ?)", (EASYWORSHIP_VERSION, EASYWORSHIP_MIN_VERSION))
        conn.execute(
            "INSERT INTO resource (rowid, resource_hash, resource_uid, resource_type, title, author, copyright, description, tags) VALUES (1, ?, 'COLOR', 8, '', '', '', '', '')",
            (_resource_hash("COLOR"),),
        )
        conn.execute("INSERT INTO resource_color (resource_id, color) VALUES (1, 0)")
        now_ticks = _ew_ticks()
        file_manifest: list[dict[str, Any]] = []
        global_presentation_id = len(items) + 1
        next_slide_id = 1
        next_resource_id = 2
        next_file_id = 1
        next_element_id = 1
        next_shape_rowid = 1
        next_group_id = 1
        next_prop_id = 1

        def insert_resource_shape(resource_id: int) -> None:
            nonlocal next_shape_rowid
            conn.execute(
                "INSERT INTO resource_shape (rowid, resource_id, shape_data) VALUES (?, ?, ?)",
                (next_shape_rowid, resource_id, DEFAULT_SHAPE_XML),
            )
            next_shape_rowid += 1

        def insert_element(
            slide_id: int,
            element_uid: str,
            element_type: int,
            style_type: int,
            order_index: int,
            x: float,
            y: float,
            width: float,
            height: float,
            background_resource_id: int | None,
            foreground_resource_id: int | None,
            shape_resource_id: int | None,
            from_master: int,
            groups: list[tuple[str, list[tuple[int, str, str]]]],
        ) -> None:
            nonlocal next_element_id, next_group_id, next_prop_id
            element_id = next_element_id
            next_element_id += 1
            conn.execute(
                """
                INSERT INTO element (
                  rowid, slide_id, element_uid, element_type, element_style_type, order_index, x, y, width, height,
                  background_resource_id, foreground_resource_id, shape_resource_id, internal_mute, from_master
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    element_id,
                    slide_id,
                    element_uid,
                    element_type,
                    style_type,
                    order_index,
                    x,
                    y,
                    width,
                    height,
                    background_resource_id,
                    foreground_resource_id,
                    shape_resource_id,
                    from_master,
                ),
            )
            for group_name, props in groups:
                group_id = next_group_id
                next_group_id += 1
                conn.execute(
                    "INSERT INTO element_property_group (rowid, link_id, group_name) VALUES (?, ?, ?)",
                    (group_id, element_id, group_name),
                )
                for value_type, key, value in props:
                    conn.execute(
                        "INSERT INTO element_property (rowid, group_id, value_type, key, value) VALUES (?, ?, ?, ?, ?)",
                        (next_prop_id, group_id, value_type, key, value),
                    )
                    next_prop_id += 1

        global_shape_specs = [
            (-651578433, "1-03F57BE2-0A93-4E46-A9F7-3A8AF0C05D8C"),
            (-1047288673, "1-B39F0FC6-6767-49D3-AB11-1546BB427703"),
            (-1594693513, "1-22FC0AB8-A323-47E6-A53C-FA7C4E3B3071"),
            (1447673860, "1-2ABDFC0C-4150-41DD-93A0-135DA65A6360"),
            (1498951319, "1-E2FCEA76-45B3-4F83-8843-A603F4351BE8"),
            (377907375, "1-8D1D9D70-FAB6-4AAC-B503-D17A485ED117"),
            (456684068, "1-340262E9-64BB-4CCA-81CD-F21A1169BC91"),
        ]

        for order_index, item in enumerate(items):
            presentation_id = order_index + 1
            slide_id = next_slide_id
            next_slide_id += 1
            presentation_uid = _ew_uid()
            presentation_type = 1 if item.kind == "video" else 2
            media_resource_id = next_resource_id
            bg_shape_id = next_resource_id + 1
            title_text_id = next_resource_id + 2
            title_shape_id = next_resource_id + 3
            next_resource_id += 4

            ext = Path(item.packaged_name).suffix or Path(item.original_path).suffix or ""
            ew_filename = _easyworship_filename(item.title, ext, order_index)
            member_name = f"media/{ew_filename}"
            file_bytes = media_bytes[item.bundled_member]
            original_name = item.original_path or f"C:\\EasyWorship\\Media\\{ew_filename}"

            conn.execute(
                """
                INSERT INTO presentation (
                  rowid, presentation_uid, presentation_rev_uid, presentation_global_uid, presentation_type,
                  aspect_ratio, group_level, order_index, thumbnail_slide_id, layout_revision,
                  thumbnail_desired_rev, thumbnail_rev, thumbnail, auto_theme, looping, title,
                  author, copyright, administrator, description, tags, reference_number,
                  provider_id, vendor_id, notes, modified_date, ready, error_no
                ) VALUES (?, ?, ?, NULL, ?, '', 0, ?, NULL, ?, ?, ?, NULL, 0, 0, ?, '', '', '', '', '', '', 0, NULL, '', ?, 1, 0)
                """,
                (presentation_id, presentation_uid, _ew_uid(), presentation_type, order_index, now_ticks, now_ticks, now_ticks, item.title, now_ticks),
            )
            conn.execute(
                """
                INSERT INTO slide (
                  rowid, presentation_id, title, slide_uid, slide_rev_uid, order_index, layout_flag, theme_id,
                  theme_slide_uid, modified_theme_id, modified_theme_layout_revision, layout_revision,
                  thumbnail_desired_rev, thumbnail_rev, thumbnail
                ) VALUES (?, ?, '', ?, NULL, 0, 3, NULL, ?, NULL, NULL, ?, ?, ?, NULL)
                """,
                (
                    slide_id,
                    presentation_id,
                    _ew_uid(),
                    "" if item.kind == "video" else "MASTER",
                    now_ticks,
                    now_ticks,
                    now_ticks,
                ),
            )
            if item.kind == "video":
                conn.execute(
                    "INSERT INTO slide_property_group (rowid, link_id, group_name) VALUES (?, ?, 'SlideAdvance')",
                    (presentation_id, slide_id),
                )

            conn.execute(
                "INSERT INTO file (rowid, file_hash, filename, shared_filename) VALUES (?, ?, ?, NULL)",
                (next_file_id, hashlib.sha256(file_bytes).hexdigest(), ew_filename),
            )
            conn.execute(
                """
                INSERT INTO resource (rowid, resource_hash, resource_uid, resource_type, title, author, copyright, description, tags)
                VALUES (?, ?, ?, ?, ?, '', '', '', '')
                """,
                (media_resource_id, _resource_hash(f"media:{ew_filename}"), presentation_uid, presentation_type, item.title),
            )
            conn.execute(
                """
                INSERT INTO resource (rowid, resource_hash, resource_uid, resource_type, title, author, copyright, description, tags)
                VALUES (?, ?, ?, 13, '', '', '', '', '')
                """,
                (bg_shape_id, _resource_hash(f"shape:bg:{item.title}:{order_index}"), _ew_uid()),
            )
            insert_resource_shape(bg_shape_id)
            conn.execute(
                """
                INSERT INTO resource (rowid, resource_hash, resource_uid, resource_type, title, author, copyright, description, tags)
                VALUES (?, ?, ?, 6, ?, '', '', '', '')
                """,
                (title_text_id, _resource_hash(f"title:{item.title}:{order_index}"), _ew_uid(), item.title),
            )
            conn.execute("INSERT INTO resource_text (resource_id, rtf) VALUES (?, ?)", (title_text_id, _rtf_title(item.title)))
            conn.execute(
                """
                INSERT INTO resource (rowid, resource_hash, resource_uid, resource_type, title, author, copyright, description, tags)
                VALUES (?, ?, ?, 13, '', '', '', '', '')
                """,
                (title_shape_id, _resource_hash(f"shape:title:{item.title}:{order_index}"), _ew_uid()),
            )
            insert_resource_shape(title_shape_id)

            if item.kind == "video":
                meta = _probe_video_metadata(file_bytes, ext)
                original_video_name = f"<videos>{Path(original_name).name}"
                conn.execute(
                    """
                    INSERT INTO resource_video (
                      rowid, resource_id, file_id, original_filename, filesize, modified_date, start_pos, end_pos,
                      poster_frame_pos, width, height, duration, repeating, alpha_channel_mode,
                      video_stream_count, audio_stream_count, video_stream_type, audio_stream_type, audio_stream_profile
                    ) VALUES (?, ?, ?, ?, ?, ?, -1, -1, -1, ?, ?, ?, NULL, 0, ?, ?, ?, ?, ?)
                    """,
                    (
                        next_file_id,
                        media_resource_id,
                        next_file_id,
                        original_video_name,
                        len(file_bytes),
                        now_ticks,
                        meta["width"],
                        meta["height"],
                        meta["duration_ticks"],
                        meta["video_stream_count"],
                        meta["audio_stream_count"],
                        meta["video_stream_type"],
                        meta["audio_stream_type"],
                        meta["audio_stream_profile"],
                    ),
                )
            else:
                width, height = _probe_image_size(file_bytes)
                conn.execute(
                    """
                    INSERT INTO resource_image (
                      rowid, resource_id, file_id, original_filename, filesize, modified_date, width, height
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (next_file_id, media_resource_id, next_file_id, original_name, len(file_bytes), now_ticks, width, height),
                )

            insert_element(
                slide_id,
                "BACKGROUND",
                presentation_type,
                0,
                0,
                0.0,
                0.0,
                1.0,
                1.0,
                1,
                media_resource_id,
                bg_shape_id,
                0,
                [
                    ("Background", []),
                    ("Overrides", [(5, "mofBackground", "1"), (5, "mofForeground", "1")]),
                    ("Foreground", [(5, "Interactive", "1")]),
                ],
            )
            insert_element(slide_id, "AUDIO", 5, 0, 1, 0.0, 0.0, 1.0, 1.0, None, None, None, 0, [])
            insert_element(
                slide_id,
                "TITLE",
                6,
                6,
                2,
                0.0,
                0.0,
                1.0,
                1.0,
                None,
                title_text_id,
                title_shape_id,
                0,
                [
                    ("Element", [(5, "Hidden", "1")]),
                    ("Text_Format", []),
                    ("Overrides", [(5, "mofText", "1")]),
                ],
            )

            file_manifest.append({"title": item.title, "filename": ew_filename, "kind": item.kind, "member_name": member_name})
            next_file_id += 1

        global_slide_ids = [next_slide_id + offset for offset in range(4)]
        global_resource_ids = list(range(next_resource_id, next_resource_id + len(global_shape_specs)))
        next_resource_id += len(global_shape_specs)

        conn.execute(
            """
            INSERT INTO presentation (
              rowid, presentation_uid, presentation_rev_uid, presentation_global_uid, presentation_type,
              aspect_ratio, group_level, order_index, thumbnail_slide_id, layout_revision,
              thumbnail_desired_rev, thumbnail_rev, thumbnail, auto_theme, looping, title,
              author, copyright, administrator, description, tags, reference_number,
              provider_id, vendor_id, notes, modified_date, ready, error_no
            ) VALUES (?, 'GLOBAL', ?, NULL, 11, '', 2, 0, NULL, ?, ?, ?, NULL, 0, 0, 'Global', '', '', '', '', '', '', 0, NULL, '', ?, 1, 0)
            """,
            (global_presentation_id, _ew_uid(), now_ticks, now_ticks, now_ticks, 133682760697490000),
        )

        for resource_id, (resource_hash, resource_uid) in zip(global_resource_ids, global_shape_specs, strict=True):
            conn.execute(
                """
                INSERT INTO resource (rowid, resource_hash, resource_uid, resource_type, title, author, copyright, description, tags)
                VALUES (?, ?, ?, 13, '', '', '', '', '')
                """,
                (resource_id, resource_hash, resource_uid),
            )
            insert_resource_shape(resource_id)

        for slide_id, title, slide_uid, order_index, layout_flag, theme_slide_uid in [
            (global_slide_ids[0], "Master", "MASTER", 0, 19, ""),
            (global_slide_ids[1], "Song", "SONG", 1, 2083, "MASTER"),
            (global_slide_ids[2], "Scripture", "SCRIPTURE", 2, 67, "MASTER"),
            (global_slide_ids[3], "Presentation", "PRESENTATION", 3, 143, "MASTER"),
        ]:
            conn.execute(
                """
                INSERT INTO slide (
                  rowid, presentation_id, title, slide_uid, slide_rev_uid, order_index, layout_flag, theme_id,
                  theme_slide_uid, modified_theme_id, modified_theme_layout_revision, layout_revision,
                  thumbnail_desired_rev, thumbnail_rev, thumbnail
                ) VALUES (?, ?, ?, ?, NULL, ?, ?, NULL, ?, NULL, NULL, ?, ?, ?, NULL)
                """,
                (slide_id, global_presentation_id, title, slide_uid, order_index, layout_flag, theme_slide_uid, now_ticks, now_ticks, now_ticks),
            )
        next_slide_id += 4

        insert_element(global_slide_ids[0], "BACKGROUND", 0, 0, 0, 0.0, 0.0, 1.0, 1.0, None, None, None, 0, [("Background", []), ("Foreground", []), ("Shape", [])])
        insert_element(global_slide_ids[0], "AUDIO", 5, 0, 1, 0.0, 0.0, 1.0, 1.0, None, None, None, 0, [("Background", []), ("Foreground", []), ("Shape", [])])
        insert_element(global_slide_ids[0], "CONTENT", 6, 1, 2, 0.0, 0.0, 1.0, 1.0, None, None, global_resource_ids[0], 0, [("Shape", []), ("Background", []), ("Overrides", [(5, "mofDims", "1")]), ("Foreground", [])])

        insert_element(global_slide_ids[1], "BACKGROUND", 0, 0, 0, 0.0, 0.0, 1.0, 1.0, None, None, None, 0, [("Background", []), ("Foreground", []), ("Shape", [])])
        insert_element(global_slide_ids[1], "AUDIO", 5, 0, 1, 0.0, 0.0, 1.0, 1.0, None, None, None, 0, [("Background", []), ("Foreground", []), ("Shape", [])])
        insert_element(
            global_slide_ids[1],
            "CONTENT_SONG",
            6,
            4,
            2,
            0.0,
            0.0,
            1.0,
            1.0,
            None,
            None,
            global_resource_ids[1],
            0,
            [
                ("Text_Style_101", [(5, "@changed", "1"), (2, "Outline_Size", "0.00133333333333333"), (2, "Shadow_Offset", "0.00333333333333333"), (2, "Font_Size", "0.120987654320988"), (0, "Shadow_Angle", "285"), (3, "Font_Name", "Noto Sans JP")]),
                ("Overrides", [(5, "mofText", "1"), (5, "mofDims", "1")]),
                ("Background", []),
                ("Text_Format", [(5, "@changed", "1"), (5, "Capitalize_All", "1"), (5, "Capitalize_Proper", "1")]),
                ("Text_Style_102", [(5, "@changed", "1"), (2, "Font_Size", "0.120987654320988")]),
                ("Foreground", []),
                ("Shape", []),
                ("Text_Layout", [(5, "@changed", "1"), (6, "Vertical_Alignment", "1")]),
            ],
        )
        insert_element(global_slide_ids[1], "COPYRIGHT", 6, 8, 3, 0.0, 0.9200000166893, 1.0, 0.0799999982118607, None, None, global_resource_ids[2], 0, [("Shape", []), ("Background", []), ("Text_Format", []), ("Overrides", [(5, "mofText", "1"), (5, "mofDims", "1")]), ("Foreground", [])])

        insert_element(global_slide_ids[2], "BACKGROUND", 0, 0, 0, 0.0, 0.0, 1.0, 1.0, None, None, None, 0, [("Background", []), ("Foreground", []), ("Shape", [])])
        insert_element(global_slide_ids[2], "AUDIO", 5, 0, 1, 0.0, 0.0, 1.0, 1.0, None, None, None, 0, [("Background", []), ("Foreground", []), ("Shape", [])])
        insert_element(
            global_slide_ids[2],
            "CONTENT_SCRIPTURE",
            6,
            5,
            2,
            0.0,
            0.0,
            1.0,
            1.0,
            None,
            None,
            global_resource_ids[3],
            0,
            [
                ("Text_Style_202", [(5, "@changed", "1"), (6, "Text_Alignment", "1"), (5, "Font_Underline", "1"), (0, "Font_Color", "13421619"), (2, "Font_Size", "0.06")]),
                ("Overrides", [(5, "mofText", "1"), (5, "mofDims", "1")]),
                ("Background", []),
                ("Text_Format", []),
                ("Text_Style_201", [(5, "@changed", "1"), (6, "Text_Alignment", "1"), (2, "Outline_Size", "0"), (2, "Shadow_Offset", "0.0133333333333333"), (2, "Shadow_Blur", "0.00666666666666667")]),
                ("Foreground", []),
                ("Text_Style_203", [(5, "@changed", "1"), (5, "Hidden", "1"), (2, "Font_Size", "0.09")]),
                ("Text_Margins", [(5, "@changed", "1"), (2, "Top", "0.0143229166666667"), (2, "Bottom", "0.0143229166666667"), (2, "Right", "0.0185546875"), (2, "Left", "0.0185546875")]),
                ("Shape", []),
            ],
        )

        insert_element(global_slide_ids[3], "BACKGROUND", 0, 0, 0, 0.0, 0.0, 1.0, 1.0, None, None, None, 0, [("Background", []), ("Foreground", []), ("Shape", [])])
        insert_element(global_slide_ids[3], "AUDIO", 5, 0, 1, 0.0, 0.0, 1.0, 1.0, None, None, None, 0, [("Background", []), ("Foreground", []), ("Shape", [])])
        insert_element(global_slide_ids[3], "TITLE", 6, 6, 2, 0.0199999995529652, 0.0266660004854202, 0.959999978542328, 0.150000005960464, None, None, global_resource_ids[4], 0, [("Shape", []), ("Background", []), ("Text_Format", []), ("Overrides", [(5, "mofText", "1"), (5, "mofDims", "1")]), ("Foreground", [])])
        insert_element(global_slide_ids[3], "SUBTITLE", 6, 7, 3, 0.0199999995529652, 0.203332006931305, 0.959999978542328, 0.0750000029802322, None, None, global_resource_ids[5], 0, [("Shape", []), ("Background", []), ("Text_Format", []), ("Overrides", [(5, "mofText", "1"), (5, "mofDims", "1")]), ("Foreground", [])])
        insert_element(global_slide_ids[3], "CONTENT_PRESENTATION", 6, 3, 4, 0.0199999995529652, 0.304998010396957, 0.959999978542328, 0.668335974216461, None, None, global_resource_ids[6], 0, [("Shape", []), ("Background", []), ("Text_Format", []), ("Overrides", [(5, "mofText", "1"), (5, "mofDims", "1")]), ("Foreground", [])])

        conn.execute("INSERT INTO presentation_property_group_global (rowid, link_id, group_name) VALUES (1, ?, 'Default_Scripture_BK')", (global_presentation_id,))
        conn.execute("INSERT INTO presentation_property_group_global (rowid, link_id, group_name) VALUES (2, ?, 'Scripture_Attributes')", (global_presentation_id,))
        conn.execute("INSERT INTO presentation_property_group_global (rowid, link_id, group_name) VALUES (3, ?, 'Default_Song_BK')", (global_presentation_id,))
        conn.execute("INSERT INTO presentation_property_global (rowid, group_id, value_type, key, value) VALUES (1, 1, 6, 'FileType', '11')")
        conn.execute("INSERT INTO presentation_property_global (rowid, group_id, value_type, key, value) VALUES (2, 1, 1, 'ID', '59')")
        conn.execute("INSERT INTO presentation_property_global (rowid, group_id, value_type, key, value) VALUES (3, 2, 6, 'Reference_Location', '0')")
        conn.execute("INSERT INTO presentation_property_global (rowid, group_id, value_type, key, value) VALUES (4, 3, 6, 'FileType', '11')")
        conn.execute("INSERT INTO presentation_property_global (rowid, group_id, value_type, key, value) VALUES (5, 3, 1, 'ID', '51')")

        conn.commit()
        return {"version": EASYWORSHIP_VERSION, "item_count": len(items), "items": file_manifest}
    finally:
        conn.close()


def _seed_easyworship_defaults(conn: sqlite3.Connection) -> None:
    now_ticks = _ew_ticks()

    def add_shape_resource(next_id: int, seed: str) -> int:
        conn.execute(
            """
            INSERT INTO resource (rowid, resource_hash, resource_uid, resource_type, title, author, copyright, description, tags)
            VALUES (?, ?, ?, 13, '', '', '', '', '')
            """,
            (next_id, _resource_hash(seed), _ew_uid()),
        )
        conn.execute("INSERT INTO resource_shape (resource_id, shape_data) VALUES (?, ?)", (next_id, DEFAULT_SHAPE_XML))
        return next_id

    # Type 13 default background/theme presentation.
    conn.execute(
        """
        INSERT INTO presentation (
          rowid, presentation_uid, presentation_rev_uid, presentation_global_uid, presentation_type,
          aspect_ratio, group_level, order_index, thumbnail_slide_id, layout_revision,
          thumbnail_desired_rev, thumbnail_rev, thumbnail, auto_theme, looping, title,
          author, copyright, administrator, description, tags, reference_number,
          provider_id, vendor_id, notes, modified_date, ready, error_no
        ) VALUES (37, ?, '6.0.7', NULL, 13, '', 1, 0, NULL, ?, ?, ?, NULL, 1, 0, 'bg4', '', '', '', '', '', '', 0, NULL, '', ?, 1, 0)
        """,
        (_ew_uid(), now_ticks, now_ticks, now_ticks, now_ticks),
    )
    conn.execute(
        """
        INSERT INTO slide (
          rowid, presentation_id, title, slide_uid, slide_rev_uid, order_index, layout_flag, theme_id,
          theme_slide_uid, modified_theme_id, modified_theme_layout_revision, layout_revision,
          thumbnail_desired_rev, thumbnail_rev, thumbnail
        ) VALUES (36, 37, 'Master', 'MASTER', NULL, 0, 2083, NULL, 'SONG', NULL, NULL, ?, ?, ?, NULL)
        """,
        (now_ticks, now_ticks, now_ticks),
    )
    bg_video_res = 169
    add_shape_resource(170, "default-bg-shape")
    add_shape_resource(171, "default-bg-song-content")
    add_shape_resource(172, "default-bg-copyright")
    add_shape_resource(173, "default-bg-scripture")
    conn.execute(
        """
        INSERT INTO resource (rowid, resource_hash, resource_uid, resource_type, title, author, copyright, description, tags)
        VALUES (?, ?, ?, 1, 'bg4', '', '', '', '')
        """,
        (bg_video_res, _resource_hash("default-bg-video"), _ew_uid()),
    )
    for rowid, element_uid, element_type, style_type, order_index, fg_id, shape_id in [
        (137, "BACKGROUND", 1, 0, 0, bg_video_res, 170),
        (138, "AUDIO", 5, 0, 1, None, None),
        (139, "CONTENT_SONG", 6, 4, 2, None, 171),
        (140, "COPYRIGHT", 6, 8, 3, None, 172),
        (141, "CONTENT_SCRIPTURE", 6, 5, 4, None, 173),
    ]:
        conn.execute(
            """
            INSERT INTO element (
              rowid, slide_id, element_uid, element_type, element_style_type, order_index, x, y, width, height,
              background_resource_id, foreground_resource_id, shape_resource_id, internal_mute, from_master
            ) VALUES (?, 36, ?, ?, ?, ?, 0.0, 0.0, 1.0, 1.0, ?, ?, ?, 0, 0)
            """,
            (rowid, element_uid, element_type, style_type, order_index, 1 if element_uid == "BACKGROUND" else None, fg_id, shape_id),
        )

    # Type 11 global presentation.
    conn.execute(
        """
        INSERT INTO presentation (
          rowid, presentation_uid, presentation_rev_uid, presentation_global_uid, presentation_type,
          aspect_ratio, group_level, order_index, thumbnail_slide_id, layout_revision,
          thumbnail_desired_rev, thumbnail_rev, thumbnail, auto_theme, looping, title,
          author, copyright, administrator, description, tags, reference_number,
          provider_id, vendor_id, notes, modified_date, ready, error_no
        ) VALUES (41, 'GLOBAL', ?, NULL, 11, '', 2, 0, NULL, ?, ?, ?, NULL, 0, 0, 'Global', '', '', '', '', '', '', 0, NULL, '', ?, 1, 0)
        """,
        (_ew_uid(), now_ticks, now_ticks, now_ticks, now_ticks),
    )
    global_shapes = [24494, 24495, 24496, 24497, 24498, 24499, 24500]
    for index, shape_id in enumerate(global_shapes):
        add_shape_resource(shape_id, f"default-global-shape-{index}")
    global_slides = [
        (
            2476,
            "Master",
            "MASTER",
            0,
            19,
            "",
            [
                ("BACKGROUND", 0, 0, 0.0, 0.0, 1.0, 1.0, None, None),
                ("AUDIO", 5, 0, 0.0, 0.0, 1.0, 1.0, None, None),
                ("CONTENT", 6, 1, 0.0, 0.0, 1.0, 1.0, None, 24494),
            ],
        ),
        (
            2477,
            "Song",
            "SONG",
            1,
            2083,
            "MASTER",
            [
                ("BACKGROUND", 0, 0, 0.0, 0.0, 1.0, 1.0, None, None),
                ("AUDIO", 5, 0, 0.0, 0.0, 1.0, 1.0, None, None),
                ("CONTENT_SONG", 6, 4, 0.0, 0.0, 1.0, 1.0, None, 24495),
                ("COPYRIGHT", 6, 8, 0.0, 0.9200000166893, 1.0, 0.0799999982118607, None, 24496),
            ],
        ),
        (
            2478,
            "Scripture",
            "SCRIPTURE",
            2,
            67,
            "MASTER",
            [
                ("BACKGROUND", 0, 0, 0.0, 0.0, 1.0, 1.0, None, None),
                ("AUDIO", 5, 0, 0.0, 0.0, 1.0, 1.0, None, None),
                ("CONTENT_SCRIPTURE", 6, 5, 0.0, 0.0, 1.0, 1.0, None, 24497),
            ],
        ),
        (
            2479,
            "Presentation",
            "PRESENTATION",
            3,
            143,
            "MASTER",
            [
                ("BACKGROUND", 0, 0, 0.0, 0.0, 1.0, 1.0, None, None),
                ("AUDIO", 5, 0, 0.0, 0.0, 1.0, 1.0, None, None),
                ("TITLE", 6, 6, 0.0199999995529652, 0.0266660004854202, 0.959999978542328, 0.150000005960464, None, 24498),
                ("SUBTITLE", 6, 7, 0.0199999995529652, 0.203332006931305, 0.959999978542328, 0.0750000029802322, None, 24499),
                ("CONTENT_PRESENTATION", 6, 3, 0.0199999995529652, 0.304998010396957, 0.959999978542328, 0.668335974216461, None, 24500),
            ],
        ),
    ]
    next_element_rowid = 18414
    for slide_rowid, title, uid, order_index, layout_flag, theme_uid, elements in global_slides:
        conn.execute(
            """
            INSERT INTO slide (
              rowid, presentation_id, title, slide_uid, slide_rev_uid, order_index, layout_flag, theme_id,
              theme_slide_uid, modified_theme_id, modified_theme_layout_revision, layout_revision,
              thumbnail_desired_rev, thumbnail_rev, thumbnail
            ) VALUES (?, 41, ?, ?, NULL, ?, ?, NULL, ?, NULL, NULL, ?, ?, ?, NULL)
            """,
            (slide_rowid, title, uid, order_index, layout_flag, theme_uid, now_ticks, now_ticks, now_ticks),
        )
        element_order = 0
        for element_uid, element_type, style_type, x, y, width, height, fg_id, shape_id in elements:
            conn.execute(
                """
                INSERT INTO element (
                  rowid, slide_id, element_uid, element_type, element_style_type, order_index, x, y, width, height,
                  background_resource_id, foreground_resource_id, shape_resource_id, internal_mute, from_master
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, 0, 0)
                """,
                (next_element_rowid, slide_rowid, element_uid, element_type, style_type, element_order, x, y, width, height, fg_id, shape_id),
            )
            next_element_rowid += 1
            element_order += 1
    conn.execute("INSERT INTO presentation_property_group_global (rowid, link_id, group_name) VALUES (1, 41, 'Default_Scripture_BK')")
    conn.execute("INSERT INTO presentation_property_group_global (rowid, link_id, group_name) VALUES (2, 41, 'Scripture_Attributes')")
    conn.execute("INSERT INTO presentation_property_group_global (rowid, link_id, group_name) VALUES (3, 41, 'Default_Song_BK')")
    conn.execute("INSERT INTO presentation_property_global (rowid, group_id, value_type, key, value) VALUES (1, 1, 6, 'FileType', '11')")
    conn.execute("INSERT INTO presentation_property_global (rowid, group_id, value_type, key, value) VALUES (2, 1, 1, 'ID', '56')")
    conn.execute("INSERT INTO presentation_property_global (rowid, group_id, value_type, key, value) VALUES (3, 2, 6, 'Reference_Location', '0')")
    conn.execute("INSERT INTO presentation_property_global (rowid, group_id, value_type, key, value) VALUES (4, 3, 6, 'FileType', '11')")
    conn.execute("INSERT INTO presentation_property_global (rowid, group_id, value_type, key, value) VALUES (5, 3, 1, 'ID', '51')")

    # Type 12 blank presentation.
    conn.execute(
        """
        INSERT INTO presentation (
          rowid, presentation_uid, presentation_rev_uid, presentation_global_uid, presentation_type,
          aspect_ratio, group_level, order_index, thumbnail_slide_id, layout_revision,
          thumbnail_desired_rev, thumbnail_rev, thumbnail, auto_theme, looping, title,
          author, copyright, administrator, description, tags, reference_number,
          provider_id, vendor_id, notes, modified_date, ready, error_no
        ) VALUES (221, 'BLANK', '6.0.7', NULL, 12, '', 1, 0, NULL, ?, ?, ?, NULL, 1, 0, 'Blank', '', '', '', '', '', '', 0, NULL, '', ?, 1, 0)
        """,
        (now_ticks, now_ticks, now_ticks, now_ticks),
    )
    blank_shapes = list(range(17735, 17745))
    for shape_id in blank_shapes:
        add_shape_resource(shape_id, f"default-blank-shape-{shape_id}")
    blank_slides = [
        (
            1607,
            "Master",
            "MASTER",
            0,
            143,
            "PRESENTATION",
            [
                ("BACKGROUND", 0, 0, 0.0, 0.0, 1.0, 1.0, 17735),
                ("AUDIO", 5, 0, 0.0, 0.0, 1.0, 1.0, None),
                ("TITLE", 6, 6, 0.0199999995529652, 0.0266660004854202, 0.959999978542328, 0.150000005960464, 17735),
                ("SUBTITLE", 6, 7, 0.0199999995529652, 0.203332006931305, 0.959999978542328, 0.0750000029802322, 17736),
                ("CONTENT_PRESENTATION", 6, 3, 0.0199999995529652, 0.304998010396957, 0.959999978542328, 0.668335974216461, 17737),
                ("CONTENT_SCRIPTURE", 6, 5, 0.0, 0.0, 1.0, 1.0, 17738),
            ],
        ),
        (
            1608,
            "Title",
            "TITLE",
            1,
            15,
            "MASTER",
            [
                ("BACKGROUND", 0, 0, 0.0, 0.0, 1.0, 1.0, None),
                ("AUDIO", 5, 0, 0.0, 0.0, 1.0, 1.0, None),
                ("TITLE", 6, 6, 0.0199999995529652, 0.330000013113022, 0.959999978542328, 0.150000005960464, 17739),
                ("SUBTITLE", 6, 7, 0.0199999995529652, 0.506666004657745, 0.959999978542328, 0.0750000029802322, 17740),
            ],
        ),
        (
            1609,
            "Title & Content",
            "TITLE_CONTENT",
            2,
            135,
            "MASTER",
            [
                ("BACKGROUND", 0, 0, 0.0, 0.0, 1.0, 1.0, None),
                ("AUDIO", 5, 0, 0.0, 0.0, 1.0, 1.0, None),
                ("TITLE", 6, 6, 0.0199999995529652, 0.0266660004854202, 0.959999978542328, 0.150000005960464, 17741),
                ("CONTENT_PRESENTATION", 6, 3, 0.0199999995529652, 0.203332006931305, 0.959999978542328, 0.770002007484436, 17742),
            ],
        ),
        (
            1610,
            "Content Only",
            "CONTENT",
            3,
            131,
            "MASTER",
            [
                ("BACKGROUND", 0, 0, 0.0, 0.0, 1.0, 1.0, None),
                ("AUDIO", 5, 0, 0.0, 0.0, 1.0, 1.0, None),
                ("CONTENT_PRESENTATION", 6, 3, 0.0199999995529652, 0.0266660004854202, 0.959999978542328, 0.946668028831482, 17743),
            ],
        ),
        (
            1611,
            "Blank",
            "BLANK",
            4,
            3,
            "MASTER",
            [
                ("BACKGROUND", 0, 0, 0.0, 0.0, 1.0, 1.0, None),
                ("AUDIO", 5, 0, 0.0, 0.0, 1.0, 1.0, None),
            ],
        ),
        (
            1612,
            "Scripture",
            "SCRIPTURE",
            5,
            67,
            "MASTER",
            [
                ("BACKGROUND", 0, 0, 0.0, 0.0, 1.0, 1.0, None),
                ("AUDIO", 5, 0, 0.0, 0.0, 1.0, 1.0, None),
                ("CONTENT_SCRIPTURE", 6, 5, 0.0, 0.0, 1.0, 1.0, 17744),
            ],
        ),
    ]
    next_blank_element_id = 13449
    for slide_rowid, title, uid, order_index, layout_flag, theme_uid, elements in blank_slides:
        conn.execute(
            """
            INSERT INTO slide (
              rowid, presentation_id, title, slide_uid, slide_rev_uid, order_index, layout_flag, theme_id,
              theme_slide_uid, modified_theme_id, modified_theme_layout_revision, layout_revision,
              thumbnail_desired_rev, thumbnail_rev, thumbnail
            ) VALUES (?, 221, ?, ?, NULL, ?, ?, NULL, ?, NULL, NULL, ?, ?, ?, NULL)
            """,
            (slide_rowid, title, uid, order_index, layout_flag, theme_uid, now_ticks, now_ticks, now_ticks),
        )
        element_order = 0
        for element_uid, element_type, style_type, x, y, width, height, shape_id in elements:
            conn.execute(
                """
                INSERT INTO element (
                  rowid, slide_id, element_uid, element_type, element_style_type, order_index, x, y, width, height,
                  background_resource_id, foreground_resource_id, shape_resource_id, internal_mute, from_master
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, 0, 0)
                """,
                (next_blank_element_id, slide_rowid, element_uid, element_type, style_type, element_order, x, y, width, height, shape_id),
            )
            next_blank_element_id += 1
            element_order += 1


def convert_easyworship_to_freeshow(ewsx_path: str | Path, output_project_path: str | Path, also_json: str | Path | None = None) -> dict[str, Any]:
    source_path = Path(ewsx_path)
    output_path = Path(output_project_path)
    items = extract_easyworship_items(source_path)
    text_shows, text_background_members = extract_easyworship_text_shows(source_path)
    members = {member.name: member for member in _scan_bundle_members(source_path)}
    manifest = _empty_easyworship_project_manifest(source_path.stem)
    for item in items:
        _append_media_reference(manifest, item)
    for show in text_shows:
        _append_text_show_reference(
            manifest,
            show_id=show["show_id"],
            show_name=show["show_name"],
            schedule_index=int(show["schedule_index"]),
            slide_payloads=show["slides"],
            bundled_backgrounds=show["backgrounds"],
        )
    _sort_project_schedule(manifest)

    temp_root = Path.cwd() / ".easyworship_to_freeshow_build"
    tmp = temp_root / sanitize_filename(output_path.stem)
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        for item in items:
            target_path = tmp / item.packaged_name
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(_read_bundle_member(source_path, members[item.bundled_member]))
        for import_path, bundled_member in text_background_members.items():
            target_path = tmp / Path(import_path).name
            if target_path.exists():
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(_read_bundle_member(source_path, members[bundled_member]))

        data_json = tmp / "data.json"
        data_json.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in items:
                file_path = tmp / item.packaged_name
                if file_path.is_file():
                    zout.write(file_path, arcname=item.packaged_name)
            for import_path in text_background_members:
                file_path = tmp / Path(import_path).name
                if file_path.is_file():
                    zout.write(file_path, arcname=Path(import_path).name)
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


def convert_freeshow_to_easyworship(project_path: str | Path, output_ewsx_path: str | Path, also_json: str | Path | None = None) -> dict[str, Any]:
    source_path = Path(project_path)
    output_path = Path(output_ewsx_path)
    items = extract_project_media_items(source_path)
    text_shows = extract_project_text_shows(source_path)
    unsupported = sorted({item.kind for item in items if item.kind not in {"image", "video"}})
    if unsupported:
        formatted = ", ".join(unsupported)
        raise ValueError(f"EasyWorship export currently supports image and video items only. Unsupported item types: {formatted}.")
    if not items and not text_shows:
        raise ValueError("FreeShow project does not contain any image, video, or song items to export to EasyWorship.")
    if not items and text_shows:
        raise ValueError("EasyWorship export currently needs at least one image or video item when exporting FreeShow songs.")

    media_bytes: dict[str, bytes] = {}
    with zipfile.ZipFile(source_path) as zin:
        for item in items:
            media_bytes[item.bundled_member] = zin.read(item.bundled_member)
        for show in text_shows:
            for bundled_background in show["backgrounds"].values():
                bundled_member = str(bundled_background["bundled_member"])
                if bundled_member not in media_bytes:
                    media_bytes[bundled_member] = zin.read(bundled_member)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path.cwd() / ".freeshow_to_easyworship_build"
    tmp_root = _reset_workspace_dir(temp_root / f"{sanitize_filename(output_path.stem)}_{uuid.uuid4().hex}")
    try:
        used_kinds = {item.kind for item in items}
        for show in text_shows:
            for bundled_background in show["backgrounds"].values():
                used_kinds.add(str(bundled_background["kind"]))
        template_bundles = {kind: _load_easyworship_template_bundle(kind) for kind in used_kinds}
        base_bundle = template_bundles[items[0].kind]
        db_path = tmp_root / "main.db"
        manifest = _build_easyworship_template_database(db_path, template_bundles, items, media_bytes)
        used_media_names = {Path(str(item_manifest["member_name"])).name.lower() for item_manifest in manifest["items"]}
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            song_manifest = _append_song_presentations(conn, text_shows, media_bytes, used_media_names)
            all_schedule_entries = [*manifest["items"], *song_manifest["songs"]]
            if len(all_schedule_entries) > 1:
                _apply_schedule_order_indices(
                    conn,
                    all_schedule_entries,
                    global_presentation_id=manifest.get("global_presentation_id"),
                )
            conn.commit()
        manifest["songs"] = song_manifest["songs"]
        manifest["song_count"] = len(song_manifest["songs"])
        manifest["item_count"] = len(manifest["items"]) + len(song_manifest["songs"])
        db_bytes = db_path.read_bytes()
        bundle_members: list[dict[str, Any]] = []
        first_item_member_name = str(manifest["items"][0]["member_name"])
        base_template_media_member = _template_media_member(base_bundle["members"])
        base_template_media_name = str(base_template_media_member["name"]).replace("/", "\\").lower()
        for template_member in base_bundle["members"]:
            bundle_member = dict(template_member)
            normalized_name = str(bundle_member.get("name", "")).replace("/", "\\").lower()
            if normalized_name == "main.db":
                bundle_member["content"] = db_bytes
            elif normalized_name == base_template_media_name:
                bundle_member["name"] = first_item_member_name
                bundle_member["content"] = media_bytes[items[0].bundled_member]
            else:
                bundle_member["content"] = bytes(bundle_member.get("content", b""))
            bundle_members.append(bundle_member)
        for item, item_manifest in zip(items[1:], manifest["items"][1:]):
            media_template_member = dict(_template_media_member(template_bundles[item.kind]["members"]))
            media_template_member["name"] = str(item_manifest["member_name"])
            media_template_member["content"] = media_bytes[item.bundled_member]
            bundle_members.append(media_template_member)
        for bundled_background in song_manifest["bundle_members"]:
            media_template_member = dict(_template_media_member(template_bundles[str(bundled_background["kind"])]["members"]))
            media_template_member["name"] = str(bundled_background["name"])
            media_template_member["content"] = bytes(bundled_background["content"])
            bundle_members.append(media_template_member)
        _write_easyworship_bundle(output_path, bundle_members)
    finally:
        if tmp_root.exists():
            shutil.rmtree(tmp_root, ignore_errors=True)
        if temp_root.exists() and not any(temp_root.iterdir()):
            temp_root.rmdir()

    if also_json is not None:
        debug_path = Path(also_json)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def convert_easyworship_request(request: ConversionRequest) -> ConversionResult:
    manifest = convert_easyworship_to_freeshow(request.input_path, request.output_path, request.debug_manifest_path)
    item_count = len(manifest.get("project", {}).get("shows", []))
    return ConversionResult(output_path=request.output_path, item_count=item_count, details=manifest)


def convert_freeshow_to_easyworship_request(request: ConversionRequest) -> ConversionResult:
    manifest = convert_freeshow_to_easyworship(request.input_path, request.output_path, request.debug_manifest_path)
    item_count = int(manifest.get("item_count", 0))
    return ConversionResult(output_path=request.output_path, item_count=item_count, details=manifest)

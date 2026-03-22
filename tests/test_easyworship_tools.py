from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from projection_software_converter.conversion.easyworship_freeshow import convert_easyworship_to_freeshow, convert_freeshow_to_easyworship
from projection_software_converter.conversion.easyworship_inspector import diff_ewsx, extract_ewsx_members, inspect_ewsx
from projection_software_converter.conversion.videosalm_freeshow import (
    AgendaItem,
    _project_manifest,
    convert_freeshow_to_videosalm,
    relaxed_json_to_python,
)


SAMPLE_EWSX = Path.home() / "Downloads" / "single_video_valid.ewsx"
SAMPLE_IMAGE_EWSX = Path.home() / "Downloads" / "Telegram Desktop" / "Camp prayer 2025 Feb.ewsx"
SAMPLE_ORDERED_EWSX = Path.home() / "Downloads" / "01.19.2025.ewsx"
TMP_ROOT = Path("out") / "test_easyworship_tools"


def _sample_media_metadata(sample_path: Path, media_table: str) -> dict[str, object]:
    members = extract_ewsx_members(sample_path)["members"]
    media_member = next(member for member in members if member["name"].lower().startswith("media\\"))
    main_db = next(member["content"] for member in members if member["name"] == "main.db")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        tmp.write(main_db)
        db_path = Path(tmp.name)
    try:
        conn = sqlite3.connect(db_path)
        presentation_type = 1 if media_table == "resource_video" else 2
        title = conn.execute(
            "SELECT title FROM presentation WHERE presentation_type = ? ORDER BY rowid LIMIT 1",
            (presentation_type,),
        ).fetchone()[0]
        original_filename = conn.execute(f"SELECT original_filename FROM {media_table} ORDER BY rowid LIMIT 1").fetchone()[0]
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)
    original_path = str(original_filename).removeprefix("<videos>") if media_table == "resource_video" else str(original_filename)
    return {
        "title": str(title),
        "original_path": original_path,
        "member_name": Path(str(media_member["name"])).name,
        "media_content": bytes(media_member["content"]),
    }


def _write_project(project_path: Path, project_name: str, items_with_payloads: list[tuple[AgendaItem, bytes]], *, use_original_ids: bool = False) -> None:
    if use_original_ids:
        shows: list[dict[str, object]] = []
        files: list[str] = []
        media: dict[str, object] = {}
        for item, _ in items_with_payloads:
            shows.append(
                {
                    "name": item.title,
                    "id": item.original_path,
                    "type": item.kind,
                    "index": item.index,
                }
            )
            files.append(item.original_path)
            if item.kind in {"video", "audio"}:
                media[item.original_path] = {"tracks": []}
        manifest = {
            "project": {
                "name": project_name,
                "created": 0,
                "parent": "/",
                "shows": shows,
                "modified": 0,
                "used": 0,
                "id": project_name,
            },
            "parentFolder": "",
            "shows": {},
            "files": files,
        }
        if media:
            manifest["media"] = media
    else:
        manifest = _project_manifest(project_name, [item for item, _ in items_with_payloads])
    with zipfile.ZipFile(project_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        zout.writestr("data.json", json.dumps(manifest))
        for item, payload in items_with_payloads:
            zout.writestr(item.bundled_member, payload)


def _sqlite_summary(path: Path) -> tuple[dict[int, int], list[tuple[int, str, int]]]:
    members = extract_ewsx_members(path)["members"]
    main_db = next(member["content"] for member in members if member["name"] == "main.db")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        tmp.write(main_db)
        db_path = Path(tmp.name)
    try:
        conn = sqlite3.connect(db_path)
        presentation_types = {
            int(kind): int(count)
            for kind, count in conn.execute(
                "SELECT presentation_type, COUNT(*) FROM presentation GROUP BY presentation_type ORDER BY presentation_type"
            )
        }
        ordered_titles = [
            (int(rowid), str(title), int(order_index))
            for rowid, title, order_index in conn.execute(
                "SELECT rowid, title, order_index FROM presentation WHERE presentation_type IN (1, 2) ORDER BY order_index, rowid"
            )
        ]
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)
    return presentation_types, ordered_titles


def _read_main_db(path: Path) -> Path:
    members = extract_ewsx_members(path)["members"]
    main_db = next(member["content"] for member in members if member["name"] == "main.db")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        tmp.write(main_db)
        return Path(tmp.name)


def _manifest_schedule_names(manifest: dict[str, object]) -> list[str]:
    project = manifest.get("project", {})
    project_shows = project.get("shows", []) if isinstance(project, dict) else []
    named_shows = manifest.get("shows", {}) if isinstance(manifest.get("shows", {}), dict) else {}
    names: list[str] = []
    for entry in project_shows:
        if not isinstance(entry, dict):
            continue
        if "type" in entry:
            names.append(str(entry.get("name") or ""))
        else:
            show_id = str(entry.get("id") or "")
            show = named_shows.get(show_id, {})
            names.append(str(show.get("name") or ""))
    return names


def _write_project_with_song(
    project_path: Path,
    project_name: str,
    media_item: AgendaItem,
    media_payload: bytes,
    *,
    media_title: str,
    song_title: str,
    song_lines: list[str],
    background_kind: str = "video",
) -> None:
    manifest = _project_manifest(project_name, [media_item])
    import_path = manifest["project"]["shows"][0]["id"]
    show_id = "song-show-1"
    layout_id = "song-layout-1"
    background_id = "song-bg-1"
    slide_entries = []
    slides = {}
    for index, line in enumerate(song_lines):
        slide_id = f"song-slide-{index + 1}"
        slides[slide_id] = {
            "group": line,
            "color": None,
            "settings": {},
            "notes": "",
            "items": [
                {
                    "style": "top:120px;left:50px;height:840px;width:1820px;",
                    "lines": [{"align": "text-align: center", "text": [{"style": "", "value": line}]}],
                    "align": "",
                    "auto": True,
                    "textFit": "shrinkToFit",
                    "specialStyle": {"lineBg": ""},
                    "scrolling": {"type": "none"},
                    "autoFontSize": 100,
                }
            ],
            "globalGroup": "verse",
        }
        slide_entries.append({"id": slide_id, "background": background_id})

    manifest["project"]["shows"][0]["name"] = media_title
    manifest["project"]["shows"].append({"id": show_id, "index": 1})
    manifest["shows"][show_id] = {
        "name": song_title,
        "private": False,
        "category": "songs",
        "settings": {"activeLayout": layout_id, "template": "default"},
        "timestamps": {"created": 0, "modified": None, "used": None},
        "quickAccess": {},
        "meta": {"title": song_title},
        "slides": slides,
        "layouts": {layout_id: {"name": "Default", "notes": "", "slides": slide_entries}},
        "media": {background_id: {"name": Path(import_path).stem, "path": import_path, "type": background_kind}},
    }

    with zipfile.ZipFile(project_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        zout.writestr("data.json", json.dumps(manifest))
        zout.writestr(media_item.bundled_member, media_payload)


@unittest.skipUnless(SAMPLE_EWSX.exists(), f"Missing EasyWorship sample at {SAMPLE_EWSX}")
class EasyWorshipInspectorTests(unittest.TestCase):
    def test_inspect_valid_sample(self) -> None:
        report = inspect_ewsx(SAMPLE_EWSX)
        self.assertEqual(report["container_mode"], "local-header")
        self.assertEqual(report["member_count"], 3)
        self.assertEqual(report["sqlite"]["page_size"], 1024)
        self.assertEqual(report["sqlite"]["info_rows"][0]["version"], "7.4.1.3")

    def test_diff_same_file_has_no_schema_drift(self) -> None:
        diff = diff_ewsx(SAMPLE_EWSX, SAMPLE_EWSX)
        self.assertEqual(diff["sqlite"]["missing_tables"], [])
        self.assertEqual(diff["sqlite"]["extra_tables"], [])
        self.assertEqual(diff["sqlite"]["table_diffs"], {})

    def test_generate_one_video_export_matches_minimal_types(self) -> None:
        sample = _sample_media_metadata(SAMPLE_EWSX, "resource_video")
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        project_path = TMP_ROOT / "one_video.project"
        output_path = TMP_ROOT / "generated.ewsx"
        item = AgendaItem(
            index=0,
            kind="video",
            source_manifest="data.json",
            title=str(sample["title"]),
            original_path=rf"C:\Videos\{Path(str(sample['original_path'])).name}",
            bundled_member=str(sample["member_name"]),
            packaged_name=str(sample["member_name"]),
        )
        _write_project(project_path, "one-video", [(item, bytes(sample["media_content"]))], use_original_ids=True)

        convert_freeshow_to_easyworship(project_path, output_path)
        report = inspect_ewsx(output_path)
        presentation_rows = report["sqlite"]["table_info"]["presentation"]["row_count"]
        self.assertEqual(report["member_count"], 3)
        self.assertEqual(report["sqlite"]["page_size"], 1024)
        self.assertEqual(presentation_rows, 2)
        self.assertTrue(report["zipfile_readability"]["ok"])
        self.assertEqual(report["zipfile_readability"]["names"], ["main.db", "media", "media/cevsp.mp4"])
        presentations = diff_ewsx(SAMPLE_EWSX, output_path)
        self.assertEqual(presentations["container"]["member_metadata_differences"], [])
        self.assertEqual(presentations["container"]["valid_members"], presentations["container"]["generated_members"])
        self.assertTrue(presentations["container"]["generated_zipfile_readable"]["ok"])
        self.assertEqual(presentations["sqlite"]["missing_tables"], [])
        self.assertEqual(presentations["sqlite"]["extra_tables"], [])
        self.assertEqual(presentations["sqlite"]["table_diffs"], {})
        self.assertEqual(presentations["sqlite"]["row_differences"], {})

    @unittest.skipUnless(SAMPLE_IMAGE_EWSX.exists(), f"Missing EasyWorship image sample at {SAMPLE_IMAGE_EWSX}")
    def test_generate_one_image_export_matches_minimal_types(self) -> None:
        sample = _sample_media_metadata(SAMPLE_IMAGE_EWSX, "resource_image")
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        project_path = TMP_ROOT / "one_image.project"
        output_path = TMP_ROOT / "generated_image.ewsx"
        item = AgendaItem(
            index=0,
            kind="image",
            source_manifest="data.json",
            title=str(sample["title"]),
            original_path=str(sample["original_path"]),
            bundled_member=str(sample["member_name"]),
            packaged_name=str(sample["member_name"]),
        )
        _write_project(project_path, "one-image", [(item, bytes(sample["media_content"]))], use_original_ids=True)

        convert_freeshow_to_easyworship(project_path, output_path)
        report = inspect_ewsx(output_path)
        self.assertEqual(report["member_count"], 3)
        self.assertEqual(report["sqlite"]["page_size"], 1024)
        self.assertTrue(report["zipfile_readability"]["ok"])
        self.assertEqual(report["zipfile_readability"]["names"], ["main.db", "media", "media/2bb1bl.png"])
        diff = diff_ewsx(SAMPLE_IMAGE_EWSX, output_path)
        self.assertEqual(diff["container"]["member_metadata_differences"], [])
        self.assertEqual(diff["container"]["valid_members"], diff["container"]["generated_members"])
        self.assertEqual(diff["sqlite"]["missing_tables"], [])
        self.assertEqual(diff["sqlite"]["extra_tables"], [])
        self.assertEqual(diff["sqlite"]["table_diffs"], {})
        self.assertEqual(diff["sqlite"]["row_differences"], {})

    @unittest.skipUnless(SAMPLE_IMAGE_EWSX.exists(), f"Missing EasyWorship image sample at {SAMPLE_IMAGE_EWSX}")
    def test_generate_mixed_export_with_video_base_has_expected_structure(self) -> None:
        video_sample = _sample_media_metadata(SAMPLE_EWSX, "resource_video")
        image_sample = _sample_media_metadata(SAMPLE_IMAGE_EWSX, "resource_image")
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        project_path = TMP_ROOT / "mixed_video_base.project"
        output_path = TMP_ROOT / "mixed_video_base.ewsx"
        items_with_payloads = [
            (
                AgendaItem(
                    index=0,
                    kind="video",
                    source_manifest="data.json",
                    title=str(video_sample["title"]),
                    original_path=rf"C:\Videos\{Path(str(video_sample['original_path'])).name}",
                    bundled_member=str(video_sample["member_name"]),
                    packaged_name=str(video_sample["member_name"]),
                ),
                bytes(video_sample["media_content"]),
            ),
            (
                AgendaItem(
                    index=1,
                    kind="image",
                    source_manifest="data.json",
                    title="Camp Prayer Image",
                    original_path=str(image_sample["original_path"]),
                    bundled_member=str(image_sample["member_name"]),
                    packaged_name=str(image_sample["member_name"]),
                ),
                bytes(image_sample["media_content"]),
            ),
        ]
        _write_project(project_path, "mixed-video-base", items_with_payloads)

        convert_freeshow_to_easyworship(project_path, output_path)
        report = inspect_ewsx(output_path)
        self.assertEqual(report["member_count"], 4)
        self.assertTrue(report["zipfile_readability"]["ok"])
        self.assertEqual(report["sqlite"]["table_info"]["presentation"]["row_count"], 3)
        self.assertEqual(report["sqlite"]["table_info"]["file"]["row_count"], 2)
        self.assertEqual(report["sqlite"]["table_info"]["resource_video"]["row_count"], 1)
        self.assertEqual(report["sqlite"]["table_info"]["resource_image"]["row_count"], 1)
        presentation_types, ordered_titles = _sqlite_summary(output_path)
        self.assertEqual(presentation_types, {1: 1, 2: 1, 11: 1})
        self.assertEqual([title for _, title, _ in ordered_titles], [str(video_sample["title"]), "Camp Prayer Image"])

    @unittest.skipUnless(SAMPLE_IMAGE_EWSX.exists(), f"Missing EasyWorship image sample at {SAMPLE_IMAGE_EWSX}")
    def test_generate_mixed_export_with_image_base_has_expected_structure(self) -> None:
        video_sample = _sample_media_metadata(SAMPLE_EWSX, "resource_video")
        image_sample = _sample_media_metadata(SAMPLE_IMAGE_EWSX, "resource_image")
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        project_path = TMP_ROOT / "mixed_image_base.project"
        output_path = TMP_ROOT / "mixed_image_base.ewsx"
        items_with_payloads = [
            (
                AgendaItem(
                    index=0,
                    kind="image",
                    source_manifest="data.json",
                    title="Camp Prayer Image",
                    original_path=str(image_sample["original_path"]),
                    bundled_member=str(image_sample["member_name"]),
                    packaged_name=str(image_sample["member_name"]),
                ),
                bytes(image_sample["media_content"]),
            ),
            (
                AgendaItem(
                    index=1,
                    kind="video",
                    source_manifest="data.json",
                    title=str(video_sample["title"]),
                    original_path=rf"C:\Videos\{Path(str(video_sample['original_path'])).name}",
                    bundled_member=str(video_sample["member_name"]),
                    packaged_name=str(video_sample["member_name"]),
                ),
                bytes(video_sample["media_content"]),
            ),
        ]
        _write_project(project_path, "mixed-image-base", items_with_payloads)

        convert_freeshow_to_easyworship(project_path, output_path)
        report = inspect_ewsx(output_path)
        self.assertEqual(report["member_count"], 4)
        self.assertTrue(report["zipfile_readability"]["ok"])
        self.assertEqual(report["sqlite"]["table_info"]["presentation"]["row_count"], 3)
        self.assertEqual(report["sqlite"]["table_info"]["file"]["row_count"], 2)
        self.assertEqual(report["sqlite"]["table_info"]["resource_video"]["row_count"], 1)
        self.assertEqual(report["sqlite"]["table_info"]["resource_image"]["row_count"], 1)
        presentation_types, ordered_titles = _sqlite_summary(output_path)
        self.assertEqual(presentation_types, {1: 1, 2: 1, 11: 1})
        self.assertEqual([title for _, title, _ in ordered_titles], ["Camp Prayer Image", str(video_sample["title"])])

    def test_generate_export_with_song_keeps_song_and_clears_stale_thumbnails(self) -> None:
        video_sample = _sample_media_metadata(SAMPLE_EWSX, "resource_video")
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        project_path = TMP_ROOT / "with_song.project"
        output_path = TMP_ROOT / "with_song.ewsx"
        media_item = AgendaItem(
            index=0,
            kind="video",
            source_manifest="data.json",
            title="Prayer Splash",
            original_path=rf"C:\Videos\{Path(str(video_sample['original_path'])).name}",
            bundled_member=str(video_sample["member_name"]),
            packaged_name=str(video_sample["member_name"]),
        )
        _write_project_with_song(
            project_path,
            "with-song",
            media_item,
            bytes(video_sample["media_content"]),
            media_title="Prayer Splash",
            song_title="Firm Foundation",
            song_lines=["Christ is my firm foundation", "The rock on which I stand"],
        )

        convert_freeshow_to_easyworship(project_path, output_path)
        db_path = _read_main_db(output_path)
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            presentations = conn.execute(
                "SELECT title, presentation_type, order_index, length(thumbnail) AS thumb_len FROM presentation ORDER BY order_index, rowid"
            ).fetchall()
            self.assertEqual(
                [(row["title"], row["presentation_type"]) for row in presentations],
                [("Prayer Splash", 1), ("Firm Foundation", 6), ("Global", 11)],
            )
            self.assertIsNone(presentations[0]["thumb_len"])
            self.assertIsNone(presentations[1]["thumb_len"])

            song_rtf = conn.execute(
                """
                SELECT rt.rtf
                FROM presentation p
                JOIN slide s ON s.presentation_id = p.rowid
                JOIN element e ON e.slide_id = s.rowid AND e.element_uid = 'CONTENT_SONG'
                JOIN resource_text rt ON rt.resource_id = e.foreground_resource_id
                WHERE p.presentation_type = 6
                ORDER BY s.order_index
                LIMIT 1
                """
            ).fetchone()[0]
            self.assertIn("Christ is my firm foundation", song_rtf)

            song_background = conn.execute(
                """
                SELECT e.foreground_resource_id
                FROM presentation p
                JOIN slide s ON s.presentation_id = p.rowid
                JOIN element e ON e.slide_id = s.rowid AND e.element_uid = 'BACKGROUND'
                WHERE p.presentation_type = 6
                ORDER BY s.order_index
                LIMIT 1
                """
            ).fetchone()[0]
            self.assertIsNotNone(song_background)
        finally:
            conn.close()
            db_path.unlink(missing_ok=True)

    @unittest.skipUnless(SAMPLE_ORDERED_EWSX.exists(), f"Missing EasyWorship mixed sample at {SAMPLE_ORDERED_EWSX}")
    def test_easyworship_to_freeshow_preserves_agenda_order(self) -> None:
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        output_path = TMP_ROOT / "ordered_from_easyworship.project"
        manifest = convert_easyworship_to_freeshow(SAMPLE_ORDERED_EWSX, output_path)

        db_path = _read_main_db(SAMPLE_ORDERED_EWSX)
        try:
            conn = sqlite3.connect(db_path)
            expected_names = [
                str(title)
                for title, _presentation_type in conn.execute(
                    """
                    SELECT title, presentation_type
                    FROM presentation
                    WHERE presentation_type IN (1, 2, 6)
                    ORDER BY order_index, rowid
                    """
                )
            ]
        finally:
            conn.close()
            db_path.unlink(missing_ok=True)

        self.assertEqual(_manifest_schedule_names(manifest), expected_names)

    def test_generate_videosalm_export_with_song_video_background(self) -> None:
        video_sample = _sample_media_metadata(SAMPLE_EWSX, "resource_video")
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        project_path = TMP_ROOT / "videosalm_song_video_bg.project"
        output_path = TMP_ROOT / "videosalm_song_video_bg.vpagd"
        media_item = AgendaItem(
            index=0,
            kind="video",
            source_manifest="data.json",
            title="Prayer Splash",
            original_path=rf"C:\Videos\{Path(str(video_sample['original_path'])).name}",
            bundled_member=str(video_sample["member_name"]),
            packaged_name=str(video_sample["member_name"]),
        )
        _write_project_with_song(
            project_path,
            "videosalm-song-video-bg",
            media_item,
            bytes(video_sample["media_content"]),
            media_title="Prayer Splash",
            song_title="Firm Foundation",
            song_lines=["Christ is my firm foundation", "The rock on which I stand"],
            background_kind="video",
        )

        manifest = convert_freeshow_to_videosalm(project_path, output_path)
        self.assertEqual(manifest["item_count"], 2)
        self.assertEqual(manifest["song_item_count"], 1)
        with zipfile.ZipFile(output_path) as zf:
            names = zf.namelist()
            self.assertIn("Song_0.json", names)
            self.assertIn("SongBook_0.json", names)
            song_payload = relaxed_json_to_python(zf.read("Song_0.json").decode("utf-8", "ignore"))
            self.assertEqual(song_payload["Text"], "Firm Foundation")
            self.assertEqual([verse["Text"] for verse in song_payload["Verses"]], ["Christ is my firm foundation", "The rock on which I stand"])
            background_name = song_payload["Style"]["Background"]["Video"]
            self.assertIn(f"Videos/{background_name}", names)
            agenda_payload = relaxed_json_to_python(zf.read("AgendaItemProperties.json").decode("utf-8", "ignore"))
            self.assertEqual(len(agenda_payload["Items"]), 2)
            self.assertEqual(agenda_payload["Items"][1]["HiddenSlides"], [])

    @unittest.skipUnless(SAMPLE_IMAGE_EWSX.exists(), f"Missing EasyWorship image sample at {SAMPLE_IMAGE_EWSX}")
    def test_generate_videosalm_export_with_song_image_background(self) -> None:
        image_sample = _sample_media_metadata(SAMPLE_IMAGE_EWSX, "resource_image")
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        project_path = TMP_ROOT / "videosalm_song_image_bg.project"
        output_path = TMP_ROOT / "videosalm_song_image_bg.vpagd"
        media_item = AgendaItem(
            index=0,
            kind="image",
            source_manifest="data.json",
            title="Prayer Card",
            original_path=str(image_sample["original_path"]),
            bundled_member=str(image_sample["member_name"]),
            packaged_name=str(image_sample["member_name"]),
        )
        _write_project_with_song(
            project_path,
            "videosalm-song-image-bg",
            media_item,
            bytes(image_sample["media_content"]),
            media_title="Prayer Card",
            song_title="Healing Jesus",
            song_lines=["There is healing in Your name"],
            background_kind="image",
        )

        manifest = convert_freeshow_to_videosalm(project_path, output_path)
        self.assertEqual(manifest["item_count"], 2)
        self.assertEqual(manifest["song_item_count"], 1)
        with zipfile.ZipFile(output_path) as zf:
            names = zf.namelist()
            song_payload = relaxed_json_to_python(zf.read("Song_0.json").decode("utf-8", "ignore"))
            self.assertEqual(song_payload["Text"], "Healing Jesus")
            background_name = song_payload["Style"]["Background"]["Image"]
            self.assertIn(f"Images/{background_name}", names)


if __name__ == "__main__":
    unittest.main()

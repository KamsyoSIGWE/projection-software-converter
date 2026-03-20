from __future__ import annotations

import argparse
import json
from pathlib import Path

from projection_software_converter.conversion.videosalm_freeshow import (
    convert_freeshow_to_videosalm,
    convert_videosalm_to_freeshow,
    extract_agenda_items,
    extract_project_media_items,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert VideoPsalm .vpagd agenda packages and FreeShow .project files")
    parser.add_argument("input", help="Path to the .vpagd or .project file")
    parser.add_argument("-o", "--output", help="Path to output .project or .vpagd file")
    parser.add_argument("--also-json", help="Optional path to write a generated debug JSON manifest")
    parser.add_argument("--inspect", action="store_true", help="Only inspect the input contents and print them as JSON")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    input_path = Path(args.input)
    suffix = input_path.suffix.lower()

    if suffix not in {".vpagd", ".project"}:
        raise SystemExit(f"Unsupported input type: {input_path.suffix}. Expected .vpagd or .project")

    if args.inspect:
        items = extract_agenda_items(input_path) if suffix == ".vpagd" else extract_project_media_items(input_path)
        print(json.dumps([item.__dict__ for item in items], indent=2, ensure_ascii=False))
        return 0

    output = Path(args.output) if args.output else input_path.with_suffix(".project" if suffix == ".vpagd" else ".vpagd")
    manifest = (
        convert_videosalm_to_freeshow(input_path, output, also_json=args.also_json)
        if suffix == ".vpagd"
        else convert_freeshow_to_videosalm(input_path, output, also_json=args.also_json)
    )
    print(f"Wrote {output}")
    item_count = len(manifest.get("project", {}).get("shows", [])) if suffix == ".vpagd" else int(manifest.get("item_count", 0))
    print(f"Items converted: {item_count}")
    return 0

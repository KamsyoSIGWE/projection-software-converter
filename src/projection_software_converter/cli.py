from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import DEFAULT_CONFIG
from .conversion.base import ConversionRequest
from .conversion.bootstrap import build_registry
from .conversion.service import ConverterService, default_output_path
from .updater import GitHubReleaseUpdater, UpdateError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="projection-software-converter", description=DEFAULT_CONFIG.app_name)
    subparsers = parser.add_subparsers(dest="command")

    convert_parser = subparsers.add_parser("convert", help="Convert a supported file without opening the GUI")
    convert_parser.add_argument("--input", required=True, help="Source file path")
    convert_parser.add_argument("--from", dest="source", required=True, help="Source format name")
    convert_parser.add_argument("--to", dest="target", required=True, help="Target format name")
    convert_parser.add_argument("--output", help="Output file path")
    convert_parser.add_argument("--also-json", help="Optional path for a debug JSON manifest")

    subparsers.add_parser("list-conversions", help="List registered formats and conversion directions")
    subparsers.add_parser("check-updates", help="Check GitHub Releases for an update")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    registry = build_registry()
    service = ConverterService(registry)

    if args.command is None:
        from .app import run_gui

        return run_gui(registry, service)
    if args.command == "convert":
        input_path = Path(args.input)
        output_path = Path(args.output) if args.output else default_output_path(input_path, args.target)
        result = service.convert(
            ConversionRequest(
                input_path=input_path,
                output_path=output_path,
                source=args.source,
                target=args.target,
                debug_manifest_path=Path(args.also_json) if args.also_json else None,
            )
        )
        print(f"Wrote {result.output_path}")
        print(f"Items converted: {result.item_count}")
        return 0
    if args.command == "list-conversions":
        payload = {
            "formats": registry.query_supported_formats(),
            "conversions": [{"from": pair.source, "to": pair.target, "handler": pair.handler_name} for pair in registry.query_conversion_pairs()],
        }
        print(json.dumps(payload, indent=2))
        return 0
    if args.command == "check-updates":
        updater = GitHubReleaseUpdater(DEFAULT_CONFIG.github_updates)
        try:
            release = updater.check_for_updates()
        except UpdateError as exc:
            print(f"Update check failed: {exc}")
            return 1
        if release is None:
            print("No published updates are available.")
            return 0
        print(f"Update available: {release.version}")
        print(release.notes or "No release notes provided.")
        return 0
    parser.print_help()
    return 1

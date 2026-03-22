from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import GitHubUpdateConfig
from .version import __version__

LOGGER = logging.getLogger(__name__)


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    notes: str
    package: ReleaseAsset
    checksum: ReleaseAsset | None
    html_url: str


def normalize_version(value: str) -> tuple[int, ...]:
    clean = value.strip().lstrip("vV")
    pieces = re.split(r"[.+-]", clean)
    version_parts: list[int] = []
    for part in pieces:
        if part.isdigit():
            version_parts.append(int(part))
        else:
            break
    return tuple(version_parts or [0])


class GitHubReleaseUpdater:
    def __init__(self, config: GitHubUpdateConfig) -> None:
        self._config = config

    def check_for_updates(self, current_version: str = __version__) -> ReleaseInfo | None:
        if "REPLACE_WITH_GITHUB_" in self._config.owner or "REPLACE_WITH_GITHUB_" in self._config.repo:
            LOGGER.info("GitHub updater is not configured yet.")
            return None

        releases = self._fetch_releases()
        latest = self._select_latest_release(releases)
        if latest is None:
            return None
        if normalize_version(latest.version) <= normalize_version(current_version):
            return None
        return latest

    def download_release_package(self, release: ReleaseInfo) -> Path:
        target_dir = Path(tempfile.mkdtemp(prefix="projection-software-converter-update-"))
        package_path = target_dir / release.package.name
        self._download_file(release.package.download_url, package_path)
        if release.checksum is not None:
            checksum_path = target_dir / release.checksum.name
            self._download_file(release.checksum.download_url, checksum_path)
            self._verify_checksum(package_path, checksum_path)
        return package_path

    def launch_release_package(self, package_path: Path) -> None:
        if not package_path.exists():
            raise UpdateError(f"Release package not found: {package_path}")
        if os.name == "nt":
            os.startfile(package_path)  # type: ignore[attr-defined]
            return
        subprocess.Popen([str(package_path)])

    def _fetch_releases(self) -> list[dict]:
        url = f"{self._config.api_base_url}/repos/{self._config.owner}/{self._config.repo}/releases"
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "ProjectionSoftwareConverter"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise UpdateError(f"Could not reach GitHub Releases: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise UpdateError("Received invalid JSON from GitHub Releases.") from exc

    def _select_latest_release(self, releases: list[dict]) -> ReleaseInfo | None:
        release_patterns, checksum_patterns = self._compiled_asset_patterns()
        candidates: list[ReleaseInfo] = []
        for release in releases:
            if release.get("draft"):
                continue
            if release.get("prerelease") and not self._config.include_prereleases:
                continue

            package_asset: ReleaseAsset | None = None
            checksum_asset: ReleaseAsset | None = None
            for asset in release.get("assets", []):
                name = str(asset.get("name", ""))
                download_url = str(asset.get("browser_download_url", ""))
                if self._matches_any_pattern(name, release_patterns):
                    package_asset = ReleaseAsset(name=name, download_url=download_url)
                elif self._matches_any_pattern(name, checksum_patterns):
                    checksum_asset = ReleaseAsset(name=name, download_url=download_url)
            if package_asset is None:
                continue

            candidates.append(
                ReleaseInfo(
                    version=str(release.get("tag_name") or release.get("name") or ""),
                    notes=str(release.get("body") or "").strip(),
                    package=package_asset,
                    checksum=checksum_asset,
                    html_url=str(release.get("html_url") or ""),
                )
            )

        if not candidates:
            return None
        return max(candidates, key=lambda item: normalize_version(item.version))

    @staticmethod
    def _download_file(url: str, destination: Path) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": "ProjectionSoftwareConverter"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response, open(destination, "wb") as handle:
                handle.write(response.read())
        except urllib.error.URLError as exc:
            raise UpdateError(f"Download failed: {exc}") from exc

    @staticmethod
    def _verify_checksum(package_path: Path, checksum_path: Path) -> None:
        expected_line = checksum_path.read_text(encoding="utf-8").strip().splitlines()[0]
        expected = expected_line.split()[0].lower()
        digest = hashlib.sha256(package_path.read_bytes()).hexdigest().lower()
        if expected != digest:
            raise UpdateError("Downloaded release package checksum verification failed.")

    def _compiled_asset_patterns(self) -> tuple[list[re.Pattern[str]], list[re.Pattern[str]]]:
        platform_name = self._current_platform_name()
        if platform_name == "macos":
            release_patterns = self._config.macos_release_asset_patterns
            checksum_patterns = self._config.macos_checksum_asset_patterns
        elif platform_name == "linux":
            release_patterns = self._config.linux_release_asset_patterns
            checksum_patterns = self._config.linux_checksum_asset_patterns
        else:
            release_patterns = self._config.windows_release_asset_patterns
            checksum_patterns = self._config.windows_checksum_asset_patterns
        return [re.compile(pattern) for pattern in release_patterns], [re.compile(pattern) for pattern in checksum_patterns]

    def _current_platform_name(self) -> str:
        override = (self._config.platform_override or "").strip().lower()
        if override in {"windows", "macos", "linux"}:
            return override
        if sys.platform == "darwin":
            return "macos"
        if sys.platform.startswith("linux"):
            return "linux"
        return "windows"

    @staticmethod
    def _matches_any_pattern(name: str, patterns: list[re.Pattern[str]]) -> bool:
        return any(pattern.fullmatch(name) for pattern in patterns)

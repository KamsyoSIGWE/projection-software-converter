from __future__ import annotations

import os
from dataclasses import dataclass

from .version import __version__

APP_NAME = "Projection Software Converter"


@dataclass(frozen=True)
class GitHubUpdateConfig:
    owner: str
    repo: str
    windows_release_asset_patterns: tuple[str, ...] = (r"ProjectionSoftwareConverter-(?P<version>.+)-Setup\.exe",)
    windows_checksum_asset_patterns: tuple[str, ...] = (r"ProjectionSoftwareConverter-(?P<version>.+)-Setup\.exe\.sha256",)
    macos_release_asset_patterns: tuple[str, ...] = (
        r"ProjectionSoftwareConverter-(?P<version>.+)-macOS\.(?:zip|dmg)",
        r"ProjectionSoftwareConverter-(?P<version>.+)-macos\.(?:zip|dmg)",
        r"ProjectionSoftwareConverter-(?P<version>.+)-darwin\.(?:zip|dmg)",
    )
    macos_checksum_asset_patterns: tuple[str, ...] = (
        r"ProjectionSoftwareConverter-(?P<version>.+)-macOS\.(?:zip|dmg)\.sha256",
        r"ProjectionSoftwareConverter-(?P<version>.+)-macos\.(?:zip|dmg)\.sha256",
        r"ProjectionSoftwareConverter-(?P<version>.+)-darwin\.(?:zip|dmg)\.sha256",
    )
    linux_release_asset_patterns: tuple[str, ...] = (
        r"ProjectionSoftwareConverter-(?P<version>.+)-linux\.AppImage",
        r"ProjectionSoftwareConverter-(?P<version>.+)-linux\.tar\.gz",
        r"ProjectionSoftwareConverter-(?P<version>.+)-Linux\.AppImage",
        r"ProjectionSoftwareConverter-(?P<version>.+)-Linux\.tar\.gz",
    )
    linux_checksum_asset_patterns: tuple[str, ...] = (
        r"ProjectionSoftwareConverter-(?P<version>.+)-linux\.(?:AppImage|tar\.gz)\.sha256",
        r"ProjectionSoftwareConverter-(?P<version>.+)-Linux\.(?:AppImage|tar\.gz)\.sha256",
    )
    platform_override: str | None = None
    api_base_url: str = "https://api.github.com"
    include_prereleases: bool = False


@dataclass(frozen=True)
class AppConfig:
    app_name: str = APP_NAME
    company_name: str = APP_NAME
    version: str = __version__
    github_updates: GitHubUpdateConfig = GitHubUpdateConfig(
        owner="REPLACE_WITH_GITHUB_OWNER",
        repo="REPLACE_WITH_GITHUB_REPOSITORY",
    )


def _github_update_config_from_env() -> GitHubUpdateConfig:
    return GitHubUpdateConfig(
        owner=os.getenv("PSC_GITHUB_OWNER", "REPLACE_WITH_GITHUB_OWNER"),
        repo=os.getenv("PSC_GITHUB_REPOSITORY", "REPLACE_WITH_GITHUB_REPOSITORY"),
        platform_override=os.getenv("PSC_RELEASE_PLATFORM") or None,
        )


DEFAULT_CONFIG = AppConfig(github_updates=_github_update_config_from_env())

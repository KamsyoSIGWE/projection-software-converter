from __future__ import annotations

import os
from dataclasses import dataclass

from .version import __version__

APP_NAME = "Projection Software Converter"
APP_EXE_NAME = "ProjectionSoftwareConverter.exe"


@dataclass(frozen=True)
class GitHubUpdateConfig:
    owner: str
    repo: str
    installer_asset_pattern: str = r"ProjectionSoftwareConverter-(?P<version>.+)-Setup\.exe"
    checksum_asset_pattern: str = r"ProjectionSoftwareConverter-(?P<version>.+)-Setup\.exe\.sha256"
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
    )


DEFAULT_CONFIG = AppConfig(github_updates=_github_update_config_from_env())

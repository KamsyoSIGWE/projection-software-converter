from __future__ import annotations

import unittest

from projection_software_converter.config import GitHubUpdateConfig
from projection_software_converter.updater import GitHubReleaseUpdater


class GitHubReleaseUpdaterTests(unittest.TestCase):
    def _build_updater(self, *, platform_override: str) -> GitHubReleaseUpdater:
        return GitHubReleaseUpdater(
            GitHubUpdateConfig(
                owner="example",
                repo="projection-software-converter",
                platform_override=platform_override,
            )
        )

    def test_selects_windows_release_asset(self) -> None:
        updater = self._build_updater(platform_override="windows")
        releases = [
            {
                "tag_name": "v0.2.0",
                "body": "notes",
                "html_url": "https://example.test/windows",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": "ProjectionSoftwareConverter-0.2.0-Setup.exe",
                        "browser_download_url": "https://example.test/windows.exe",
                    },
                    {
                        "name": "ProjectionSoftwareConverter-0.2.0-Setup.exe.sha256",
                        "browser_download_url": "https://example.test/windows.exe.sha256",
                    },
                ],
            }
        ]

        release = updater._select_latest_release(releases)

        self.assertIsNotNone(release)
        assert release is not None
        self.assertEqual(release.package.name, "ProjectionSoftwareConverter-0.2.0-Setup.exe")
        self.assertEqual(release.checksum.name, "ProjectionSoftwareConverter-0.2.0-Setup.exe.sha256")

    def test_selects_macos_release_asset(self) -> None:
        updater = self._build_updater(platform_override="macos")
        releases = [
            {
                "tag_name": "v0.3.0",
                "body": "notes",
                "html_url": "https://example.test/macos",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": "ProjectionSoftwareConverter-0.3.0-macOS.dmg",
                        "browser_download_url": "https://example.test/macos.dmg",
                    },
                    {
                        "name": "ProjectionSoftwareConverter-0.3.0-macOS.dmg.sha256",
                        "browser_download_url": "https://example.test/macos.dmg.sha256",
                    },
                    {
                        "name": "ProjectionSoftwareConverter-0.3.0-Setup.exe",
                        "browser_download_url": "https://example.test/windows.exe",
                    },
                ],
            }
        ]

        release = updater._select_latest_release(releases)

        self.assertIsNotNone(release)
        assert release is not None
        self.assertEqual(release.package.name, "ProjectionSoftwareConverter-0.3.0-macOS.dmg")
        self.assertEqual(release.checksum.name, "ProjectionSoftwareConverter-0.3.0-macOS.dmg.sha256")

    def test_selects_linux_release_asset(self) -> None:
        updater = self._build_updater(platform_override="linux")
        releases = [
            {
                "tag_name": "v0.4.0",
                "body": "notes",
                "html_url": "https://example.test/linux",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": "ProjectionSoftwareConverter-0.4.0-linux.AppImage",
                        "browser_download_url": "https://example.test/linux.AppImage",
                    },
                    {
                        "name": "ProjectionSoftwareConverter-0.4.0-linux.AppImage.sha256",
                        "browser_download_url": "https://example.test/linux.AppImage.sha256",
                    },
                ],
            }
        ]

        release = updater._select_latest_release(releases)

        self.assertIsNotNone(release)
        assert release is not None
        self.assertEqual(release.package.name, "ProjectionSoftwareConverter-0.4.0-linux.AppImage")
        self.assertEqual(release.checksum.name, "ProjectionSoftwareConverter-0.4.0-linux.AppImage.sha256")

    def test_skips_release_without_matching_platform_asset(self) -> None:
        updater = self._build_updater(platform_override="macos")
        releases = [
            {
                "tag_name": "v0.2.0",
                "body": "notes",
                "html_url": "https://example.test/windows",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": "ProjectionSoftwareConverter-0.2.0-Setup.exe",
                        "browser_download_url": "https://example.test/windows.exe",
                    }
                ],
            }
        ]

        release = updater._select_latest_release(releases)

        self.assertIsNone(release)


if __name__ == "__main__":
    unittest.main()

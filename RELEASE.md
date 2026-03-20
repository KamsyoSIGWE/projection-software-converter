# Release Process

## Local Release Steps
1. Update code and documentation.
2. Ensure the version in `src/projection_software_converter/version.py` is correct.
3. Build the Windows bundle and installer.
4. Test install, launch, convert, update-check, and uninstall.
5. Create a Git tag like `v0.2.0`.
6. Push the tag and publish a GitHub Release.

## GitHub Actions
The workflow in `.github/workflows/windows-release.yml`:
- installs dependencies
- generates the icon and version metadata
- builds the PyInstaller app bundle
- compiles the Inno Setup installer
- computes SHA256 hashes
- uploads artifacts
- attaches release assets when triggered by a GitHub Release

## Asset Naming
The updater expects installer assets to follow:
- `ProjectionSoftwareConverter-<version>-Setup.exe`
- optionally `ProjectionSoftwareConverter-<version>-Setup.exe.sha256`

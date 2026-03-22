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
- optionally signs `ProjectionSoftwareConverter.exe` when signing secrets are configured
- compiles the Inno Setup installer
- optionally signs the installer `.exe` when signing secrets are configured
- computes SHA256 hashes
- uploads artifacts
- attaches release assets when triggered by a GitHub Release

### Optional Windows Signing Setup

To enable automatic Windows code signing in GitHub Actions, add these repository secrets:

- `WINDOWS_CODESIGN_PFX_BASE64`
- `WINDOWS_CODESIGN_PFX_PASSWORD`

Optional repository variable:

- `WINDOWS_CODESIGN_TIMESTAMP_URL`

The `.pfx` file should be base64 encoded before storing it in `WINDOWS_CODESIGN_PFX_BASE64`.

PowerShell helper:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\path\to\certificate.pfx"))
```

## Asset Naming
The updater expects installer assets to follow:
- `ProjectionSoftwareConverter-<version>-Setup.exe`
- optionally `ProjectionSoftwareConverter-<version>-Setup.exe.sha256`

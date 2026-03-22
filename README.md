# Projection Software Converter

Projection Software Converter is a desktop application for moving presentation packages between supported projection platforms without rewriting the UI each time a new converter is added.

The current release supports:
- VideoPsalm `.vpagd` -> FreeShow `.project`
- FreeShow `.project` -> VideoPsalm `.vpagd`
- EasyWorship `.ewsx` -> FreeShow `.project`
- FreeShow `.project` -> EasyWorship `.ewsx`

The app exposes those formats through a central conversion registry, a PySide6 desktop interface, a CLI, a Windows installer, and a GitHub Releases based updater. Windows release artifacts are currently the packaged distribution target, while macOS and Linux portability work is in progress.

## Features
- Dynamic supported-conversions registry
- PySide6 desktop interface with upload/convert workflow
- Registry-driven validation and converter routing
- GitHub Releases update checks and release-package handoff
- PyInstaller packaging in `onedir` mode
- Inno Setup installer with per-user or all-users install choice
- GitHub Actions workflows for Windows releases and cross-platform native build artifacts

## Quick Start
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[build]
python -m projection_software_converter
```

## CLI
Launch the GUI:
```powershell
python -m projection_software_converter
```

Run a conversion directly:
```powershell
projection-software-converter-cli convert `
  --input .\031526.vpagd `
  --from VideoPsalm `
  --to FreeShow `
  --output .\out\031526.project
```

Inspect available conversions:
```powershell
projection-software-converter-cli list-conversions
```

Check for updates without opening the UI:
```powershell
projection-software-converter-cli check-updates
```

## Project Layout
- `src/projection_software_converter`: app, GUI, registry, service, updater
- `src/videosalm_to_freeshow`: compatibility wrapper for the legacy package name
- `installer/ProjectionSoftwareConverter.iss`: Inno Setup installer script
- `projection-software-converter.spec`: PyInstaller spec
- `.github/workflows/windows-release.yml`: Windows CI/release workflow
- `.github/workflows/cross-platform-build.yml`: native Windows/macOS/Linux build matrix
- `scripts/`: helper scripts for icon generation and version metadata

## Documentation
- [BUILD_WINDOWS.md](BUILD_WINDOWS.md)
- [BUILD_MACOS.md](BUILD_MACOS.md)
- [BUILD_LINUX.md](BUILD_LINUX.md)
- [INSTALLER.md](INSTALLER.md)
- [RELEASE.md](RELEASE.md)
- [GitHub Releases](https://github.com/KamsyoSIGWE/projection-software-converter/releases)

## Sharing With Other Windows Users
For quick sharing, zip and send `dist\Projection Software Converter\`.

For a cleaner install and update experience, build the Inno Setup installer and send the `.exe` from `dist\installer\`. The installer shows the standard Windows setup wizard and progress bar while installing files.

## Cross-Platform Status
The conversion engine and GUI are being prepared for macOS and Linux support, but the packaged release workflow is still Windows-first today. See [MAC_LINUX_PORT_PROMPT.md](MAC_LINUX_PORT_PROMPT.md) and [MAC_LINUX_PHASE1_REPORT.md](MAC_LINUX_PHASE1_REPORT.md) for the current portability plan and audit.

For native-machine build steps during this transition, see [BUILD_MACOS.md](BUILD_MACOS.md) and [BUILD_LINUX.md](BUILD_LINUX.md).

The repository now includes a native GitHub Actions build matrix for Windows, macOS, and Linux. At this stage it produces native folder-based PyInstaller bundles plus archived CI artifacts; polished macOS and Linux release formats still need follow-up work.

## Adding a New Converter
1. Add the format pair to `src/projection_software_converter/resources/conversions.json`.
2. Implement the handler function.
3. Register it in `src/projection_software_converter/conversion/bootstrap.py`.

No UI changes are required because the UI reads directly from the registry.

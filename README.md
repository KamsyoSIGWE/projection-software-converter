# Projection Software Converter

Projection Software Converter is a Windows-friendly desktop application for moving presentation packages between supported projection platforms without rewriting the UI each time a new converter is added.

The current release supports:
- VideoPsalm `.vpagd` -> FreeShow `.project`
- FreeShow `.project` -> VideoPsalm `.vpagd`

The app exposes those formats through a central conversion registry, a PySide6 desktop interface, a CLI, a Windows installer, and a GitHub Releases based updater.

## Features
- Dynamic supported-conversions registry
- PySide6 desktop interface with upload/convert workflow
- Registry-driven validation and converter routing
- GitHub Releases update checks and installer handoff
- PyInstaller packaging in `onedir` mode
- Inno Setup installer with per-user or all-users install choice
- GitHub Actions workflow for Windows builds and release artifacts

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
- `scripts/`: helper scripts for icon generation and version metadata

## Documentation
- [BUILD_WINDOWS.md](BUILD_WINDOWS.md)
- [INSTALLER.md](INSTALLER.md)
- [RELEASE.md](RELEASE.md)

## Adding a New Converter
1. Add the format pair to `src/projection_software_converter/resources/conversions.json`.
2. Implement the handler function.
3. Register it in `src/projection_software_converter/conversion/bootstrap.py`.

No UI changes are required because the UI reads directly from the registry.

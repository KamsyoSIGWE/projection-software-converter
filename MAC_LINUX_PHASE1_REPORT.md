# Phase 1 macOS/Linux Compatibility Report

Date: 2026-03-22

## Scope

This report covers the Phase 1 audit from `MAC_LINUX_PORT_PROMPT.md`:

- inspect the current codebase for Windows-only assumptions
- identify packaging and release blockers for macOS and Linux
- separate true runtime blockers from Windows-specific distribution choices

## Summary

The core conversion engine is much closer to cross-platform than the release/distribution story.

The biggest blockers are not the converters themselves. They are:

1. the updater/release pipeline assumes a Windows installer `.exe`
2. build docs and CI only target Windows
3. the current packaging metadata and spec are tuned for Windows artifacts
4. project messaging still describes the app as Windows-only or Windows-first

## High-priority blockers

### 1. Update system is Windows-installer centric

Files:

- `src/projection_software_converter/config.py`
- `src/projection_software_converter/updater.py`
- `src/projection_software_converter/gui/main_window.py`

Findings:

- `APP_EXE_NAME` is hardcoded to `ProjectionSoftwareConverter.exe`
- GitHub release asset matching expects `ProjectionSoftwareConverter-<version>-Setup.exe`
- checksum matching also assumes installer `.exe.sha256`
- the GUI update flow is written around "download installer and launch it"

Impact:

- macOS and Linux cannot use the current release/update model as-is
- platform-specific asset discovery and install behavior will need to be introduced

### 2. Build and release workflow only targets Windows

Files:

- `BUILD_WINDOWS.md`
- `INSTALLER.md`
- `.github/workflows/windows-release.yml`

Findings:

- all documented packaging steps use PowerShell
- CI only builds on `windows-latest`
- installer generation depends on Inno Setup
- release attachment is built around Windows installer artifacts

Impact:

- there is currently no supported macOS or Linux build path
- native macOS and Linux runners will be required

### 3. Packaging spec is Windows-oriented

Files:

- `projection-software-converter.spec`
- `scripts/write_version_info.py`
- `assets/app.ico`

Findings:

- the spec is single-path and currently optimized around Windows output naming
- `write_version_info.py` produces Windows version-resource metadata
- the current icon asset is `.ico`, which is fine for Windows but not ideal as the only icon source for macOS/Linux packaging

Impact:

- the spec likely needs platform-conditional behavior or separate specs
- macOS should eventually use `.icns`
- Linux likely needs desktop entry/icon packaging decisions

### 4. Project metadata and docs still present the app as Windows-specific

Files:

- `pyproject.toml`
- `README.md`

Findings:

- project description says "Windows desktop tool"
- README describes the app as "Windows-friendly"
- sharing/install sections focus on Windows users

Impact:

- the project is not yet documented as cross-platform
- this would cause confusion even if macOS/Linux builds existed

## Medium-priority blockers and risks

### 5. Default user-folder logic is portable enough, but not native-best

File:

- `src/projection_software_converter/gui/upload_dialog.py`

Findings:

- output defaults to `Path.home() / "Downloads"`
- fallback is `Path.home()`

Impact:

- this is likely to work on many systems
- using `QStandardPaths` would be more native and more reliable across desktops

### 6. Some conversion code intentionally writes Windows-style paths into exported formats

File:

- `src/projection_software_converter/conversion/videosalm_freeshow.py`

Findings:

- synthetic Windows-style paths are generated for VideoPsalm compatibility
- some import/export helpers normalize backslashes explicitly

Impact:

- this is not necessarily a blocker, because those strings may be part of the target file format rather than the host OS
- it should be reviewed carefully so we do not "fix" format-specific behavior that is actually required

### 7. Package-data declaration is probably too narrow for future cross-platform packaging

File:

- `pyproject.toml`

Findings:

- package data only declares `projection_software_converter = ["resources/*.json"]`
- the app now also depends on nested EasyWorship template assets under `resources/easyworship_templates/`, including `.db` files

Impact:

- editable installs and PyInstaller builds may work today, but wheel/sdist/native packaging could miss required assets
- this should be widened before broader distribution work

## Items that already look mostly portable

### 1. Core conversion service and registry

Files:

- `src/projection_software_converter/conversion/service.py`
- `src/projection_software_converter/conversion/bootstrap.py`
- converter modules under `src/projection_software_converter/conversion/`

Notes:

- uses `pathlib`
- no obvious Windows-only runtime dependency in the conversion dispatch layer

### 2. GUI structure

Files:

- `src/projection_software_converter/gui/main_window.py`
- `src/projection_software_converter/gui/upload_dialog.py`

Notes:

- PySide6 GUI code itself is not Windows-bound
- file dialogs and worker-thread conversion flow should translate well

### 3. CLI entry points

File:

- `pyproject.toml`

Notes:

- console entry points are standard setuptools scripts
- this is a good base for cross-platform usage and testing

## Recommended Phase 2 starting points

Do Phase 2 in this order:

1. replace Windows-specific project metadata wording in `pyproject.toml` and `README.md`
2. switch Downloads-folder discovery to `QStandardPaths`
3. widen package-data declarations to include nested resource templates and `.db` assets
4. separate updater asset logic from Windows-only installer assumptions
5. add `BUILD_MACOS.md` and `BUILD_LINUX.md`

## Native-build requirement

This audit confirms that macOS and Linux release artifacts should be built on native runners or native machines.

Recommended build matrix:

- Windows: current PyInstaller + Inno Setup flow
- macOS: PyInstaller on macOS runner or machine
- Linux: PyInstaller on Linux runner or machine

Do not treat Windows as the source of truth for cross-platform packaging behavior.

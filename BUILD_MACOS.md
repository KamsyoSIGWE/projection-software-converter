# Build macOS App

## Current status

macOS support is in progress. The current repository can now build a native `.app` bundle on a macOS machine and package it as a versioned zip for distribution, but signing, notarization, and `.dmg` creation are not part of the current flow yet.

Run these steps on macOS, not on Windows.

## Prerequisites

- Python 3.10+
- Terminal access on macOS

## Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .[build]
```

## Run the app locally

```bash
python -m projection_software_converter
```

## Build the current macOS bundle

```bash
python -m PyInstaller ./projection-software-converter.spec --noconfirm
```

## Output

The current PyInstaller spec produces:

- `dist/Projection Software Converter.app`
- `dist/Projection Software Converter/`

The executable inside the app bundle is:

`dist/Projection Software Converter.app/Contents/MacOS/ProjectionSoftwareConverter`

For release-style packaging, zip the app bundle as:

`ProjectionSoftwareConverter-<version>-macOS.zip`

## Notes

- This is an early cross-platform build path and may still need macOS-specific polish.
- A custom `.icns` asset flow, signing, notarization, and `.dmg` packaging are not part of the current implementation yet.
- Windows-specific version metadata and installer generation are intentionally not part of the macOS build path.
- Use this build path for native macOS testing while the broader macOS release flow is being added.

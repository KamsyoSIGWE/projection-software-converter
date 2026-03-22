# Build macOS App

## Current status

macOS support is in progress. The current repository can be built on a native macOS machine for local testing and folder-based distribution, but it does not yet produce a polished notarized `.app` or `.dmg` release flow.

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
python ./scripts/generate_icon.py
PYTHONPATH="$PWD/src" python ./scripts/write_version_info.py
python -m PyInstaller ./projection-software-converter.spec --noconfirm
```

## Output

The current PyInstaller spec produces a folder-based build under:

`dist/Projection Software Converter/`

The executable inside that folder is:

`dist/Projection Software Converter/ProjectionSoftwareConverter`

## Notes

- This is an early cross-platform build path and may still need macOS-specific polish.
- A native `.app`, `.icns` asset flow, signing, and notarization are not part of the current implementation yet.
- Use this build path for native macOS testing while the broader macOS release flow is being added.

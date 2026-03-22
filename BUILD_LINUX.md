# Build Linux App

## Current status

Linux support is in progress. The current repository can be built on a native Linux machine for local testing and folder-based distribution, but it does not yet produce a Linux-specific release format such as AppImage or a distro package.

Run these steps on Linux, not on Windows.

## Prerequisites

- Python 3.10+
- A desktop environment capable of running PySide6 apps

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

## Build the current Linux bundle

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

- This is an early cross-platform build path and may still need Linux-specific polish.
- AppImage, `.tar.gz`, desktop-entry integration, and distro-specific packaging are not part of the current implementation yet.
- Use this build path for native Linux testing while the broader Linux release flow is being added.

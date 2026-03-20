# Build Windows App

## Prerequisites
- Python 3.10+
- Inno Setup 6
- PowerShell

## Install Dependencies
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[build]
```

## Build the App Bundle
```powershell
python .\scripts\generate_icon.py
$env:PYTHONPATH = "$PWD\src"
python .\scripts\write_version_info.py
pyinstaller .\projection-software-converter.spec --noconfirm
```

The packaged app will be created under `dist\Projection Software Converter\`.

## Build Installer
```powershell
$env:PYTHONPATH = "$PWD\src"
$env:APP_VERSION = (python -c "from projection_software_converter.version import __version__; print(__version__)")
iscc .\installer\ProjectionSoftwareConverter.iss
```

The installer will be written to `dist\installer\`.

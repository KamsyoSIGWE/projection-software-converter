# Installer Notes

The installer is built with Inno Setup and is configured for:
- Current-user installs under `%LOCALAPPDATA%\Programs\Projection Software Converter`
- All-users installs under `%ProgramFiles%\Projection Software Converter`
- Start Menu shortcut
- Optional Desktop shortcut
- Launch after installation
- Clean uninstall support

## Build
```powershell
python .\scripts\generate_icon.py
$env:PYTHONPATH = "$PWD\src"
python .\scripts\write_version_info.py
pyinstaller .\projection-software-converter.spec --noconfirm
$env:APP_VERSION = (python -c "from projection_software_converter.version import __version__; print(__version__)")
iscc .\installer\ProjectionSoftwareConverter.iss
```

## Install Mode
The installer uses Inno Setup's install mode selection so the user can choose between:
- current user only
- all users

## Post-Install Launch
After installation, the user can leave the default checkbox enabled to launch Projection Software Converter immediately.

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

The generated installer shows the normal Windows install wizard with a file-copy progress bar.

## Install Mode
The installer uses Inno Setup's install mode selection so the user can choose between:
- current user only
- all users

## Post-Install Launch
After installation, the user can leave the default checkbox enabled to launch Projection Software Converter immediately.

## Shipping Updates
For user-friendly updates, send the installer from `dist\installer\` instead of a zip of the app folder. The installer can upgrade an existing installation and shows the normal Windows progress UI while it installs.

If you want the app's "Check for Updates" feature to use your GitHub Releases, set these environment variables before building:

```powershell
$env:PSC_GITHUB_OWNER = "your-github-owner"
$env:PSC_GITHUB_REPOSITORY = "your-github-repo"
```

Then publish releases whose installer assets follow this naming pattern:
- `ProjectionSoftwareConverter-<version>-Setup.exe`
- `ProjectionSoftwareConverter-<version>-Setup.exe.sha256`

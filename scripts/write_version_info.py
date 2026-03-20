from __future__ import annotations

from pathlib import Path

from projection_software_converter.config import APP_NAME
from projection_software_converter.version import __version__


def version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = [int(part) for part in version.split(".") if part.isdigit()]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def main() -> None:
    major, minor, patch, build = version_tuple(__version__)
    output_path = Path("packaging") / "version_info.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, {build}),
    prodvers=({major}, {minor}, {patch}, {build}),
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', '{APP_NAME}'),
          StringStruct('FileDescription', '{APP_NAME}'),
          StringStruct('FileVersion', '{__version__}'),
          StringStruct('InternalName', 'ProjectionSoftwareConverter'),
          StringStruct('OriginalFilename', 'ProjectionSoftwareConverter.exe'),
          StringStruct('ProductName', '{APP_NAME}'),
          StringStruct('ProductVersion', '{__version__}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)"""
    output_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()

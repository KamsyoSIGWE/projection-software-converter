# macOS/Linux Port Prompt

Use this prompt when continuing the work to make Projection Software Converter available to macOS and Linux users.

## Prompt

You are working in the `projection-software-converter` repository. The Windows build is already functioning and includes:

- FreeShow <-> EasyWorship conversion
- FreeShow <-> VideoPsalm conversion
- GUI packaging with PyInstaller on Windows
- installer support for Windows with Inno Setup

Your goal is to make this app available to macOS and Linux users in a clean, release-ready way.

Important rules:

1. Do not assume Windows packaging steps work on macOS or Linux.
2. Do not try to produce a macOS `.app` or Linux release artifact from Windows only.
3. Use native runners or native machines for platform builds:
   - macOS build on macOS
   - Linux build on Linux
4. Preserve the current Windows workflow.
5. Keep the GUI and CLI both working.
6. Prefer small, verifiable steps and test after each phase.

## Ordered plan

### Phase 1: Audit platform assumptions

1. Inspect the codebase for Windows-only assumptions, including:
   - path handling
   - PowerShell-specific build steps
   - Windows-only executable names
   - installer assumptions
   - shell commands in docs/scripts
2. Review:
   - `pyproject.toml`
   - `projection-software-converter.spec`
   - `scripts/`
   - `README.md`
   - `BUILD_WINDOWS.md`
   - installer docs/files
3. Identify any app code that assumes Windows directories or separators.

Deliverable:
- a short compatibility report listing blockers for macOS and Linux

### Phase 2: Make runtime behavior cross-platform

1. Ensure file/path code uses `pathlib` or portable path logic.
2. Verify Downloads-folder default logic works on:
   - Windows
   - macOS
   - Linux
3. Verify the GUI launches with PySide6 on all supported platforms.
4. Check that conversion logic does not rely on Windows-only filesystem behavior.

Deliverable:
- code changes that make runtime behavior platform-safe

### Phase 3: Split build docs by platform

1. Keep Windows instructions as-is or lightly updated.
2. Add separate build docs for:
   - macOS
   - Linux
3. Document:
   - venv setup
   - editable install
   - app launch
   - PyInstaller packaging
   - output artifact locations

Deliverables:
- `BUILD_MACOS.md`
- `BUILD_LINUX.md`
- updated `README.md`

### Phase 4: Add native packaging for macOS

1. Build the GUI app with PyInstaller on macOS.
2. Verify the app launches as a macOS `.app`.
3. Confirm bundled resources, icons, and conversion templates are included.
4. If needed, add a macOS-specific PyInstaller spec or conditional logic.
5. Decide whether to ship:
   - `.app` in a zip
   - `.dmg`

Deliverables:
- working macOS build steps
- documented macOS artifact format

### Phase 5: Add native packaging for Linux

1. Build the GUI app with PyInstaller on Linux.
2. Verify the app launches on a normal desktop environment.
3. Confirm bundled resources, icons, and conversion templates are included.
4. Decide whether to ship:
   - extracted folder
   - `.tar.gz`
   - AppImage

Deliverables:
- working Linux build steps
- documented Linux artifact format

### Phase 6: Automate builds in CI

1. Add a GitHub Actions matrix for:
   - Windows
   - macOS
   - Linux
2. Install dependencies per platform.
3. Build artifacts per platform.
4. Upload artifacts from CI.
5. Keep Windows installer generation separate if needed.

Deliverables:
- CI workflow that produces release artifacts for all platforms

### Phase 7: Verify user-facing behavior

1. Test these flows on each platform:
   - launch GUI
   - choose input file
   - choose output folder
   - convert EasyWorship -> FreeShow
   - convert FreeShow -> EasyWorship
   - convert FreeShow -> VideoPsalm
   - convert VideoPsalm -> FreeShow
2. Verify packaged apps can read/write files correctly outside the repo.
3. Check that output defaults and file dialogs feel native enough.

Deliverable:
- release checklist with pass/fail results by platform

### Phase 8: Release polish

1. Update docs to explain what to send users on each platform.
2. Add versioned release notes.
3. Clarify platform limitations, if any.
4. If notarization/signing is needed later, document it as a follow-up rather than blocking initial support unless required.

Deliverable:
- final release notes and distribution guidance

## Specific things to verify

- PySide6 plugins bundle correctly on macOS and Linux
- the EasyWorship template resources are included in packaged builds
- VideoPsalm and FreeShow conversions still bundle media correctly
- the app does not rely on `iscc` except for Windows installer builds
- no docs tell macOS/Linux users to run Windows-only commands

## Preferred execution order

Do the work in this order:

1. compatibility audit
2. runtime portability fixes
3. platform build docs
4. macOS packaging
5. Linux packaging
6. CI automation
7. cross-platform verification
8. release polish

## Final deliverables

When done, provide:

1. summary of cross-platform code changes
2. list of new docs added
3. exact build commands per platform
4. exact output artifact locations per platform
5. known limitations
6. what still requires native macOS/Linux testing if CI was not available

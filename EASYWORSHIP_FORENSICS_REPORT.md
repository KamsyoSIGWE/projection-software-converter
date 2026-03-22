# EasyWorship `.ewsx` Forensics Report

## Scope

The EasyWorship exporter is now anchored to two real truth files:

- `C:\Users\osigw\Downloads\single_video_valid.ewsx`
- `C:\Users\osigw\Downloads\Telegram Desktop\Camp prayer 2025 Feb.ewsx`

The working assumptions are:

- the one-video file is the canonical truth for minimal video schedules in the current EW7 version family
- the camp-prayer file is the canonical truth for minimal image schedules in the same version family
- multi-item export should be assembled by cloning those minimal truth blocks instead of guessing a fresh schema

## What The Truth Files Proved

- The container is ZIP-like and EasyWorship-version-sensitive.
- Minimal valid schedules can be as small as:
  - `main.db`
  - `media`
  - one packed media member
- The SQLite database can stay minimal:
  - one media presentation
  - one `Global` presentation
- The valid minimal files do not require injected `Blank` or `bg4` presentations.
- The database uses a `1024` byte page size.
- Media is embedded directly inside the schedule.
- Minimal video and minimal image schedules have different media-presentation row shapes, so one template is not enough.

## What Differed In Earlier Invalid Exports

Before the template-driven rewrite, invalid generated files differed from the truth samples in several ways:

- the database schema was freshly guessed instead of cloned
- SQLite column declarations drifted from the truth samples
- `sqlite_sequence` drifted
- row content drifted in `presentation`, `slide`, `resource`, `file`, `resource_video`, and `resource_text`
- packed media naming and metadata were generated heuristically instead of preserved from the template
- the archive stopped after the last local member payload and did not write the ZIP central directory and end-of-central-directory footer

Those differences were enough for EasyWorship to reject the file as invalid.

## What Was Added

### Inspector / Comparator

Added `projection_software_converter.conversion.easyworship_inspector` with:

- `inspect_ewsx(...)`
- `extract_ewsx_members(...)`
- `inspect_sqlite_bytes(...)`
- `schema_diff_sqlite(...)`
- `diff_ewsx(...)`
- `dump_ewsx_report(...)`

The comparator reports:

- container mode
- member list
- local-header metadata
- central directory / EOCD metadata
- whether the file is readable by standard ZIP tooling
- SQLite schema drift
- per-table row drift summaries

### Embedded Template Shells

The project now carries packaged EasyWorship template shells under:

- `src/projection_software_converter/resources/easyworship_templates/single_video_valid.main.db`
- `src/projection_software_converter/resources/easyworship_templates/single_video_valid.bundle.json`
- `src/projection_software_converter/resources/easyworship_templates/single_image_valid.main.db`
- `src/projection_software_converter/resources/easyworship_templates/single_image_valid.bundle.json`

This removes the runtime dependency on local copies of the truth `.ewsx` files living in `Downloads`.

### Exporter Rewrite

`FreeShow -> EasyWorship` now uses per-kind template shells:

- load the embedded truth-derived video or image shell
- start the output `main.db` from the first item's truth shell
- append additional media presentations by cloning the corresponding truth block for each extra image or video item
- preserve the truth file's member ordering, local-header metadata, global block, and constant rows

The mutable fields are intentionally narrow:

- presentation title
- resource titles
- RTF title text
- file hash
- packed media filename
- media order index
- `resource_video` media facts such as filename, size, dimensions, duration, and stream metadata
- `resource_image` media facts such as filename, size, and modified date

The bundle writer now emits:

- local file headers
- central directory entries
- end-of-central-directory footer

That matters because the real truth files include a standard ZIP footer, while the earlier invalid generated files did not.

## Current Diff Result

When the exporter is fed the same payload as the real minimal truth samples:

- the generated one-video export matches `single_video_valid.ewsx`
- the generated one-image export matches `Camp prayer 2025 Feb.ewsx`

The current regression diff for both single-item paths is:

- `member_metadata_differences = []`
- `missing_tables = []`
- `extra_tables = []`
- `table_diffs = {}`
- `row_differences = {}`

## Current Status

- `EasyWorship -> FreeShow`: implemented
- `.ewsx` inspector/comparator: implemented
- one-video `FreeShow -> EasyWorship`: template-driven and validated against the video truth file
- one-image `FreeShow -> EasyWorship`: template-driven and validated against the image truth file
- multi-item image/video `FreeShow -> EasyWorship`: template-driven from the per-kind truth blocks
- regression tests against the real truth files: added
- mixed-order regression coverage: added for both video-first and image-first schedules

## Recommended Next Step

Rebuild the app, generate fresh mixed image/video `.ewsx` schedules, and test them in the same EasyWorship build that opened the truth files.

If EasyWorship rejects a newly generated multi-item file, the next debugging target should be:

- the remaining differences between minimal truth-derived schedules and larger real-world schedules
- or ordering / metadata fields that only become significant when several items share the same schedule

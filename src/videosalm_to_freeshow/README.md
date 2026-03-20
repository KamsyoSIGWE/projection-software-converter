# videosalm_to_freeshow

Convert a VideoPsalm `.vpagd` agenda package into a FreeShow `.project` package.

This converter currently targets the same simple FreeShow project shape seen in these user-provided samples:
- `single_image.project`
- `video_with_title.project`
- `two_item_playlist.project`

## What it preserves
- agenda order
- item titles
- image items
- video items
- bundled media copied into the `.project` zip

## Current mapping
Each VideoPsalm image/video becomes a simple FreeShow project item in `project.shows` with:
- `name` = VideoPsalm `Text`
- `id` = original Windows source path from VideoPsalm (or a synthetic Windows-style path if missing)
- `type` = `image` or `video`
- `index` = agenda order

Videos also get a minimal `media` entry with empty `tracks`, matching the uploaded FreeShow samples.

## Usage
```bash
pip install -e .
python -m videosalm_to_freeshow input.vpagd -o output.project
```

Inspect parsed agenda items only:
```bash
python -m videosalm_to_freeshow input.vpagd --inspect
```

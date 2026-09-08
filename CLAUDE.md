# Repo conventions for AI agents

Read `PROMPT.md` for the full brief and the backlog. This file is the short
version that must hold for every change.

## Never break these

1. **The dieline must agree across all four implementations.** Run
   `python3 tools/verify_geometry.py` after any change touching box dimensions,
   UV maths or panel layout. It must exit 0. Never raise the tolerance to make a
   failure pass.
2. **`app/daybreak-studio.html` stays one self-contained file.** No bundler, no
   framework, no CDN. It is opened from `file://`, frequently offline.
3. **Blender scripts support 4.2 – 5.1.** Use the existing `action_fcurves()`,
   engine-picking and icon-validation helpers rather than writing new
   version-specific code.
4. **Textures stay square.** Panel rects are positions inside the square canvas,
   not a crop.
5. **The watcher never feeds Blender a partial file.** `tools/watch_jobs.py`
   requires both settled file size *and* a valid PNG `IEND` trailer. Keep both —
   size alone cannot distinguish a finished download from a stalled one.
6. **No hardcoded Blender paths.** Use `find_blender()`; bundle names vary.
7. **Top-level `$()` calls go below `const $`** in the app's UI section. A
   call above it throws at load and leaves `$` uninitialised for the whole page.
8. **Version through `tools/release.py --bump`, never by hand.** `VERSION` and
   the app's `APP_VERSION` are the same number in two places; the verifier
   fails if they differ. Add a line to the opened `CHANGELOG.md` section.

## Delivering to Joe's machine

Every release goes to two places, and the second is not optional:
1. `../releases/daybreak-mills-v<version>.zip` — the versioned deliverable.
2. `python3 tools/update.py` run inside the checkout, so the IDE copy is the
   new version too. A zip that only sits in releases/ has not been delivered.

## Conventions

- Real-world units. Meshes are built at true size so object scale stays 1.0.
- Python: stdlib plus Pillow for `make_dielines.py`; `numpy` and `bmesh` are
  available inside Blender. Nothing else.
- Comments explain *why*, especially where a version quirk or a packaging rule
  drove the code. Don't narrate what the line already says.
- New numbers that describe the product (sizes, colours, type, regulatory
  minimums) belong in `spec/boxes.json`, not inline.

## Before you say a change is done

- `python3 tools/verify_geometry.py` exits 0
- the app opens from `file://` with no console errors and logs its UV self-test
- a job exported from the app still builds in Blender under 1e-7 drift

# Stage 1 regression baseline

Run from the project root:

```
python3 -m unittest discover -s tests -v
python3 tools/verify_geometry.py
node tests/browser_baseline.cjs
```

The browser test needs Playwright in the test environment. Set `NODE_PATH` if
using a separately installed package and `CHROME_PATH` to use a local Chrome
executable. These are test dependencies only; the Studio remains one offline HTML
file. Set `BASELINE_OUTPUT` to a temporary folder to retain its exported ZIP and
four size jobs for Blender verification.

Baseline scenarios:
- Existing `jobs/daybreak_mini_cocoa_job.json` and its PNG: compact, dark artwork.
- Existing `jobs/daybreak_regular_bran_job.json` and its PNG: regular, light artwork.
- Browser-generated session: custom claim, moved logo zone and embedded logo;
  import/export and IndexedDB save/load preserve them.
- Browser-generated Cocoa jobs: all four sizes match the canonical dimensions.
- SVG dimensions and PDF MediaBox match the current net in physical units.
- Offline boot has no uncaught errors and passes the UV self-test.
- Security tests run an isolated HTTP server with mocked Blender; no real builds,
  configuration changes or external network calls occur.

For the real Blender gate, extract `browser-single.zip` into a temporary folder
and run your detected Blender with `--background --python
blender/daybreak_pipeline.py -- --jobs <folder> --save <temporary-output.blend>`.
Confirm UV drift below 1e-7. A successful stub is not a substitute for this gate.


## Stage 2 projects

Run `node tests/projects.cjs` in the same Playwright environment. It checks
single-session migration, gallery naming, independent projects, duplication,
checkpoints, autosave recovery, embedded assets, camera restoration, invalid
imports, quota errors and retry, conflicting tabs, pending sketches, save races
and reopening. It uses a disposable browser context, never the user's profile.


## Stage 3 workspace

Run `node tests/workspace.cjs` using the same isolated Playwright setup. It checks
persistent 3D and panel previews, all six panel controls and face picking,
contextual numeric controls, aspect ratio, locking, layer order and visibility,
snapped pointer dragging, copy/brief/asset undo and redo, redo invalidation,
project history isolation and saved layer IDs after reopening. The screenshot
is written to a temporary folder for visual review.

## Stage 4 packaging content

Run `node tests/content.cjs` in the same Playwright environment. It covers real
editor interactions, shared inheritance, flavour overrides and explicit blanks,
non-negative nutrition input, copy undo/redo, actual canvas text, overflow
warnings, per-flavour job content, project isolation, reopening and legacy
content defaults. It also checks the embedded nutrient schema against the spec.
Nutrition figures in the test are synthetic fixtures, not product data.

## Stage 5 exports and queue

Run `node tests/output.cjs` in the same Playwright environment. It exercises the
actual export controls and paired HTTP queue: checks, explicit proof export,
checkpoint/hash references, SVG/PDF labels, stable textures, export cancellation,
submission, cancellation, retry, result download and design restoration. The
bridge and fake Blender use a disposable directory. The resulting Studio package
is retained as `/private/tmp/daybreak-stage5-proof.zip` for real Blender testing.

`python3 -m unittest discover -s tests -v` includes durable queue tests for
serialization, duplicate submissions, process cancellation, fresh retries,
restarts, timeouts, missing files and truncated output. Fake Blender writes to
the real pipeline output paths. A separate real Blender render must also succeed.

## Simplified connection

`node tests/connect.cjs` checks the Connect button, approval exchange and a
remembered connection after session storage is cleared and Studio is reloaded.
The isolated test service supplies approval; it never approves a real Mac dialog.
`test_pairing_flow.py` covers denied/expired requests, request isolation, rate
limits and explicit Allow-only handling of the native dialog result.

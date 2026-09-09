# Daybreak Mills


## Development roadmap

| Stage | Focus | Deliverables | Status |
| --- | --- | --- | --- |
| 1 | Security and baseline | Local bridge pairing, restricted Blender selection, upload validation, regression checks | Complete — v1.14.1 |
| 2 | Projects and recovery | Named projects, gallery, duplication, checkpoints, autosave, recovery and legacy session migration | Complete — v1.15.0 |
| 3 | Box-centered workspace | Brief/project starting screen, persistent live box, clickable panels, contextual editing, Edit asset tools, undo/redo and alignment | Planned |
| 4 | Complete packaging content | Editable back copy, ingredients, nutrition, per-flavour overrides and overflow indicators | Planned |
| 5 | Reliable export and rendering | Proof labeling, export checks, Blender queue, progress, cancellation, retry and version-linked results | Planned |
| 6 | Production output and polish | Printer-specific exports, accessibility, keyboard controls and performance | Planned |

Each stage ends with verified workflows, a reviewable release and focused commits
pushed to its working branch. Stage numbers describe the delivery sequence, not
the order of recommendations in the original review. Stage 2 builds on the
Stage 1 branch; the box-centered editing redesign is scheduled for Stage 3.

A packaging pipeline that runs from a demographic brief to a rendered carton and
a print-ready dieline, without anything being redrawn by hand in between.

```
 creative brief  →  auto-laid-out artwork  →  4K texture  →  Blender carton
 (demographics)     (browser, editable)       + job.json     (real dimensions)
                              ↓
                    dieline SVG + PDF at true size, for print approval
```

Four box sizes, a flavour range, one brand — and the brand is a file, so it
can be yours. No build step, no package manager, no network. Open the HTML
file, run the Python.

---

## Run it

**The studio app** — open `app/daybreak-studio.html` in any browser. It works
from `file://` and offline; there is no server and no bundler.

0. **Brand** — Daybreak Mills is the built-in default, not the only option.
   Name (the wordmark), tagline, back-panel title, palette (ink, paper,
   board), display and body typefaces — a font installed on the machine or a
   TTF / OTF / WOFF file that travels inside the brand file — the flavour
   table (name, what it is, field / deep / accent / type colours, its claim),
   the occasion claims the brief falls back to, and brand slogans for the ads.
   Add or remove flavours (1–8). Every flavour names an **archetype** — plain
   flake, chocolate, fruit, honey, frosted, bran — which is what the brief
   engine scores, so a custom range still gets a reasoned recommendation.
   *Save brand file* / *Load brand file* / *Reset to Daybreak Mills*. The
   fronts of the whole range redraw live as you type.
1. **Assets** — sketch or import the logo, the character and a bowl per
   flavour. Brush, eraser, fill, left–right mirror, undo, on a transparent
   1024² canvas per slot; or drop in any image — a photo or JPEG included —
   and the background colour is sampled from the corners and knocked out
   (tolerance slider), trimmed to content and fitted. Every stroke commits to
   its slot, and the *On the box* panel shows the front with it in place.
   *Download* writes PNGs named to the `assets/brand/` convention. A folder of
   ready-made files still loads from the Brief tab.
   **Dieline art** slots (one per size) take a whole net designed outside on
   the dieline kit — a Photoshop, Illustrator or InDesign export of the same
   square — and use it as the texture, either *replacing* the studio's layout
   or *overlaying* it. Kept at its own resolution up to 4096.
   The front panel sits beside the canvas with three **zones** on it — logo,
   character, bowl. Drag one to move it, drag its corner to resize it; the
   sketch canvas takes the zone's shape so a drawing that fills the canvas
   fills the zone edge to edge. Zones are stored as fractions of the front
   panel, so they carry across box sizes, ride along in `job.json` and the
   asset pack, and *Reset zones* returns to the brief's rule.
2. **Brief** — set audience, household size, channel, positioning, occasion. It
   scores those into a pack size and a flavour and shows every point of
   reasoning. Press *Generate artwork from brief*. The brief places the logo on
   the chips, the character on front and back, and the bowl for the flavour it
   chose (see `assets/brand/README.md` for the filename convention).
3. **Artwork** — the net is already laid out. Drop images onto any panel, drag
   them, retype the copy, move the layout sliders.
4. **3D Proof** — WebGL, textured through the same dieline UVs Blender uses.
   The **Show** pickers switch between any flavour and size without touching
   the brief, or put every flavour of a size — or the whole 4 × 6 matrix — on
   the stage at once, laid out the way Blender will build them. Double-click a
   box in a grid to focus it; *Use this box for export* promotes a preview to
   the brief's overrides.
5. **Export** — texture + `job.json` for Blender; SVG + PDF for print. Or
   **Export the range**: every flavour from this brief (or the full 4 × 6
   matrix) as one zip. The strip at the bottom of the tab shows all six front
   panels side by side.
   **Dieline kit** — one zip with all four sizes as square templates in
   texture space at the chosen resolution: an SVG with `BOARD`, `ART` and
   `GUIDES` layers for Illustrator / InDesign, a transparent guides PNG for
   Photoshop, a reference render of the brief's layout, `dieline_kit.json`
   with every panel in px and mm, and a README with the round trip. Design on
   it, export the same square, load it under Assets → Dieline art.
6. **Ads** — the carton posed in an ad. Four poses (front, three-quarter,
   tilted, trio of three flavours) × three formats (1:1 feed, 9:16 story,
   16:9 banner) × one or all six flavours, each with a slogan drawn at random
   from a pool the brief chooses (`EAT MORE`, `MORNINGS, SORTED`, `START
   RIGHT` …), the pack claim as a sub-line, and the logo at the bottom. The
   set shows as a contact sheet on the page; download any ad as PNG, the whole
   set as a zip (with `ads.json` and the contact sheet), or the contact sheet
   alone. *Shuffle* re-rolls the slogans.

**Projects** in the header opens the project gallery. Create, rename or duplicate
projects, save named checkpoints, and restore earlier work. The Studio saves the
active project in this browser as you edit, including embedded assets and view
settings. The save indicator distinguishes unsaved, saving, saved and failed
states. Switching projects waits for pending imports and edits to finish.

Your previous autosaved session migrates into **Recovered session** on first
launch; its original storage entry remains as a migration backup. **Import
session as project** on the Brief tab creates a separate project, and **Save
session file** downloads a portable backup. **New session** no longer clears
work; its replacement opens Projects.

Restoring a checkpoint or the previous autosave first saves a checkpoint of the
current work. If two tabs edit the same project, the stale tab saves its edits as
a **recovered copy**, preserving both versions. Storage failures keep the last
committed revision intact and show a backup reminder. Browser storage is local
to the browser/profile and may depend on the file location; download backups
before clearing browser data, moving the app, or changing machines. Checkpoints
also live in that browser. A session backup carries the active design, not its
checkpoint history. Close old Studio tabs before upgrading project storage.

**The Blender side** — put the exported texture and `job.json` in `jobs/`, then:

```bash
blender --background --python blender/daybreak_pipeline.py -- \
    --jobs jobs \
    --hdri assets/kloofendal_48d_partly_cloudy_puresky_4k.hdr \
    --save daybreak_lineup.blend \
    --render
```

It builds one carton per job, lined up and framed. `--hero` frames a single box
close. Without `--hdri` it falls back to a Blender built-in world.

**Install it once and forget it (macOS):**

```bash
python3 tools/install.py             # or double-click run-install.command
```

Two things, per-user, no sudo. The bridge becomes a **login service**
(launchd, restarted if it dies), so the Deploy panel is green whenever you're
logged in. And a tiny **`Daybreak Bridge.app`** is registered for the
`daybreak://` link, so if the bridge is ever down, the Deploy button opens
`daybreak://start` and macOS starts it for you — the browser asks "Open Daybreak
Bridge?" the first time; tick *always allow*. That is the only way a web page
can start a program: it can't launch anything, but it can open a URL and the
OS can route that URL to an app. `--status` and `--uninstall` do what they say.

**Or start everything at once:**

```bash
python3 tools/start.py               # or double-click run-all.command on macOS
```

Starts the bridge in the background, launches your chosen Blender (on the last
lineup you built, with the MCP server started if that add-on is installed), and
opens the studio in your browser. `python3 tools/start.py --stop` ends the
bridge; Blender is a normal app, close it like one.

**Or just the bridge.** Start it once and leave it:

```bash
python3 tools/bridge.py              # or double-click run-bridge.command on macOS
```

The Export tab's **Deploy to Blender** panel goes green, lists every Blender
on the machine with its version (pick one — it's remembered in
`daybreak.config.json`), and the button sends your choice straight through —
**this box**, **all 6 flavours of this size**, or the **full 4 × 6 matrix**
(24 boxes, ~3 s on Blender 5.1) — saved into `jobs/`, built by that Blender,
opened in the GUI, render shown back in the studio. The picker defaults to
whatever the 3D Proof tab was showing. The bridge also runs the folder watcher, so dropped files and
downloads still get picked up.

**Or just the watcher**, no button:

```bash
python3 tools/watch_jobs.py          # or double-click run-watcher.command on macOS
```

It finds Blender on its own, watches `jobs/` **and** `~/Downloads`, and builds
each job the moment its export finishes. Export from the browser and a render
appears — no moving files, no terminal.

A texture is only picked up once its PNG is complete: the watcher checks both
that the file size has settled and that the PNG carries its terminating `IEND`
chunk, because size-stability alone cannot tell a finished download from a
stalled one. Built jobs are recorded in `jobs/.processed.json`, so restarting
does not rebuild everything, but re-exporting the same job does.

The build always runs headless — you don't see a Blender window. Pass `--open`
and each finished `.blend` is opened in the Blender GUI once its render is done.

A range zip is extracted into `jobs/<name>/` and built as **one scene**, every
flavour side by side — flavours across, sizes back to front for the matrix.
With `--open` that lineup is what opens.

`jobs/status.html` is rewritten after every build. Open it in a browser and
leave it; it refreshes itself and shows each build with its render.

`--mode lineup` rebuilds one scene holding every job instead of a render each.
`--dry-run` prints the command without running it. `--once` processes what is
already there and exits.

**Regenerate the blank templates** (only needed if a box size changes):

```bash
python3 tools/make_dielines.py       # needs Pillow
```

**Cut a release:**

```bash
python3 tools/release.py --bump minor    # or patch / major
```

Bumps `VERSION` and the app's inlined `APP_VERSION` together, opens a dated
section in `CHANGELOG.md`, runs the verifier, and writes
`dist/daybreak-mills-v<version>.zip`. Every exported `job.json` carries
`generator_version`, so a render can always be traced to the build that made it.

**Update the checkout to the newest release:**

```bash
python3 tools/update.py                 # or --check to just look
```

Finds the newest `../releases/daybreak-mills-v*.zip` and extracts it over this
folder. Files you edited by hand are detected (they differ from both the
incoming and the previous release) and backed up to `_backup/<version>/` first;
the update stops unless `--force`. A dirty git tree is treated the same way.

**Verify everything still agrees** — run this before you commit:

```bash
python3 tools/verify_geometry.py     # stdlib only
```

---

## The one invariant

The dieline — the unfolded net that says where each panel sits in UV space — is
computed **independently in four places**:

| File | Language | Function |
|---|---|---|
| `app/daybreak-studio.html` | JavaScript | `geom()` |
| `tools/make_dielines.py` | Python | `dieline_uvs()` |
| `blender/cereal_box_generator.py` | Python | `build_box_mesh()` |
| `blender/daybreak_pipeline.py` | Python | `build_box_mesh()` |

If any one drifts, artwork lands misaligned on the carton, and **you will not
see it until it reaches a press.** So three guards exist:

- `app/daybreak-studio.html` runs a UV self-test at load and logs the result to
  the browser console.
- `blender/daybreak_pipeline.py` compares its mesh against the `dieline_uv`
  block in every job file and **refuses to build** past `1e-4` drift.
- `tools/verify_geometry.py` checks everything reachable without Blender or a
  browser, and exits non-zero on drift. Current worst across the repo: `4.7e-07`.

Measured agreement between the browser and Blender on real jobs: `2.2e-08` to
`4.3e-08`.

**Do not edit any dieline formula without running `verify_geometry.py`.**

---

## Layout

```
VERSION · CHANGELOG.md   semver; VERSION is the single source of truth
spec/boxes.json          sizes, flavours, dieline formulas, type and FDA specs
app/                     the browser studio, one self-contained HTML file
blender/                 daybreak_pipeline.py (jobs → cartons)
                         cereal_box_generator.py (scene from scratch, no jobs)
                         startup_hook.py (runs inside the GUI at launch)
tools/                   make_dielines.py, verify_geometry.py, watch_jobs.py,
                         bridge.py, start.py, install.py, release.py, update.py
run-install.command      double-click once: bridge as a login service + daybreak:// link (macOS)
run-all.command          double-click: bridge + Blender GUI + studio (macOS)
run-bridge.command       double-click: bridge + watcher (macOS)
run-watcher.command      double-click: watcher only (macOS)
daybreak.config.json     your chosen Blender (created by the studio dropdown; gitignored)
templates/               blank labelled dielines, SVG + PNG, one pair per size
docs/design-system.html  the brand and layout system
jobs/                    exported jobs; the pipeline reads this folder
assets/brand/            logo, character, bowls — matched by filename
assets/                  HDRIs (not committed — see below)
```

## Box sizes

Real dimensions used by the major US brands, height × width × depth:

| | inches | cm | Front panel @ 4096 | DPI |
|---|---|---|---|---|
| Regular ~12 oz | 12 × 7.75 × 2.5 | 30.5 × 19.7 × 6.4 | 1548 × 2397 | 200 |
| Family ~18 oz | 13 × 7.75 × 3 | 33 × 19.7 × 7.6 | 1476 × 2476 | 191 |
| Mega ~27 oz | 13.5 × 9.5 × 3.15 | 34.3 × 24.1 × 8 | 1538 × 2185 | **162** |
| Mini | 6.5 × 4 × 1.5 | 16.5 × 10.2 × 3.8 | 1489 × 2420 | 372 |

All four share one square canvas, so a bigger carton gets *less* resolution.
4096 is fine for renders. For press, export at 8192 — Mega especially.

## Two UV maps

Every box mesh carries both:

- **`CubeProject`** — box projection. Even texel density, but front and back
  share the same UV region by design. Use it for tiling materials like kraft.
- **`Dieline`** — every face its own non-overlapping island, laid out as a real
  carton net. **This is the one artwork goes through**, and it is set
  `active_render`.

## Assets

The HDRI is not committed (20.7 MB). Fetch it into `assets/`:

```bash
curl -o assets/kloofendal_48d_partly_cloudy_puresky_4k.hdr \
  https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/kloofendal_48d_partly_cloudy_puresky_4k.hdr
```

CC0, from [Poly Haven](https://polyhaven.com/). Any outdoor `.hdr`/`.exr` works.
The pipeline finds the brightest pixel, inverts Blender's equirectangular
mapping and places a real sun lamp there, so EEVEE gets a crisp shadow instead
of the soft blob a world alone gives. On this HDRI it solves to 47.9° elevation
— and the file is named `kloofendal_48d`, which is a decent check that the maths
is right.

## Requirements

- **App**: any modern browser. No dependencies.
- **Blender scripts**: Blender 4.2–5.1. Both the legacy and 4.4+ slotted-action
  APIs are handled, and both EEVEE engine identifiers.
- **`make_dielines.py`**: Pillow.
- **`verify_geometry.py`**: stdlib only.

## Known gaps

- A flavour with no bowl in `assets/brand/` gets a dashed placeholder. Supply
  `bowl.png` as a generic fallback or one per flavour.
- `spec/boxes.json` exists but nothing reads it yet — the sizes and flavours are
  still duplicated across four files. See `PROMPT.md`, task 1.
- The nutrition panel is a drawn placeholder, not real typeset content.
- The watcher polls on a timer rather than using OS filesystem events. Fine at
  a 2 s interval; swap in `watchdog` if you want it instant.

## Licence

Daybreak Mills is a fictional brand invented for this system. The box dimensions
are public product measurements. The HDRI is CC0.


## Secure local bridge (1.14.1)

Restart an already-running bridge after this update. In Export, choose **Choose
pairing file**, then select `jobs/bridge-pairing.json` in this checkout. The bridge
creates that file at startup with owner-only permissions. Pairing is remembered
for the current browser tab; a new tab may need pairing again. Offline editing
and file exports work without pairing. The pairing key is excluded from Git and
release ZIPs; do not share it. To revoke it, stop the bridge, remove the pairing
file, restart and pair again.

The bridge accepts only loopback Host headers and local-file or non-browser
origins. A local-file origin alone grants no access: deployment, Blender
selection, history, render retrieval and detailed status require the pairing
key. Unpaired discovery returns only the bridge identity, version and pairing
requirement. Blender selections are limited to detected installs or the path
explicitly configured when launching the bridge.

Uploads are limited to 256 MiB, with 512 MiB expanded ZIP data, 129 entries,
64 jobs and 1 MiB per JSON file. Invalid paths, links, duplicate/unlisted files,
missing textures and incomplete PNGs are rejected before extraction. Folder
imports use the same archive checks. Each extraction uses a fresh directory;
bridge uploads use unique names outside the folder watcher's matching pattern.
These checks validate the package container, not print readiness or nutrition
content. Local users and deliberately imported files remain trusted inputs.

See `tests/README.md` for the repeatable Stage 1 checks and sample scenarios.

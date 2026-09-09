# Changelog

Versions follow semver. `VERSION` at the repo root is the single source of
truth; the app, the Python tools and every exported `job.json` carry it, and
`tools/verify_geometry.py` fails if the app's inlined copy drifts from it.

## 1.17.0 — 2026-09-09

- Replace back and side placeholder content with editable stories, ingredients, allergens and nutrition data.
- Add shared content and field-level flavour overrides, including deliberate blank values, saved with project history and recovery.
- Typeset content at physical sizes with wrapping, overflow indicators and missing-data checks; carry resolved content and checks into every exported job.
- Reserve space for the back character and add packaging-content browser regression coverage.

## 1.16.0 — 2026-09-09

- Add a unified workspace with persistent live box, six-panel selection, contextual controls and integrated brief, brand and asset editing.
- Add millimetre positioning, direct dragging, grid/edge snapping and image layer ordering, visibility and locks.
- Add project-scoped undo/redo for artwork, copy, brief, brand and asset edits; preserve image IDs and layer settings in sessions.
- Add workspace browser regression tests and document the Stage 3 controls.

## 1.15.0 — 2026-09-09

- Add named projects, a thumbnail gallery, duplication, named checkpoints and previous-autosave recovery.
- Migrate the legacy session without removing its backup; preserve conflicting tab edits as a recovered project.
- Flush pending imports and sketches before switching; report storage failures and preserve newer edits during saves.
- Document the six-stage roadmap and add project migration/recovery browser tests.

## 1.14.1 — 2026-09-09

- Secure local bridge pairing, restricted Blender selection and bounded archive validation for deployments and folder imports.
- Add bridge security tests and offline browser/session/export regression baseline.

## 1.14.0 — 2026-09-05

- **Your own brand.** A new first tab, *Brand*. Daybreak Mills becomes the
  built-in default (`DEFAULT_BRAND`) rather than a set of constants: name
  (the wordmark), tagline, back-panel title, palette (ink / paper / board),
  display and body typefaces — a font installed on the machine or a TTF /
  OTF / WOFF file that is embedded in the brand file and registered with
  `FontFace` — the flavour table with colours and a per-flavour claim, the
  occasion claims, and brand slogans that join every ad pool. Add or remove
  flavours (1–8). Save / load `<brand>_brand.json`; reset to Daybreak Mills.
  The whole range's fronts redraw live in the tab.
- **Archetypes.** The brief engine no longer scores flavour keys; each
  flavour declares an archetype (golden, cocoa, berry, honey, frosted, bran)
  and `recommend()` scores those, so a custom range — three flavours or
  eight, any names — still gets a reasoned pick. `claimFor()` uses the
  flavour's own claim and the brand's occasion claims.
- Everything derived from the brand is rebuilt by `applyBrand()`: the
  flavour selects, asset bowl slots, palette swatches, the header mark, the
  page title; wordmark and tagline in the artwork, SVG / PDF / kit titles,
  the ads' logo line and contact sheet all read `BRAND.name`.
- Pipeline `arrange()` takes its column order from `range.json`, so a custom
  brand's flavours line up in the order the studio shows them.
- The brand rides in the session and in `job.json` provenance via the
  flavour block.
- Fixed: `brandPreview()` called `withFlavour()` for every flavour without
  awaiting — the nested restores ran out of order and left the recommendation
  pointing at the last flavour. Awaited now (see the PROMPT.md constraint).


## 1.13.0 — 2026-09-05

- **Dieline kit.** Export tab: one zip with all four sizes as square templates
  in texture space at the chosen resolution — `dieline_<Size>_<px>.svg` with
  `BOARD` / `ART` / `GUIDES` layers (panels, 4 mm safe area, labels, title
  block) for Illustrator and InDesign, a transparent `_guides.png` for
  Photoshop, a `reference_<Size>_<flavour>.png` of the brief's own layout,
  `dieline_kit.json` (every panel in px and mm, the UV map, DPI), and a README
  with the round trip for each application.
- **Dieline art slots.** Assets tab: one slot per size takes the designed net
  back — a PNG of the same square — and `drawNet()` uses it as the texture,
  *replacing* the studio's layout or *overlaying* it (a sketch straight onto
  the slot defaults to overlay; an import defaults to replace). Kept at its
  own resolution up to 4096; knockout and trim are off for these slots since
  the board colour at the corners is part of the design. The sketch canvas
  shows that size's panel guides underneath. Round-trips through the session,
  the asset pack, the folder picker (`dieline_art_<size>.png`) and
  `job.json` (`dieline_art`).


## 1.12.0 — 2026-09-04

- **Sessions persist.** The whole working state — brief and overrides, typed
  copy, layout sliders, zones, sketched and imported assets, dropped images,
  3D proof and ad settings — is autosaved to IndexedDB about a second after
  any change and restored when the studio opens. Reopening after an update,
  a reload, or a second tab no longer starts from blank boxes. A pill in the
  header shows the last save. *Save session file* / *Load session file* on
  the Brief tab, and a two-click *New session* that clears everything.
- Deploy no longer fires `daybreak://start` while the bridge probe is still
  in flight in a fresh tab — it waits for the probe (well under a second)
  and only wakes the bridge if nothing answered, so a running bridge is never
  "woken" and macOS never asks "Open Daybreak Bridge?" for nothing.


## 1.11.0 — 2026-09-04

- **Ad generator** — a sixth tab. The carton is rendered by a second,
  transparent WebGL context and set into an ad: four poses (front,
  three-quarter, tilted with a roll, trio of the flavour and its two range
  neighbours) × three formats (1:1 1080², 9:16 1080×1920, 16:9 1920×1080) ×
  the brief's flavour or all six. Slogans come from a pool the brief selects
  by audience and occasion (kids get `EAT MORE`, seniors `SIMPLE. HONEST.
  GOOD.`, health `START RIGHT` …), random per ad, one for the set, or custom;
  the pack claim can ride under it; the logo (or wordmark) sits at the bottom
  with the flavour name. Background: flavour gradient, deep, or bone.
- The set shows as a contact sheet on the page with per-ad PNG download,
  click to open full size, *Download all as zip* (every PNG + `ads.json`
  manifest + `contact_sheet.png`), and *Contact sheet PNG* on its own.
  *Shuffle slogans* re-rolls with a new seed.
- Box shots are trimmed to their alpha bounds before composition so the
  carton fills its zone; ad shots render a touch brighter than the proof.
- WebGL setup refactored into `makeGLContext()` / `withGL()`; `drawBoxes()`
  is shared by the proof stage and `renderShot()`.


## 1.10.0 — 2026-09-04

- **Adjustable zones.** The Assets tab shows the front panel beside the
  sketch canvas with three zones on it — logo, character, bowl. Drag to move,
  drag the corner to resize, click one to edit its slot. Zones are stored as
  fractions of the front panel (`state.zones`), so they survive a change of
  box size, ride along in `job.json` and the asset pack, and *Reset zones*
  returns to the brief's rule. The sidebar reports each zone in mm.
- **The sketch canvas takes the zone's shape.** Long side 1024, the other by
  the zone's aspect, refitting anything already drawn when a zone is resized
  — so a drawing that fills the canvas fills the zone edge to edge. Imports,
  fill, mirror and undo all follow the canvas size.
- **No more bone chip.** The masthead is the logo if there is one, else the
  wordmark straight on the field, front and top flap. A logo zone dragged
  taller at the top pushes the flavour name down.
- Every asset now places through one `zoneRects()`; the drag preview renders
  the panel without the moving asset and composites it live.


## 1.9.0 — 2026-09-04

- **Asset designer.** A new first tab: sketch or import the logo, the
  character and a bowl per flavour before the brief runs. Brush, eraser,
  flood fill, left–right mirror (for mascots), undo, brand-palette swatches,
  on a transparent 1024² canvas per slot. Import any image: the background
  colour is sampled from the corners and knocked out with a tolerance slider
  and a soft edge, trimmed to content, fitted and scalable. Every stroke
  commits to the slot the brief places, and an *On the box* preview shows the
  front panel with it in place. PNG downloads follow the `assets/brand/`
  naming (`logo.png`, `character.png`, `bowl_<flavour>.png`), so they load
  straight back through the folder picker. Keyboard: B/E/F/M, [ ], ⌘Z.
- The folder picker and asset-pack save/load stay on the Brief tab; loading
  either refreshes the designer's canvases.
- Tabs renumbered: Assets · Brief · Artwork · 3D Proof · Export.


## 1.8.0 — 2026-09-04

- **Deploy the full matrix.** The Deploy panel has a *what* picker — this box,
  all six flavours of this size, or the full 4 × 6 matrix — and one button.
  It defaults to whatever the 3D Proof tab is showing, so "look at the grid,
  deploy the grid" is two clicks. 24 boxes built in 3.1 s on Blender 5.1.1.
  (The old button silently used the range selector further down the tab.)
- Pipeline camera climbs with grid depth: at the old product-shot height the
  Regular row hid Mega and Family completely in a matrix render. Now ~20°
  looking down for four rows, unchanged for a single row or a hero.
- `release.py` no longer packages ranges or deploys that landed in `jobs/`
  during testing — a test deploy once shipped 10 MB of textures.


## 1.7.0 — 2026-09-04

- **The Deploy button can start the bridge.** A web page cannot launch a
  program — that is a browser rule, not a gap in the code — but it can open a
  URL, and macOS routes a registered URL scheme to an app. `tools/install.py`
  (double-click `run-install.command`, once) builds `~/Applications/Daybreak
  Bridge.app`, registered for `daybreak://`, whose only job is to run
  `start.py --no-browser --no-blender`. When the studio finds no bridge, Deploy
  opens `daybreak://start`, waits up to 25 s for it to answer, then deploys as
  normal. The buttons are never disabled any more; their label says which
  path they'll take.
- **The bridge as a login service.** The same installer registers a launchd
  LaunchAgent (`com.daybreakmills.bridge`, RunAtLoad + KeepAlive) so the
  bridge is up whenever you're logged in and restarts if it dies. It stops
  any hand-started bridges first so the service gets the port. `--status`,
  `--uninstall`.
- `bridge.py` now writes its own `jobs/.bridge.pid`, whatever started it.


## 1.6.0 — 2026-09-04

- **The 3D Proof tab shows more than the brief's one box.** A *Show* group
  in its sidebar picks any flavour and any size to preview — without changing
  the brief or what gets exported — and *Use this box for export* promotes a
  preview to the brief's overrides when you do want it.
- **Grid modes.** *All six flavours · this size* and *Full matrix · 4 sizes ×
  6 flavours* put 6 or 24 cartons on the WebGL stage at once, in the same
  layout `arrange()` builds in Blender (flavours across, sizes back to front,
  tallest at the back, 0.30 m apart). Orbit and zoom work on the whole grid;
  double-click a box to focus it.
- Renderer: per-box textures and a per-draw offset; the matrix drops to 512 px
  textures so 24 boxes fit in VRAM. Textures are power-of-two only — WebGL 1
  renders a mipmapped NPOT texture black.
- The geometry table and the stage label follow whatever is previewed.

## 1.5.1 — 2026-09-04

- Fixed: the bridge insisted on port 8765 and died if it was taken. On the
  reference machine an unrelated local Python tool already owned it, so the
  studio's "Bridge not running" was really "someone else answered". The bridge
  now takes the first free port in 8765–8774 and records it in
  `jobs/.bridge.port`; the studio probes that range and accepts only a reply
  whose `/status` says `"bridge": "daybreak"`; `start.py` does the same.

## 1.5.0 — 2026-09-04

- **One command brings everything up.** `tools/start.py` (double-click
  `run-all.command`) starts the bridge in the background, launches your chosen
  Blender's GUI, and opens the studio in the browser. `--stop` ends the bridge.
- **`blender/startup_hook.py`** runs inside that Blender at launch: starts the
  MCP add-on's server if one is installed (so an assistant can reconnect), and
  opens the newest lineup from `jobs/renders/` so you land on the last build.
- Fixed: `blender_version()` was uncached and shelled out to `--version` on
  every status poll — 45 launches during one start-up in testing. Now cached
  per path.

## 1.4.1 — 2026-09-04

- `tools/update.py`: bring the IDE checkout up to the newest release zip in
  one command, safely. Detects files you edited locally (differs from both the
  incoming and the previous release) or a dirty git tree, backs them up to
  `_backup/<version>/`, and stops unless `--force`. Never touches `.vscode/`,
  `daybreak.config.json`, HDRIs, your jobs, or `_backup/`.

## 1.4.0 — 2026-09-04

- **Deploy to Blender.** `tools/bridge.py` is a local server (stdlib, loopback
  only) that runs the watcher and receives deploys from the studio. The Export
  tab's new panel shows whether it is running, lists every Blender install on
  the machine with its version, lets you choose one, and sends the range (or
  the current box) straight to it: saved into `jobs/`, built by the chosen
  Blender, opened in the GUI, render shown back in the studio. Without the
  bridge the panel says so and the file exports keep working.
- **Choose your Blender.** `daybreak.config.json` `{"blender": path}` beats
  auto-detection; set it from the studio dropdown, `POST /select`, or by hand.
  `--blender` on the command line beats both.
- A single deployed box gets hero framing; a range gets the lineup.
- Fixed: bridge listeners were registered before `$` existed (same class of
  bug as the 1.3.0 range button). A check now asserts no top-level `$()` call
  precedes its definition.

## 1.3.1 — 2026-09-04

- Fixed: the watcher chose Blender alphabetically, which on a machine with
  `Blender.app` (4.5 LTS), `Blender 2.app` (5.0) and `Blender 3.app` (5.1)
  picked the oldest. Installs are now ranked by real version — read from the
  bundle's `Info.plist` on macOS, else `--version` — and the chosen version is
  printed at start.
- Fixed: a range's render was written to `jobs/<range>/renders/` (that folder
  is `--jobs` for a range) but the watcher looked in `jobs/renders/`, so the
  status page showed "no render" for every range. The stub used in testing
  happened to write where the watcher expected, which hid it.

## 1.3.0 — 2026-09-04

- **The range.** One brief now produces every flavour. *Export the range* in
  the studio renders all six (or the full 4 × 6 matrix) from the same brief and
  layout — each with its own palette, claim and bowl — into one zip with a
  `range.json` manifest. Dependency-free ZIP writer inlined in the app.
- **Range preview strip** on the Export tab: all six front panels side by side.
- **Watcher accepts range zips.** Extracted into `jobs/<name>/` and built as
  one Blender lineup; `--open` opens that lineup. A zip is only touched once
  its end-of-central-directory record is present.
- **Pipeline arranges a range as a grid** — flavours across, sizes back to
  front, tallest at the back — ordered by the manifest, and frames the camera
  for the grid's depth as well as its width.
- **`jobs/status.html`**: a self-refreshing page the watcher rewrites after
  every build, showing each job or range with its brief and render. No server.
- Fixed: `withFlavour` restored state before an async callback finished, so a
  range's job files were all written for the last flavour. Now awaits.
- Fixed: the range button's listener was registered before `$` existed and
  killed the script at load.

## 1.2.0

- Brand assets, placed by the brief. A folder of `logo`, `character` and
  `bowl_<flavour>` images is matched by filename; the brief puts the logo on
  every bone chip, the character on front and back, and the bowl for whichever
  flavour it recommended. Asset pack save/load as one JSON.
- Front panel refactored around a single `frontLayout()` so the asset placer
  and the text pass cannot disagree about where the product zone is.
- `watch_jobs.py --open` saves a `.blend` per job and opens it in the Blender
  GUI after the headless render.
- `job.json` records which asset files were baked in.

## 1.1.0

- `tools/watch_jobs.py`: polls `jobs/` and `~/Downloads`, moves finished
  exports in, launches Blender headless. Blender is auto-detected by glob
  (never hardcoded — the reference install is `/Applications/Blender 3.app`).
- A texture is only picked up once its size has settled *and* its PNG `IEND`
  trailer is present; size alone could not distinguish a finished download
  from a stalled one.
- `run-watcher.command` double-click launcher for macOS.
- `PROMPT.md` and `CLAUDE.md` corrected to describe four surfaces, not three.

## 1.0.0

- `app/daybreak-studio.html`: brief engine, dieline compositor, WebGL proof,
  PNG / JSON / SVG / true-size PDF exporters. Single file, no dependencies.
- `blender/daybreak_pipeline.py`: jobs → cartons, art through the Dieline UV,
  HDRI with a sun lamp solved from the brightest pixel, framed camera.
- `blender/cereal_box_generator.py`: 4 sizes × 6 shaders from scratch.
- `tools/make_dielines.py`: labelled SVG + PNG templates, asserted against
  the UVs read back out of the `.blend`.
- `tools/verify_geometry.py`: cross-checks every dieline implementation.
- `spec/boxes.json`, `docs/design-system.html`.

# Handoff prompt

Paste the block below into Claude Code, Cursor, or any IDE agent, with this repo
open. It gives the agent the architecture, the invariant that matters, and a
prioritised backlog.

If you only want one task done, delete the rest of the backlog before pasting —
agents work better with a single clear target than a menu.

---

```
You are working on Daybreak Mills, a cereal packaging pipeline that runs from a
demographic creative brief to a rendered 3D carton and a print-ready dieline.
Read README.md and spec/boxes.json first.

## Architecture

Four surfaces, connected by two file formats.

  app/daybreak-studio.html    A single self-contained HTML file. Asset designer
                              (sketch/import per slot, corner-colour knockout),
                              brief engine, dieline artwork compositor (2D
                              canvas), WebGL 3D proof, exporters, and an ad
                              generator (poses × formats × flavours, slogans
                              from the brief, contact sheet, zip). No build step, no bundler,
                              no CDN, no framework. It must keep working when
                              opened directly from file:// with no network.

  blender/daybreak_pipeline.py  Reads jobs/*_job.json plus its texture PNG,
                              builds a carton at real dimensions, maps the art
                              through the Dieline UV, lights it with an HDRI,
                              frames a camera, renders.

  tools/make_dielines.py      Generates the blank labelled templates in
                              templates/ (SVG + PNG per box size).

  tools/bridge.py             Local HTTP server on 127.0.0.1, first free port in
                              8765-8774 (8765 was taken on the reference machine
                              by an unrelated tool). The studio probes the range
                              and trusts only a /status reply with
                              "bridge": "daybreak". It runs the
                              watcher in a thread and receives deploys from the
                              studio's "Deploy to Blender" button. CORS must
                              allow Origin "null" — that is what file:// sends.
                              Blender choice: daybreak.config.json, set by
                              POST /select. Never expose beyond loopback.

  tools/start.py              One-shot launcher: bridge in the background, the
                              chosen Blender GUI with blender/startup_hook.py,
                              the studio in a browser. --stop ends the bridge.
                              The hook starts any MCP add-on server it finds and
                              opens the newest lineup .blend.

  tools/install.py            macOS only. Installs bridge.py as a launchd
                              LaunchAgent (KeepAlive, runs at login) and builds
                              ~/Applications/Daybreak Bridge.app, registered for
                              the daybreak:// URL scheme, whose executable runs
                              start.py --no-browser --no-blender. The studio's
                              Deploy button opens daybreak://start when no
                              bridge answers, then polls for up to 25 s. This
                              is the only legitimate page -> process path: a
                              browser cannot spawn anything, but the OS routes
                              a registered scheme to an app. The scheme call
                              must happen synchronously inside the click.

  tools/watch_jobs.py         Polls jobs/ and ~/Downloads, and launches Blender
                              headless when a job's export finishes. This is
                              what makes the browser -> Blender handoff
                              automatic; a web page cannot write outside
                              downloads or start an application on its own.

  Assets: assets/brand/ holds logo, character and per-flavour bowls, matched
  by filename, plus dieline_art_<size>.png — a whole net designed outside on
  the dieline kit (square templates in texture space, exportKit() in the
  app) and applied in drawNet() as the texture, replacing or overlaying. They are baked into the exported texture, so Blender needs
  nothing extra; job.json lists which files were used, for provenance.

  Range: daybreak_range_*.zip / daybreak_matrix_*.zip from the studio hold N
  jobs plus range.json (order, sizes, flavours, brief). The watcher extracts a
  range into jobs/<name>/ and the pipeline builds that folder as one grid.
  The app's ZIP writer (makeZip) is hand-rolled, stored entries only.

  Formats: jobs/*_job.json is the browser → Blender contract. Its schema is
  visible in the sample jobs and in jobJSON() in the app.

## The invariant — read this before touching any geometry

The dieline is the unfolded net that says where each of the six panels sits in
UV space. It is computed INDEPENDENTLY in four places (listed in README.md).
If any one drifts, artwork lands misaligned on the carton and it is nearly
invisible until it reaches a printing press.

Guards that already exist, and that you must not weaken:
  - the app runs a UV self-test at load and logs to the console
  - daybreak_pipeline.py refuses to build past 1e-4 drift from the job file
  - tools/verify_geometry.py checks everything and exits non-zero on drift

After ANY change that touches box dimensions, UV maths, or panel layout:

    python3 tools/verify_geometry.py

It must exit 0. Current worst drift across the repo is 4.7e-07. Do not raise the
tolerance to make a failure go away — fix the drift.

## Constraints

  - The app stays a single file with zero dependencies. No React, no bundler, no
    CDN scripts. It is opened from file:// and often offline. If you genuinely
    need a library, inline it and say why in the commit.
  - Blender scripts must run on 4.2 through 5.1. Two compatibility traps are
    already handled and must stay handled: `action.fcurves` was replaced by
    slotted actions in 4.4+, and the EEVEE engine identifier differs between
    versions. Icon names also differ — an unknown icon raises inside a panel's
    draw and silently truncates the rest of that panel.
  - Real-world units throughout. Box meshes are built at true size so object
    scale stays 1.0; bevel widths and UV density then mean what they say.
  - Textures are square. The panel rectangles are positions inside that square,
    not a crop. Cropping to the net breaks UV alignment.
  - The watcher must never hand Blender a partly-written file. It requires BOTH
    that the file size has settled across two polls AND that the PNG carries its
    terminating IEND chunk. Size-stability alone cannot tell a finished download
    from a stalled one — that was a real bug, caught by feeding it a truncated
    PNG. Do not drop either half of that check.
  - In the app, every top-level `$("...")` listener registration must sit
    BELOW `const $ = ...` in the UI section. Two releases in a row shipped a
    listener above it; the TDZ throw at load leaves `$` uninitialised for the
    whole page and everything downstream silently fails.
  - withFlavour() in the app MUST await its callback. It swaps global state to
    render another flavour and restores it in finally; with an un-awaited async
    callback the restore ran early and every job in a range was written for the
    wrong flavour. Keep the await.
  - Never hardcode a Blender path, and never pick one by name. The reference
    machine has THREE: Blender.app (4.5 LTS), Blender 2.app (5.0), Blender 3.app
    (5.1). Alphabetical order picked the oldest. find_blender() ranks by real
    version via blender_version(); keep it that way.
  - Test stubs must mirror the real tool's OUTPUT PATHS, not just its exit code.
    A stub that wrote renders where the watcher expected hid a path bug that
    only appeared on the real pipeline.
  - WebGL textures in the app must be POWER-OF-TWO sizes. It is WebGL 1, and a
    mipmapped NPOT texture renders black with no error. 768 shipped once and
    every box in the range view came out black.
  - An element styled with an explicit `display` ignores the `hidden`
    attribute — the author rule beats the UA `[hidden]{display:none}`. Add an
    explicit `#id[hidden]{display:none}` beside it (see #ad-empty).
  - Everything brand-specific reads from BRAND (DEFAULT_BRAND is Daybreak
    Mills) and is derived by applyBrand(): FLAVOURS, NAVY/BONE/CARTON,
    FONT_DISPLAY/FONT_BODY, FLAV_SLUGS, AD_SLOTS, AD_PALETTE, the selects.
    Never hardcode a flavour KEY in scoring or claims — recommend() scores
    ARCHETYPES via addF()/byArchetype(), claimFor() reads the flavour's own
    claim and BRAND.claims. Never write "DAYBREAK MILLS" as a literal in
    artwork or exports; use BRAND.name. fitText()/ctxWidthFor() choose the
    display face for weight >= 800 and the body face otherwise via fontFor().
  - Asset placement goes through zoneRects() only. state.zones holds user
    overrides as FRACTIONS of the front panel (null = the brief's rule in
    frontLayout()); the Assets tab edits them, drawManagedAssets() and
    drawMasthead() read them, job.json carries them. Never place an asset
    from frontLayout() directly again — that is how the placer and the text
    pass drifted apart once. There is no bone chip any more: the masthead
    is the logo, or the wordmark straight on the field.
  - WebGL has TWO contexts: the proof stage (opaque) and the ad generator's
    offscreen one (alpha, preserveDrawingBuffer). makeGLContext() builds
    both from the same shaders; withGL(ctx, fn) swaps the module-level
    gl/prog/buffers for the duration of fn so makeTexture()/bind()/drawBoxes()
    need no context argument. Textures belong to the context that made them
    — never pass a proof texture to renderShot(). ADS.texCache is cleared by
    redraw() because the artwork changed.
  - The 3D proof grid (proofPlan() in the app) uses the same spacing and
    ordering as arrange() in daybreak_pipeline.py: flavours across in
    FLAVOUR_ORDER, sizes back to front in SIZE_ORDER, 0.30 m centre to centre.
    Change one and change the other, so the browser preview and the Blender
    lineup stay the same picture.

## Backlog, highest value first

1. COLLAPSE THE DUPLICATION. spec/boxes.json exists but nothing reads it. The
   four box sizes (and the default flavour table, now DEFAULT_BRAND in the
   app) are currently copy-pasted across
   app/daybreak-studio.html, blender/cereal_box_generator.py,
   blender/daybreak_pipeline.py and tools/make_dielines.py. Make the Python
   files load spec/boxes.json directly. For the app — which must stay one file
   with no fetch() — add a small build step in tools/ that inlines the spec into
   the HTML, and commit the generated file. Then extend verify_geometry.py to
   assert the inlined copy matches the spec.

2. PRODUCT SHOTS — MOSTLY DONE. Brand assets load from a folder or are drawn
   and imported in the Assets tab (the AD object and ad*() functions in the
   app; one 1024² canvas per slot, commits into state.assets on every stroke)
   and are placed by the brief: logo on every chip, character front and back,
   and the bowl for whichever flavour was chosen (assets/brand/README.md has
   the naming convention; addAssetFiles()/classifyAsset()/drawManagedAssets()).
   What is still missing: a procedural fallback that draws cereal pieces on
   canvas (rings, flakes, stars, clusters per flavour) for any flavour without a
   bowl file, so no export ever ships a dashed placeholder. Asset positions are
   also fixed rules — a drag handle on the bowl and character would help.

3. TYPESET NUTRITION PANEL. The right panel is a drawn placeholder. Make it real
   typeset content driven by per-flavour nutrition data added to spec/boxes.json,
   respecting the FDA point-size minimums already recorded there. Note the FDA
   does NOT mandate Helvetica — that is convention. What is regulated is the
   minimum sizes and a ban on decorative, script or stylised faces.

4a. AD GENERATOR — DONE in 1.11.0 (adsGenerate()/adsCompose()). Remaining:
   an animated version (the tilted pose swinging in, 3–5 s MP4/GIF via
   captureStream + MediaRecorder), copy variants per audience beyond the
   slogan pool, and a "hero shot" pose with the bowl asset composited large.

4. BATCH EXPORT — DONE in 1.3.0 (exportRange() in the app, process_range() in
   the watcher, arrange() in the pipeline). Remaining: a range across several
   BRIEFS rather than one brief across flavours, e.g. the same flavour for kids /
   families / seniors side by side.

5. SAVE AND LOAD SESSIONS — DONE in 1.12.0. sessionSnapshot()/sessionApply()
   in the app; autosaved to IndexedDB (key "current") 900 ms after any
   redraw()/runBrief(), restored at boot, plus JSON file save/load. Every new
   piece of state MUST be added to both functions or it silently stops
   surviving a reload — that is exactly the bug that motivated this.

6. BACK PANEL CONTENT. The back is ruled placeholder lines. Give it a real
   layout system — activity panel, story blocks, recipe — driven by the brief
   the same way the front is.

7. TESTS. There is no committed automated test of the app or the watcher.
   Playwright is the natural fit for the app: drive the brief, assert the
   recommendation for known inputs, export, and validate the emitted PDF and SVG
   parse and carry the right true size in mm. For the watcher, a stub `blender`
   on PATH plus fixture files covers it — assert a truncated PNG is refused, a
   complete one is built, and the ledger prevents a rebuild. Both were verified
   by hand during development but nothing is committed. The only automated check
   in the repo today is tools/verify_geometry.py, which is geometry-only.

8. WATCHER USES POLLING. tools/watch_jobs.py polls on a 2 s timer. Fine in
   practice, but `watchdog` would make it event-driven and instant. Low value,
   listed for completeness.

## Versioning

  VERSION at the root is the single source of truth (semver). Bump with
  `python3 tools/release.py --bump patch|minor|major` — it also rewrites the
  APP_VERSION constant in the app and opens a CHANGELOG.md section. Never edit
  either number by hand; verify_geometry.py fails if they disagree. Every
  exported job.json carries generator_version.

## Definition of done for any change

  - python3 tools/verify_geometry.py exits 0
  - app/daybreak-studio.html still opens from file:// offline with no console
    errors, and its UV self-test still logs "passed"
  - a job exported from the app still builds in Blender with the pipeline
    reporting UV drift below 1e-7
  - README.md updated if you changed behaviour, file layout or requirements
  - a CHANGELOG.md line under the current version describing the change
```

---

## Suggested first message after the block above

> Start with backlog item 1 only. Show me the plan before you edit anything.

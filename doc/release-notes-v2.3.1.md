# Moonshine V2.3.1 — Frame By Frame

This update improves free camera and colour editing, quiets a repeated ghost
message, and fixes a crash caused by loading savestates while Sunshine's
background video player is running.

## Free camera

- Choose **Practice > Free camera > Resume gameplay** to run the game at
  normal speed while keeping free camera On. Pause gameplay stops it again.
- Resume also works from Sunshine's normal pause screen. Active TAS
  recordings keep the frames spent running in free camera.
- Both sticks now follow all directions, including small angles between the
  main directions. A smooth response gives finer control near the centre.
- Diagonal movement stays within the selected speed. Movement speed and
  look sensitivity remain separate.
- Optional **Camera smoothing** eases movement and turning as you start,
  change direction and stop. Choose 0.1–1.5 seconds in 0.1-second steps;
  the default **Off** responds immediately.

## Colours

- The shared colour editor now uses **Hue, Saturation and Lightness (HSL)**
  for Mario, FLUDD, timers, inputs, menu colours and other editable overlays.
- Hue chooses the colour; Saturation adjusts its strength; Lightness runs
  from black to white. Hold **Y** for adjustments of one instead of four.
- Existing colours are kept. Original/Custom appearance, individual parts,
  Keep, Discard and Reset remain available.

## Fixes

- Restored Moonshine menu access, skins and display customisation on the
  A/B/C file-select screen when Intro Skip is enabled.
- Savestate loads preserve the background video player's live buffers rather
  than mixing an old saved frame with its current decoding work.
- **Ghost challenger ready** appears once for a retained challenger instead
  of appearing on every level reset.
- Fixed Windows folder handling in the automatic release packaging checks.

## One data folder

- Settings and practice files now live in **/Moonshine data**. The launcher
  moves existing Moonshine data there on first launch.
- Themes use `theme/`; ghosts, SD states, TAS projects, crash reports and
  backups each have their own folder. Settings are saved as `moonshine.ini`.
- Crash history keeps up to 16 recent reports, with matching files for each
  crash. Earlier reports are preserved during migration.
- The app stays in `apps/moonshine_launcher`. The optional flag background
  is included only in the Japanese download.

## Updating

The **ENGLISH-MENUS** download supports **US, PAL and JP Sunshine**,
with English Moonshine menus in every region. The **JAPANESE-MENUS**
launcher also supports all three regions: its launcher is Japanese, its JP
Moonshine menus are Japanese, and its US/PAL Moonshine menus are English.
The **JAPANESE-MENUS** Dolphin download is for JP Sunshine only.

Replace the Moonshine app files using your chosen download.
Keep your settings, layout, theme, records, ghosts, achievements and playlists.
Use the launcher and mod files from the same download.

Make new savestates and TAS projects for this build. Keep older states and
projects with their matching version. The SD file menus still require the Wii
launcher; Dolphin uses the matching BPS patch for your own clean ISO.

See [the English guide](guide-en.md) or [日本語ガイド](guide-ja.md) for controls.

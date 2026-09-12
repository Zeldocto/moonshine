# Moonshine — a Super Mario Sunshine practice mod

**V2.3.1 — Frame By Frame** improves free camera with optional smoothing,
adds HSL colour controls and fixes savestate and file-select issues.
Settings and practice files now live together in `/Moonshine data`.
See the [English guide](doc/guide-en.md), [日本語ガイド](doc/guide-ja.md),
and [release notes](doc/release-notes-v2.3.1.md).

It implements most of the [GCT generator](https://gct.zint.ch/) practice codes, adds emulator-like savestates to console (Wii through Nintendont), and more. It supports JP 1.0, US, and PAL versions. Vibe coded software, use at your own risk.

<p align="center">
  <a href="doc/showcase.webp">
    <img src="doc/showcase.webp" alt="Moonshine menus and practice features">
  </a>
</p>

Features:
- Three compressed savestate slots, with named SD states on Wii.
- Frame advance, free camera and TAS projects with a Beginning and two checkpoints.
- Virtually all gecko codes integrated into the main launcher.
    - Integrated Timer, Metadata, Input display, Level select, Warp wheel and much more.
- In-game settings menu configuration for codes, persistent and stored on SD card (wii) / slot B memory card (emulator).
- Configurable button binds.
- Configurable GUI elements (text, position, color, size for timer, metadata display, pattern selector, vanilla HUD elements etc.)
- A brand new integrated IL system.
    - Saves your PB per level.
    - Plays you a little victory fanfare when you PB.
    - Has Any% plaza segments built in Faithfully to how they appear in the run.
    - In the future you will be able to toggle between profiles for categories. I.e 'Any%', '120', '96', ETC.
    - IL menu functions as built in warp list.
- Automatic memory card encoding based on version launched.
- And much more.

> [!WARNING]
> While the mod will generally boot with the GCT generator practice codes installed, and supports Gecko codes in principle, we strongly advise against loading the mod with Gecko codes enabled, as they will either break or be broken by Moonshine's features. For example, 'Level Select' is known to cause Moonshine's instant restart to break in unpredictable/nondeterministic ways.

## Installation

### Console (wii)

Choose `Moonshine_ENGLISH-MENUS_Launcher_V2.3.1_US-PAL-JP.zip` for
**English Moonshine menus on US, PAL or JP Sunshine**. The separate
`Moonshine_JAPANESE-MENUS_Launcher_V2.3.1_US-PAL-JP.zip` selects the
Japanese launcher and Japanese Moonshine menus when playing JP Sunshine.
Both downloads support all three game regions. Copy its `apps` folder to the SD root, so the launcher is at
`/apps/moonshine_launcher/boot.dol`. It lets you select JP, US or PAL Sunshine
from SD, USB or a real disc, and configure Nintendont options such as
progressive scan and the retail PAL language.

The English download keeps Moonshine menus English in every game region.
The Japanese download provides Japanese launcher menus and Japanese Moonshine
menus for JP Sunshine; selecting US or PAL keeps the game-side Moonshine
menus English. Language belongs to the download, independently of the game
region you select.

Replace the app files when updating. If you still use `apps/susamune_launcher`,
rename it to `apps/moonshine_launcher` first to avoid a duplicate Homebrew
Channel entry. Keep your settings, records, ghosts, achievements and playlists.
On first launch, existing Moonshine files move into `/Moonshine data`.
Older states and TAS projects need their matching build; make fresh ones
for V2.3.1.

Put `background.png` and optional `bgm.mp3` in `/Moonshine data/theme`.
The launcher creates missing folders. The **日本語版** ZIP includes an optional
flag background at that location; skip it to keep your existing theme.
The English ZIP supplies no theme.

Settings and binds are stored per region in `/Moonshine data/moonshine.ini`, in `[settings_jp]` / `[binds_jp]` sections and their `us` / `pal` counterparts.

The data folder also contains `ghosts`, `states`, `tas`, `crashes` and `backups`.
See [the folder guide](doc/guide-en.md#your-data-folder) for file locations.

### Emulator

Choose `Moonshine_ENGLISH-MENUS_Dolphin_V2.3.1_US-PAL-JP.zip` for English
Moonshine menus on **US, PAL or JP**, or
`Moonshine_JAPANESE-MENUS_Dolphin_V2.3.1_JP.zip` for Japanese menus on JP.
Apply its matching BPS to a clean
ISO with a BPS patcher such as
[Floating IPS](https://github.com/Alcaro/Flips/releases). The patch verifies
the source image before writing the Moonshine ISO.

| Region | Patch | Clean CRC32 | Clean MD5 |
| --- | --- | --- | --- |
| JP 1.0 (`GMSJ01`) | `moonshine_jp.bps` | `C3B17583` | `3B07A4BB22DB926B177E207F9D7F0D87` |
| US (`GMSE01`) | `moonshine_us.bps` | `771AD977` | `0C6D2EDAE9FDF40DFC410FF1623E4119` |
| PAL (`GMSP01`) | `moonshine_pal.bps` | `4C1D3641` | `72C4860D8555D5E790628E348ABC244D` |

The Japanese Dolphin download contains `moonshine_jp_ja.bps` for JP Sunshine.
The English JP patch keeps Moonshine menus English. SD state and TAS file
menus require the Wii launcher; Dolphin still has the three memory slots.

> [!IMPORTANT]
> Saving and loading the goop with savestates is broken in Dolphin unless 'Texture Cache Accuracy' it set to Safe. You can find this option in the 'Hacks' tab of 'Graphics' in the game's config:
> ![dolphin texture cache setting](doc/texture_cache_setting.png)
> It says it degrades performance although on my machine it seems to run fine still. YMMV.

> [!IMPORTANT]
> For settings persistence to work, make sure you have a memory card in slot B.

## Credits

- https://gct.zint.ch/ and all its authors - Psychonauter, Noki Doki, sup39, Milk. 
    - Disassembled gecko codes were used to implement the practice features ported from these codes. 
    - Also used the assembly source at https://forgejo.sup39.dev/sms/supSMS-GeckoCode by sup39 as reference.
- https://github.com/DotKuribo/BetterSunshineEngine/
    - Used heavily as reference. Clang fork with CodeWarrior ABI support used to compile mod (toolchain/)
- https://github.com/DotKuribo/SunshineHeaderInterface
    - THANK YOU FOR WRITING THIS
- https://github.com/SuperrSonic/Better-Nintendont
    - Nintendont fork used as base for the launcher in this repo
- https://github.com/doldecomp/sms
    - fed to the LLMs to know how everything works

## FAQ (Frequently Anticipated Questions) 

### How do the savestates work? 

It exploits the fact that the Wii has a considerable amount of RAM free when running a Gamecube game through Nintendont, to snapshot more or less the entire state of the game. This lets you save and restore basically anywhere, any time within the same stage/area (including during a cutscene, shine get or death animation, etc.).

### Does it support Gamecube?

No.

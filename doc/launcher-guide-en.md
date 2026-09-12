# Moonshine Launcher guide - V2.3.1 Frame By Frame

## Getting started

Choose Version to match your Sunshine disc: JP, US or PAL. Choose Path, then your game image on SD or USB, or Disc Drive. Choose Launch Game.

Hold B while opening the launcher to cancel Auto Boot and return to its menu.

In the game, open the mod menu with Y + Start. This is the default; your own button binds stay as you set them.

Use L/R to change top-level tabs, the C-stick to move through rows, A to select, and B to go back.

Settings and binds are saved separately for JP, US and PAL. They belong to the device you opened the launcher from, even if your game is on another device.

## Where to find things

Quick: your Shined favourites. Newer named settings can be Shined too, including all four free-camera settings. Existing stars stay.

Practice: savestates, frame advance, free camera, TAS projects, RNG and gameplay options.

Runs: individual levels, playlists, timer and splits, and PB Safety.

Records: achievements and practice statistics. There is also a Records shortcut inside Runs.

Ghosts: record, save, race, watch and share ghosts.

Display: layout editors, HUD overlays, timers and Mario/FLUDD appearance.

System: button binds and a short in-game guide.

## Button binds

Open System > Button binds to change a shortcut. Follow the prompts to record your button combination.

On a Practice action, press X to change its shortcut without leaving that page.

Default savestate buttons: D-Left saves; D-Right loads. D-Down toggles practice pause; D-Up advances a frame.

These are defaults for new settings. Updating keeps your existing shortcuts.

Free camera, TAS project actions and the state-slot cycling shortcuts start unassigned.

Choose a Step shortcut that you can comfortably press while holding Mario's other buttons. Pause and Step accept held gameplay buttons.

## Save and load states

Open Practice > Savestates. There are three memory slots, shared between your saves.

Save to chooses the slot your Save shortcut writes into. Load from chooses the slot or SD file your Load shortcut restores.

The two choices are independent. Changing a choice does not save or load anything.

For example, Save to State 1 and Load from State 2 lets you replace State 1 while practising from State 2.

System > Button binds has separate cycle-save-slot and cycle-load-slot shortcuts. Both start unassigned. The older cycle-both-slots shortcut is still available.

You must be in the same level and episode to load a state. Nothing is deleted automatically if a new save cannot fit: all your previous states stay intact.

Hold your Load shortcut to keep gameplay still after loading. Release it to move. If practice pause was already on, it stays on after you release Load.

An intro finishes before the hold begins. Keep Load held to stop on Mario's first controllable frame, or release early to continue. A previous practice pause still takes effect when Mario can move.

Clear save slot asks before clearing the slot under Save to. Other slots are kept. Errors remain visible even if successful save/load messages are switched Off.

Memory states are lost when you close the game or reboot. Save a separate copy to SD if you want to keep one.

## Keep a state on SD

First make a memory savestate. Under Practice > Savestates, set Save to to that slot.

Open SD states > Save memory state to SD. Give it a name, then press Start to finish. X + Start cancels naming.

Wait until saving finishes before removing the storage device. Files live in /Moonshine data/states on the launcher's device.

To use a saved file after rebooting, launch the same mod build, game region and setup. Enter the same level and episode. A secret also needs the same parent episode.

Open SD states > Refresh / first page, then highlight your file.

Y selects the file for your usual Load shortcut. Close the menu and press Load. All three memory slots stay saved.

A imports it into the slot under Save to, after confirmation. Load from does not change; choose the imported slot there when you want to load it.

Start renames the file. X asks to delete it.

Loading an SD file reads it each time. Import a frequently used state into memory for faster repeated loads.

Large SD files can load with three full memory slots if one saved slot matches the current scene and setup. That slot is kept as a recovery point; all three slots stay saved.

If an SD read fails partway through, the game restores that recovery state and tells you its slot number. If there is no suitable recovery state and too little temporary space, loading is refused safely.

Make fresh SD states and TAS projects with this build. Keep old files with their matching older build. States are specific to their build and setup; use ghosts to share an attempt across game regions.

## Pause and frame advance

Open Practice > TAS projects for Pause / Resume and Advance one frame. D-Down toggles practice pause. D-Up pauses gameplay, then advances one frame with each further press. Select either row and press X to change its shortcut, or Z to clear it.

You can press Pause or Step during loading, an intro or a movie. Armed means it will pause as soon as you can control Mario. Intros and movies run in real time. Press Pause again to cancel.

While paused, the QFT stays still. Each Step advances it by one game frame. TAS appears beside the QFT for an assisted attempt. Restart the stage for a fresh, ordinary attempt.

Hold A, then press Step to jump on that frame. To press A again on a later frame, release A and press it again before stepping. Keeping A held counts as holding it continuously.

While paused, Advance wins over overlapping shortcuts, including B+D-Up. Hold A+B and press Advance for a jump-dive. Normal reset shortcuts still work outside practice pause.

The Pause or Step shortcut itself is kept away from Mario. After choosing Step or Resume in the menu, release A to continue.

Free camera must be Off to control Mario during a Step. For a spin, choose the next main-stick direction yourself before each Step.

The Sunshine timer and compact QFT use different decimal precision, so their last digits can look different even on the same frame.

## Free camera

Open Practice > Free camera and turn it On. This also pauses live gameplay.

Choose Resume gameplay here to run at normal speed while keeping free camera On. Pause gameplay stops it again. Camera controls do not move Mario.

Both sticks follow every direction. The smooth response gives slower movement near the centre and full speed at the edge.

Camera smoothing eases movement and turning when you press or release the sticks. Choose 0.1 to 1.5 seconds in 0.1-second steps. Longer times give slower starts and stops. Off is the default and responds immediately.

Main stick: move. C-stick: look. L/R analog pressure: move down/up. Hold X for a temporary speed boost.

Movement speed saves a speed from 0.25x to 4x. Look sensitivity separately changes C-stick turning speed from 0.25x to 4x. Reverse sideways changes main-stick left/right movement.

Hide all HUD hides game and Moonshine overlays while using free camera. You can still open the menu. Turn it or free camera Off to restore your overlays.

Recenter returns to the game's camera view. Turning free camera Off also restores that view and keeps gameplay paused or running as you had it.

Camera On means Mario input Off. Turn it Off before stepping a jump or spin.

Free camera also works in the normal Start pause and while watching ghosts. During Ghost Watch you can resume playback with free camera still On.

## TAS projects

Open Practice > TAS projects. Your recorded inputs, Beginning and two checkpoints stay together under one name.

1. Choose New TAS where you want to begin. Moonshine captures the Beginning and RNG automatically. Release A; gameplay stays paused.

2. Hold Mario's buttons and press Step to record one frame, or Resume to record normal play. Opening the menu pauses your work.

3. Open Checkpoints and Save Checkpoint 1 before a move you might want to retry. Later, Go to Checkpoint 1 returns there ready to edit. Step or Resume records a new continuation. Checkpoint 2 gives you another retry point.

4. Replay watches your inputs from the Beginning. B or Start stops playback. Continue stays paused until you Step or Resume.

5. Save TAS asks for a name the first time. Confirm with Start and wait for the saved message. It saves the full recording, Beginning and existing checkpoints. It does not make a new checkpoint or need another free memory slot. Later saves update the same TAS.

6. Use the same build, game version and setup, then Open TAS by name. A matching checkpoint or Beginning opens paused and keeps the later inputs for Replay. If no point matches your current area and episode, the recording opens without moving Mario. Return to its Beginning area before Replay.

Save Checkpoint keeps a retry point in memory. Save TAS keeps everything on SD, in /Moonshine data/tas. Only the SD save survives closing the game or rebooting. There is no need to import the Beginning and checkpoints separately.

TAS projects share the three memory slots with ordinary states. If an occupied ordinary state needs replacing, you choose which one or cancel. The TAS screen names its own Beginning and checkpoints for you.

Saving over a checkpoint asks first: A replaces it, B keeps it. This also applies to checkpoint shortcuts. Save TAS updates your named SD project directly.

Continue, Replay, Beginning and checkpoint actions have optional shortcuts. Select a row, then X to assign or Z to clear. They start unbound. The project name also shows recorded frames and the 4096-frame limit.

In Open TAS, Start renames the highlighted file. X asks to delete its SD copy. Memory checkpoints stay; save again to keep that work after closing the game.

Normal area changes keep the recording. Intro, fade, conversation and movie inputs are recorded too, including skips and FLUDD's movies. Loading waits use no input frames; ready intro and movie frames count toward the 4096-frame limit. A take holds 32 area/movie transitions. A reached limit or unsupported transition keeps the take for saving.

Your usual Close shortcut works inside Checkpoints and the other TAS pages. While assigning a new shortcut, the recorder owns those buttons. Finish or cancel the edit, release the buttons, then press Close again.

Other area means the checkpoint is still saved, but you must enter its matching area and episode to load it. Replay and Go to Beginning need the area and episode where the TAS began. They do not warp there automatically.

Go to Beginning, Go to Checkpoint and Open TAS leave you paused and ready to edit. Later inputs remain available for Replay until Step or Resume records the first new input. Save/Open alone does not shorten the recording. The SD copy stays until Save TAS replaces it.

After Stop or a completed Replay, use Continue when you want to record again. It stays paused while you arrange the next input; ordinary Steps do not silently edit a stopped take.

Replay is experimental. DESYNC fN marks the first frame that differs, but the remaining inputs keep playing. B or Start stops playback. Damaged files, incompatible settings and wrong-area state loads are still refused. Use an exported ghost to share a finished attempt.

TAS banner starts On. Find it in TAS projects or Display > Other HUD, or Shine it to Quick. Off hides the large progress/help banner. A small DESYNC warning remains during a mismatched replay. f0 means the starting state differed.

An early or late arrival at the expected loading zone warns and keeps playing the remaining inputs in order. Checkpoint editing may be unavailable while the current area differs from that point in the recording. Save TAS still keeps the whole take. Return to an existing compatible checkpoint to edit. An unexpected destination is still refused.

## Save, race and watch ghosts

Open Ghosts to manage tracks. Save latest ghost creates a new personal file. An empty personal row also offers to save your latest ghost.

Personal and imported lists have pages. On the page row, use C-stick left/right, or A for the next page. Your library is limited by storage space, not a fixed number of files.

Choose a ghost to race it or watch it. Watch2 shows two tracks together. B or Start leaves Watch. Your full menu combo opens the menu without leaving Watch.

Pause, Step and free camera work while watching. The ghost stays still while paused.

Ghost Watch skips movies automatically and keeps the ghost's movement timing. Watch stays active when gameplay returns.

Ghosts > Ghost inputs turns on the ghost's controller display. Both ghosts shows two ghost controllers in Watch2, or your live input and the ghost's input while racing.

Older ghosts may have no recorded inputs to display. Ghost input displays teach you the movement; they do not control Mario.

Shared .smsghost files go in Moonshine data/ghosts/import. Import them from Ghosts. Your exported files appear in Moonshine data/ghosts/share.

## TAS ghosts and splits

Ghosts made using practice pause, Step, free camera or savestate loads are marked TAS. Time spent paused is omitted from the ghost.

Saving a state while recording a ghost keeps the recording from the level's start up to that point. Load it, try a new continuation, then finish and save the full-level TAS ghost.

A state made without an active ghost recording cannot invent the missing opening. Local input takes and ghost recordings are separate features.

TAS attempts cannot earn an ordinary PB. Restart the stage to begin a fresh attempt.

Runs > Timer and splits contains the Level splits display toggle. Display > Timer and splits has the same controls.

The new handmade checkpoints include the remaining level routes and Full Reds. A route can have up to eight segments, including its finish. Existing records are kept where the checkpoint timing still means the same thing.

In Runs > ILs, press Z on a supported row to choose its starting episode. Use C-stick Up/Down, A to keep or B to cancel. Your choice is saved separately for JP, US and PAL.

Episode choices cover the seven main-course 100-coin ILs, Gelato/Noki/Pianta Hidden, and the ten Full Reds ILs. Other IL starts stay fixed.

A practice pause in the previous stage should not disqualify a new clean IL or streak attempt. Rejected streak attempts briefly show the reason beside the counter.

Choose Off, PB, SOB or Ghost for comparison. SOB adds your best recorded segments together. Ghost compares against your selected race ghost.

The -- display means the required split time is missing or incompatible. Old ghost files and unsupported checkpoints cannot supply a comparison.

## Layout and HUD colours

Open Display > Layout editor. Choose Timers, Controller inputs, Metadata, Native HUD colours, Custom text, Practice feedback, or Menu and notifications.

In an editor, C-stick up/down chooses an option; left/right changes it. Start selects All or the next character/part. X + Start goes backwards.

Colours now use Hue, Saturation and Lightness (HSL). Hue chooses the colour from 0 to 359 degrees. Saturation goes from grey at 0 percent to full colour at 100. Lightness goes from black at 0 percent to white at 100. Your existing colours are kept. Hold Y to change by 1 instead of 4.

A keeps your edits, B discards them, and Z resets the selected option. Each asks for confirmation.

Timers > Sunshine timer edits position, size, opacity, brightness, the characters, TIME and the streak.

Appearance has Original and Custom choices for All or individual parts. Original keeps the game's shading and can still be tinted. Custom uses the chosen colours more directly. Editing HSL does not switch this timer's appearance mode.

Native HUD colours has separate controls for the normal health counter and underwater air meter.

Metadata has Field gap, Row gap, Fields per row and Value widths. Horizontal layout puts several fields on each row. Compact widths reduce empty space.

Rollout and dust controls are also beside their settings under HUD and displays > Movement feedback.

## Mario and FLUDD colours

Open Display > Appearance > Mario appearance, then Mario colours or FLUDD colours.

Mario parts: cap, shirt, overalls, gloves, shoes, sunglasses and Sunshine shirt.

FLUDD parts: body paint, metal, straps, tank, spray/hover/rocket/turbo nozzles, sprayed water and water highlights.

Use the same editor controls: Start selects a part; C-stick chooses and adjusts an option; hold Y for one-unit HSL changes.

Each part has its own Original/Custom choice. Here, editing HSL selects Custom. Choosing Original keeps your custom colour for later.

Keep the edits to save the colours for your next boot. Mario's skin stays unchanged. Sprayed water colours affect the stream, its mist and splashes, while sea water and Yoshi juice keep their own colours.

## Updates and help

Keep your settings, theme, records and ghosts when updating. Replace the packaged launcher files together; do not mix a new launcher with old mod files.

Put background.png and bgm.mp3 in /Moonshine data/theme. A launcher opened from USB uses that folder on USB.

On first launch, existing Moonshine files move into /Moonshine data. Keep your old data when updating; no manual rename is needed. Settings are in moonshine.ini; ghosts, states, tas, crashes and backups have their own folders. The app stays in apps/moonshine_launcher.

When reporting a problem, include the build checksum shown on the launcher's home screen, game region, level/episode and the steps that caused it.

The crashes folder keeps up to 16 recent reports. Send the matching text and .bin/.core files from the same report. Older reports are preserved during migration.

The longer guide-en.md is included beside boot.dol. This Guide works even without that file.

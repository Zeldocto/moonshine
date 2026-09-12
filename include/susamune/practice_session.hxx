#ifndef SUSAMUNE_PRACTICE_SESSION_HXX
#define SUSAMUNE_PRACTICE_SESSION_HXX

#include <Dolphin/types.h>
#include "susamune/practice_input.h"
#include "susamune/state_codec.hxx"
#include "susamune/tas_storage.h"

class Menu;

namespace PracticeSession {

enum { kSavestateSpanCount = 3 };
struct SavestateData {
    u32 version, flags, frames, settingsHash, startFingerprint, frameHash;
    u32 stateKey[2], originKey[2];
    u32 padHash, savedFingerprint, steps, releases;
    u32 transitionCount, transitionHash;
};
static_assert(sizeof(SavestateData) == 64, "practice state metadata size");
bool captureSavestate(SavestateData &out,
                      StateCodec::ReadSpan (&spans)[kSavestateSpanCount],
                      bool forceRng = false, bool omitTake = false);
bool savestateRestoreSpans(const SavestateData &data,
                          StateCodec::WriteSpan (&spans)[kSavestateSpanCount]);
bool restoreSavestate(const SavestateData &data, u32 slot, u32 generation);
// Own replay loads restore the start state without replacing the live take.
bool copySavestateBytes(void *destination, const void *source, u32 size);
bool projectSavestateMatches(const SavestateData &data, const u32 (&startKey)[2],
                             u32 role, u32 frames);
bool captureTake(SusamuneTasTakeData &out, StateCodec::ReadSpan (&spans)[2]);
bool restoreTake(const SusamuneTasTakeData &data, const void *frames, const void *transitions,
                 const SavestateData *loadedCheckpoint = nullptr);
bool takeBelongsTo(const u32 (&key)[2]);

void init();
void beforeStageSetup();
void afterStageSetup();
// Call before borrowing a director state; modal includes menu/wheel/editors.
void beforeDirect(bool modalOwnsInput);
bool freezeRequested();
bool ownsGameplayInput();
// Call after restoring the real director state, before gameplay observers.
void afterDirect(s32 appState, bool retailAdvanced);
// Service replay loads only after the existing GX completion barrier.
void afterDraw();
void onSavestateSaved(u32 slot, u32 generation);
void onSavestateCleared(u32 slot, u32 generation);
void onSavestateLoaded();
void armLoadHold(u16 buttons);
void cancelLoadHold();
bool holdingLoad();
void draw(Menu *menu);

bool requestPauseToggle(bool fromMenu = false);
bool requestStep(bool fromMenu = false);
bool requestFreeCameraToggle();
bool requestRecord();
bool requestRecordFrom(u32 slot, u32 generation);
bool requestBeginning();
void pauseEditing();
void pauseForCheckpoint();
bool attachedTo(const u32 (&key)[2]);
bool atRecordedScene();
bool checkpointReady();
bool projectAvailable();
u32 editRevision();
u32 takePosition();
bool requestContinue();
void stripShortcutButtons(u16 buttons);
bool requestPlayback();
void requestStop();
// Approved warps must release the hold so the retail transition can run.
void releaseForDeparture();
void recenterCamera();

// Timer presentation includes Load holds; menu actions use the manual toggle.
bool paused();
bool manualPaused();
bool nativePaused();
bool resumingNativePause();
// An armed hold survives loading and waits for Mario's controls to return.
bool pausePending();
bool freeCamera();
bool hideHud();
bool recording();
bool replaying();
// -1 means no warning; 0 identifies the loaded beginning.
s32 desyncFrame();
bool starting();
bool assisted();
bool available();
u32 stepCount();
u32 recordedFrames();
u32 replayFrame();
u32 capacityFrames();
const char *status();
// False for frozen/UI frames. Physical input remains separate from replay.
bool consumedInput(SusamunePracticeInput *out);

} // namespace PracticeSession

#endif

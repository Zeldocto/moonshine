#include "susamune/movement_timing_display.hxx"

#include "Dolphin/mem.h"
#include "SMS/Player/Mario.hxx"
#include "SMS/Player/MarioGamePad.hxx"
#include "SMS/System/MarDirector.hxx"
#include "susamune/creation_extras.hxx"
#include "susamune/menu.hxx"
#include "susamune/retail_input.hxx"
#include "susamune/settings.hxx"

extern "C" {
extern void *marioTimingVtable[] asm("__vt__6TMario");
void retailMarioTimingPerform(TMario *, u32, JDrama::TGraphics *)
    asm("perform__6TMarioFUlPQ26JDrama9TGraphics");
int retailSlipJumpMode(TMario *) asm("canSlipJump__6TMarioFv");
}

namespace MovementTimingDisplay {
namespace {

enum Result { EARLY, ON_TIME, LATE, CHECK_JUMP };

TMario *sMario;
TMarDirector *sDirector;
u32 sFrame, sLandingFrame, sJumpFrame;
float sResultY, sResultV;
u16 sResultFrames;
u8 sPopupFrames, sResult, sJumpPhase, sJumpResultFrames, sJumpPopupFrames;
bool sFrameActive, sLanded, sJumping, sHookReady;

bool gbEnabled() { return gSettings.getBool(SETTING_GB_SKIP_DISPLAY); }
bool jumpEnabled() { return (gSettings.get(SETTING_JUMP_DISPLAY) & 1) != 0; }

int buttslideStatus() {
    if (!(gSettings.get(SETTING_JUMP_DISPLAY) & 2)) return 0;
    TMario *mario = gpMarioOriginal;
    TMarDirector *director = RetailInput::stageDirector();
    if (!mario || mario != sMario || !director || director != sDirector ||
        !director->_260 || director->mCurState != TMarDirector::STATE_NORMAL ||
        *reinterpret_cast<void ***>(mario) != marioTimingVtable ||
        !mario->mFloorTriangle || (mario->mState & ~1u) != 0x00840452u) return 0;
    // Retail mode 1 also jumps through slippingBasic before the timed gate.
    const int mode = retailSlipJumpMode(mario);
    const bool ready = mode == 1 || (mode && mario->mSubStateTimer > 20 &&
        (mario->mState == 0x00840452u || !(mario->mActionState & 8)));
    return ready ? 2 : 1;
}

void reset() {
    sMario = gpMarioOriginal;
    sDirector = RetailInput::stageDirector();
    sJumping = false;
    sPopupFrames = 0;
    sJumpPopupFrames = 0;
    sFrameActive = false;
    sLanded = false;
}

bool grounded(u32 state) {
    return !(state & (TMario::STATE_AIRBORN | TMario::STATE_WATERBORN |
                      TMario::STATE_CUTSCENE));
}

void perform(TMario *mario, u32 cue, JDrama::TGraphics *graphics) {
    if (!sFrameActive || !(cue & 1) || mario != sMario ||
        mario != gpMarioOriginal ||
        *reinterpret_cast<void ***>(mario) != marioTimingVtable ||
        sDirector != RetailInput::stageDirector() || !sDirector ||
        !sDirector->_260 || sDirector->mCurState != TMarDirector::STATE_NORMAL) {
        retailMarioTimingPerform(mario, cue, graphics);
        return;
    }
    const u32 before = mario->mState;
    const float y = mario->mTranslation.y, v = mario->mSpeed.y;
    retailMarioTimingPerform(mario, cue, graphics);
    if (mario != gpMarioOriginal || sDirector != RetailInput::stageDirector()) {
        reset();
        return;
    }
    const u32 after = mario->mState;
    const TMarioControllerWork *const pad = mario->mControllerWork;
    const u32 pressed = pad ? pad->mFrameInput : 0;
    // Later quarterframes clear these edges. Observe immediately after the
    // retail movement call, while its original controller work is still live.
    if (gbEnabled() && sJumping && before == TMario::STATE_JUMP &&
        (pressed & TMarioControllerWork::B)) {
        const u32 frames = sFrame - sJumpFrame;
        sResultFrames = frames > 255 ? 255 : (u16)frames;
        sResultY = y;
        sResultV = v;
        sResult = frames < 9 ? EARLY : frames > 9 ? LATE :
            y >= 403.5f && y < 404.5f && v >= 5.95f && v < 6.05f ?
            ON_TIME : CHECK_JUMP;
        sPopupFrames = 90;
        sJumping = false;
    }
    if ((before & TMario::STATE_AIRBORN) && grounded(after)) {
        sLandingFrame = sFrame;
        sLanded = true;
    } else if (grounded(before) && (after & TMario::STATE_AIRBORN) &&
               (pressed & TMarioControllerWork::A)) {
        if (jumpEnabled() && sLanded) {
            const u32 frames = sFrame - sLandingFrame;
            sJumpResultFrames = frames > 6 ? 7 : frames ? (u8)frames : 1;
            sJumpPhase = sDirector->unk58 & 3;
            sJumpPopupFrames = 90;
        }
        sLanded = false;
        if (gbEnabled() && after == TMario::STATE_JUMP) {
            sJumping = true;
            sJumpFrame = sFrame;
        }
    } else if (!grounded(after)) {
        sLanded = false;
    }
    if (after != TMario::STATE_JUMP) sJumping = false;
}

}  // namespace

void onStageSetup() {
    reset();
    if (marioTimingVtable[8] == reinterpret_cast<void *>(&retailMarioTimingPerform)) {
        marioTimingVtable[8] = reinterpret_cast<void *>(&perform);
        DCStoreRange(marioTimingVtable + 8, sizeof(void *));
    }
    sHookReady = marioTimingVtable[8] == reinterpret_cast<void *>(&perform);
}

void onSavestateLoaded() { reset(); }

void beforeDirect(bool active) {
    if (gpMarioOriginal != sMario ||
        RetailInput::stageDirector() != sDirector) reset();
    if (!gbEnabled()) { sJumping = false; sPopupFrames = 0; }
    if (!jumpEnabled()) { sLanded = false; sJumpPopupFrames = 0; }
    sFrameActive = active && sHookReady && sMario && (gbEnabled() || jumpEnabled());
    if (!sFrameActive) return;
    ++sFrame;
    if (sPopupFrames) --sPopupFrames;
    if (sJumpPopupFrames) --sJumpPopupFrames;
}

void afterDirect(bool) { sFrameActive = false; }

static __attribute__((noinline)) void drawResult(Menu *menu, unsigned display,
                                                unsigned color, unsigned frames) {
    char text[80];
    formatPracticeDisplay(text, sizeof(text), display, color, frames,
                          sJumpPhase, sResultY, sResultV);
    gCreationExtras.drawPracticeDisplay(menu, text, display, color);
}

bool draw(Menu *menu) {
    if (!menu) return false;
    bool drawn = false;
    if (gbEnabled() && sPopupFrames) {
        drawResult(menu, 0, sResult, sResultFrames);
        drawn = true;
    }
    if (jumpEnabled() && sJumpPopupFrames) {
        drawResult(menu, 1, sJumpResultFrames - 1, sJumpResultFrames);
        drawn = true;
    }
    const int slide = buttslideStatus();
    if (slide) {
        drawResult(menu, 2, slide == 2 ? 0 : 1, 0);
        drawn = true;
    }
    return drawn;
}

}  // namespace MovementTimingDisplay

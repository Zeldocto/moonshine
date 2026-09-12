#include "susamune/retail_input.hxx"
#include "susamune/addresses.hxx"
#include "SMS/Manager/FlagManager.hxx"
#include "SMS/System/Application.hxx"
#include "SMS/System/MovieDirector.hxx"

namespace {
u32 directorType(bool allowFileSelect = false) {
    // Intro Skip constructs file select from GAME_INTRO without changing context.
    const bool fileSelect = allowFileSelect &&
        gpApplication.mContext == TApplication::CONTEXT_GAME_INTRO &&
        gpApplication.mCurrentScene.mAreaID == TGameSequence::AREA_OPTION;
    if (gpApplication.mContext != TApplication::CONTEXT_DIRECT_STAGE &&
        gpApplication.mContext != TApplication::CONTEXT_DIRECT_MOVIE &&
        !fileSelect) return 0;
    const u32 address = reinterpret_cast<u32>(gpApplication.mDirector);
    if ((address & 3) || address < 0x80000000u || address > 0x817ffd00u) return 0;
    return *reinterpret_cast<const u32 *>(address);
}
}

namespace RetailInput {
TMarDirector *stageDirector() {
    // Additional movies also run under the stage application context.
    return directorType(true) == SUSAMUNE_MEM1_ADDR(0x803b3ca0u, 0x803df0c8u, 0x803d68a8u)
        ? static_cast<TMarDirector *>(gpApplication.mDirector) : nullptr;
}

TMovieDirector *movieDirector() {
    return directorType() == SUSAMUNE_MEM1_ADDR(0x803b48d8u, 0x803dfa50u, 0x803d73b8u)
        ? static_cast<TMovieDirector *>(gpApplication.mDirector) : nullptr;
}

Context context() {
    const u32 pad = reinterpret_cast<u32>(gpApplication.mGamePads[0]);
    if ((pad & 3) || pad < 0x80000000u || pad > 0x817fff00u) return Unavailable;
    if (TMarDirector *stage = stageDirector())
        return stage->_260 || OSIsThreadTerminated(&gSetupThread) ? StageReady : StageLoading;
    if (TMovieDirector *movie = movieDirector()) {
        if (movie->mGamePad != gpApplication.mGamePads[0] || gpApplication.mCutSceneID > 19)
            return Unavailable;
        return (movie->mFlags & 1) || OSIsThreadTerminated(&gSetupThread) ? MovieReady : MovieLoading;
    }
    return Unavailable;
}

u32 sceneKey() {
    if (movieDirector()) return kMovieSceneTag | gpApplication.mCutSceneID;
    if (TMarDirector *stage = stageDirector()) {
        const u32 parent = TFlagManager::smInstance ?
            static_cast<u32>(TFlagManager::smInstance->getFlag(0x40003)) & 0xffffu : 0;
        return (static_cast<u32>(stage->mAreaID) << 24) |
               (static_cast<u32>(stage->mEpisodeID) << 16) | parent;
    }
    return 0xffffffffu;
}
}

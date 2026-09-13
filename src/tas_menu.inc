#pragma clang section text=".foxtrot.text" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"

class TasProjectTab final : public MenuTab {
public:
    TasProjectTab() : mPage(MAIN), mSel(0), mPending(0), mLength(0), mKeyPage(0),
        mCursor(0), mBinding(false), mUpper(false), mReplaceConfirm(false), mRename(false), mSlot(0), mGeneration(0), mId(0), mCrc(0) { mName[0] = 0; focus(); }
    const char *title() const override { return "TAS projects"; }
    const char *summary() const override { return "New, edit, replay and save a TAS with its checkpoints."; }
    void focus() override { mInput.begin(SUSAMUNE_BIND_BUTTON_MASK); }
    void showCheckpointPrompt() { mPage = CHECKPOINTS; mSel = 0; mReplaceConfirm = false; focus(); }
    bool grabsInput() const override {
        // The recorder owns every button, including its final commit frame.
        return mBinding || gBinds.recording() || mPage == NAME ||
            ((mPage != MAIN || TasProject::busy()) && !gBinds.wasPressedRaw(BIND_MENU_TOGGLE));
    }
    bool suppressesBinds() const override { return true; }
    bool favoriteHint() const override { return mPage == MAIN && mSel == 8; }
    void update(Menu *menu, TMarioGamePad *pad) override {
        const u32 nav = menu->navigationInput(pad);
        if (mBinding || gBinds.recording()) {
            if (nav & (TMarioGamePad::CSTICK_LEFT | TMarioGamePad::CSTICK_RIGHT |
                       TMarioGamePad::CSTICK_UP | TMarioGamePad::CSTICK_DOWN)) gBinds.cancelRecord();
            mBinding = gBinds.recording(); focus(); return;
        }
        const u16 pressed = mInput.update();
        if (TasProject::checkpointOverwritePending()) {
            if (pressed & (JUTGamePad::A | JUTGamePad::B)) {
                TasProject::confirmCheckpointOverwrite(!(pressed & JUTGamePad::B));
                focus();
            }
            return;
        }
        if (TasProject::replacementNeeded()) {
            if (pressed & JUTGamePad::B) {
                if (mReplaceConfirm) mReplaceConfirm = false;
                else TasProject::cancelReplacement();
                focus(); return;
            }
            if (mReplaceConfirm) {
                if (pressed & JUTGamePad::A) {
                    TasProject::replace(mSlot, mGeneration); mReplaceConfirm = false; focus();
                }
                return;
            }
            navigate(nav, 3);
            if ((pressed & JUTGamePad::A) && TasProject::replacementAllowed(mSel)) {
                mSlot = mSel; mGeneration = gSavestateMgr->slotInfo(mSlot).generation;
                mReplaceConfirm = true; focus();
            }
            return;
        }
        if (TasProject::busy()) {
            if (PracticeSession::starting() && TasProject::active()) { mPage = MAIN; menu->hide(); }
            return;
        }
        if (mPage == NAME) {
            if (pressed & JUTGamePad::START) {
                if (!(JUTGamePad::mPadStatus[0].mButton & JUTGamePad::X)) {
                    if (!mLength || !(mRename ? TasProject::rename(mId, mCrc, mName) : TasProject::save(mName))) {
                        menu->toast(TasProject::status()); return;
                    }
                }
                mPage = MAIN; mSel = 3; focus(); return;
            }
            if (pressed & JUTGamePad::Z) { mLength = 0; mName[0] = 0; return; }
            const u32 old = pad->mButtons.mRapidInput;
            pad->mButtons.mRapidInput = pressed;
            updateCreationKeyboardText(pad, mName, mLength, 31, mKeyPage, mUpper, mCursor);
            pad->mButtons.mRapidInput = old;
            return;
        }
        if (pressed & JUTGamePad::B) { mPage = MAIN; mSel = 0; focus(); return; }
        if (mPage == DELETE) {
            if (pressed & JUTGamePad::A) { TasProject::remove(mId, mCrc); mPage = MAIN; mSel = 4; focus(); }
            return;
        }
        if (mPage == CONFIRM) {
            navigate(nav, 3);
            if (!(pressed & JUTGamePad::A)) return;
            if (mSel == 0) {
                if (!TasProject::active()) {
                    menu->toast("Beginning was replaced; this TAS cannot be saved."); return;
                }
                if (TasProject::named()) { TasProject::save(TasProject::name()); mPage = MAIN; }
                else beginName();
            }
            else if (mSel == 1) {
                mPage = MAIN;
                if (mPending == 0) TasProject::newProject(); else TasProject::open(mId, mCrc);
            } else mPage = MAIN;
            mSel = 0; focus(); return;
        }
        if (mPage == FILES) {
            const auto &files = TasProject::catalog();
            const u32 count = TasProject::catalogReady() ? files.count : 0;
            navigate(nav, count + 2);
            if (!(pressed & (JUTGamePad::A | JUTGamePad::X | JUTGamePad::START))) return;
            if (mSel < count) {
                const auto &entry = files.entries[mSel]; mId = entry.id; mCrc = entry.headerCrc;
                memcpy(mName, entry.name, 32); mName[31] = 0;
                if (pressed & JUTGamePad::START) {
                    mRename = true; beginKeyboard(); focus(); return;
                }
                if (pressed & JUTGamePad::X) { mPage = DELETE; focus(); return; }
                if (TasProject::dirty()) { mPending = 1; mPage = CONFIRM; mSel = 2; }
                else { TasProject::open(mId, mCrc); mPage = MAIN; mSel = 0; }
            } else {
                if (!(pressed & JUTGamePad::A)) return;
                if (mSel == count + 1 && (!TasProject::catalogReady() || !files.more)) return;
                TasProject::refresh(mSel == count ? 0 : files.nextId); mSel = 0;
            }
            focus(); return;
        }
        if (mPage == CHECKPOINTS || mPage == MAIN) {
            navigate(nav, mPage == CHECKPOINTS ? 5 : 9);
            const BindId bind = selectedBind();
            if (bind != BIND_COUNT) {
                if (pressed & JUTGamePad::X) {
                    mBinding = true; gBinds.beginRecord(bind); focus(); return;
                }
                if (pressed & JUTGamePad::Z) { gBinds.set(bind, 0); focus(); return; }
            }
        }
        if (mPage == MAIN && mSel == 8) {
            if (pressed & JUTGamePad::X) {
                gSettings.toggleFavorite(SETTING_TAS_BANNER);
            } else if ((pressed & JUTGamePad::A) ||
                       (nav & (TMarioGamePad::CSTICK_LEFT | TMarioGamePad::CSTICK_RIGHT))) {
                gSettings.cycle(SETTING_TAS_BANNER, 1);
            }
            return;
        }
        if (mPage == CHECKPOINTS) {
            if (!(pressed & JUTGamePad::A)) return;
            if (mSel == 0) {
                if (TasProject::loadCheckpoint(0)) menu->hide();
            } else if (mSel & 1) TasProject::saveCheckpoint((mSel + 1) / 2);
            else TasProject::loadCheckpoint(mSel / 2);
            menu->toast(TasProject::status()); focus(); return;
        }
        if (!(pressed & JUTGamePad::A)) return;
        bool close = false;
        switch (mSel) {
        case 0:
            if (TasProject::dirty()) { mPage = CONFIRM; mPending = 0; mSel = 2; }
            else TasProject::newProject();
            break;
        case 1: close = TasProject::continueEditing(); break;
        case 2: close = TasProject::replay(); break;
        case 3:
            if (TasProject::named()) TasProject::save(TasProject::name());
            else beginName();
            break;
        case 4: mPage = FILES; mSel = 0; TasProject::refresh(); break;
        case 5: mPage = CHECKPOINTS; mSel = 0; break;
        case 6: close = PracticeSession::requestPauseToggle(true); break;
        case 7: close = PracticeSession::requestStep(true); break;
        }
        if (close) menu->hide();
        focus();
    }
    void draw(Menu *menu, int x, int y, int w, int h) override {
        if (mPage == NAME && !TasProject::busy()) {
            drawCreationKeyboard(menu, mRename ? "Rename TAS project" : "Name TAS project", mName[0] ? mName : "(enter a name)", mKeyPage, mUpper, mCursor);
            return;
        }
        char frames[32];
        snprintf(frames, sizeof(frames), "%lu / %lu frames", PracticeSession::recordedFrames(), PracticeSession::capacityFrames());
        const int framesWidth = Menu::textWidth(frames, 12);
        int nameSize = 17;
        while (nameSize > 9 && Menu::textWidth(TasProject::name(), nameSize) > w - framesWidth - 38) --nameSize;
        menu->drawText(TasProject::name(), x + 4, y, nameSize, nameSize, cTitle());
        menu->drawText(frames, x + w - framesWidth - 22, y + 3, 12, 12, cValue());
        if (TasProject::checkpointOverwritePending()) {
            char question[64];
            snprintf(question, sizeof(question), "Replace %s?", JapaneseUi::text(TasProject::roleName(TasProject::pendingCheckpointRole())));
            menu->drawText(question, x + 4, y + 44, 17, 17, cRowSel());
            menu->drawText("This replaces the checkpoint with your current position.", x + 4, y + 84, 13, 13, cRow());
            drawHelpLine(menu, x, y, w, h, "A: replace checkpoint   B: keep it"); return;
        }
        if (TasProject::replacementNeeded()) {
            menu->drawText(mReplaceConfirm ? "Replace this memory state?" : "Choose a memory state to replace", x + 4, y + 26, 15, 15, cRowSel());
            for (u32 slot = 0; slot < 3; ++slot) {
                const auto info = gSavestateMgr->slotInfo(slot);
                char label[64];
                snprintf(label, sizeof(label), "Memory %lu: area %u, episode %u", slot + 1, info.area, info.episode);
                drawValueRow(menu, x, y + 56 + slot * ROW_H, w, label,
                    TasProject::replacementAllowed(slot) ? "" : "In this TAS", slot == (mReplaceConfirm ? mSlot : mSel), false, true);
            }
            drawHelpLine(menu, x, y, w, h, mReplaceConfirm ? "A: replace this state   B: keep it" : "C-stick: choose   A: select   B: cancel");
            return;
        }
        if (TasProject::busy()) {
            menu->drawText(TasProject::status(), x + 4, y + 48, 13, 13, cRowSel());
            drawHelpLine(menu, x, y, w, h, "Please wait until the current action finishes."); return;
        }
        if (mPage == DELETE) {
            menu->drawText("Delete this TAS from SD?", x + 4, y + 32, 17, 17, cRowSel());
            menu->drawText(mName, x + 4, y + 68, 16, 16, cValue());
            menu->drawText("Its recording and checkpoint files will be deleted.", x + 4, y + 104, 13, 13, cRow());
            drawHelpLine(menu, x, y, w, h, "A: delete SD project   B: keep. Memory checkpoints stay."); return;
        }
        if (mPage == CONFIRM) {
            menu->drawText("This TAS has unsaved edits.", x + 4, y + 28, 15, 15, cRowSel());
            static const char *const rows[] = {"Save TAS and stay here", "Discard edits and continue", "Cancel"};
            for (int i = 0; i < 3; ++i) drawValueRow(menu, x, y + 58 + i * ROW_H, w, rows[i], "", i == mSel, false, true);
            drawHelpLine(menu, x, y, w, h, "Other memory states stay unless you choose to replace one."); return;
        }
        const int listY = y + 28, listH = h - 98;
        const auto &files = TasProject::catalog();
        const int fileCount = TasProject::catalogReady() ? files.count : 0;
        const int count = mPage == FILES ? fileCount + 2 : mPage == CHECKPOINTS ? 5 : 9;
        const int start = listScrollStart(mSel, count, listH / ROW_H), end = clampi(start + listH / ROW_H, 0, count);
        static const char *const mainRows[] = {"New TAS", "Continue", "Replay", "Save TAS", "Open TAS", "Checkpoints", "Pause / Resume", "Advance one frame", "TAS banner"};
        static const char *const checkpointRows[] = {"Go to Beginning", "Save Checkpoint 1", "Go to Checkpoint 1", "Save Checkpoint 2", "Go to Checkpoint 2"};
        for (int i = start; i < end; ++i) {
            char value[32] = {}; const char *label;
            if (mPage == FILES) label = i < fileCount ? files.entries[i].name : i == fileCount ? "Refresh" : "Next page";
            else if (mPage == CHECKPOINTS) {
                label = checkpointRows[i]; const auto cp = TasProject::checkpoint((i + 1) / 2);
                if (cp.present && !cp.loadableHere) memcpy(value, "Other area", 11);
                else if (cp.present) snprintf(value, sizeof(value), "%lu frames", cp.frames);
                else memcpy(value, "Empty", 6);
            } else label = mainRows[i];
            const bool banner = mPage == MAIN && i == 8;
            drawValueRow(menu, x, listY + (i - start) * ROW_H, w, label,
                banner ? gSettings.valueLabel(SETTING_TAS_BANNER) : value, i == mSel,
                banner && gSettings.favorite(SETTING_TAS_BANNER), true);
        }
        drawScrollHints(menu, x, listY, w, listH, start, end, count);
        const BindId bind = selectedBind();
        if (bind != BIND_COUNT) {
            char combo[kBindTextMax], line[kBindTextMax + 64];
            Binds::format(gBinds.recording() ? gBinds.recordPreview() : gBinds.get(bind), combo);
            snprintf(line, sizeof(line), gBinds.recording() ? "New bind: %s" : "Shortcut: %s   X: change   Z: clear", combo);
            menu->drawText(line, x + 4, y + h - 64, 12, 12, cValue());
        }
        menu->drawText(TasProject::status(), x + 4, y + h - 42, 11, 11, cValue());
        drawHelpLine(menu, x, y, w, h, gBinds.recording() ?
            "Hold new buttons, then release to save. C-stick cancels." : mPage == FILES ? "A: open   Start: rename   X: delete   B: back" :
            mPage == CHECKPOINTS ? "A: choose action   B: back. Beginning is kept for Replay." :
            mSel == 8 ? "Shows TAS progress below gameplay. Desync warnings stay visible." :
            "Continue stays paused. Hold Mario inputs, then use Step or Resume.");
    }
private:
    enum { MAIN, CHECKPOINTS, FILES, NAME, CONFIRM, DELETE };
    BindId selectedBind() const {
        static const BindId checkpointBinds[] = {BIND_TAS_BEGINNING, BIND_TAS_SAVE_CHECKPOINT1,
            BIND_TAS_LOAD_CHECKPOINT1, BIND_TAS_SAVE_CHECKPOINT2, BIND_TAS_LOAD_CHECKPOINT2};
        if (mPage == CHECKPOINTS && mSel < 5) return checkpointBinds[mSel];
        if (mPage == MAIN) switch (mSel) {
        case 1: return BIND_TAS_CONTINUE;
        case 2: return BIND_TAS_REPLAY;
        case 6: return BIND_PRACTICE_PAUSE;
        case 7: return BIND_PRACTICE_STEP;
        }
        return BIND_COUNT;
    }
    void navigate(u32 nav, int count) {
        if (nav & TMarioGamePad::CSTICK_UP) mSel = wrap(mSel - 1, count);
        if (nav & TMarioGamePad::CSTICK_DOWN) mSel = wrap(mSel + 1, count);
        if (mSel >= count) mSel = 0;
    }
    void beginName() {
        if (!TasProject::active()) return;
        const char *current = TasProject::name();
        mLength = clampi(strlen(current), 0, 31);
        memcpy(mName, current, mLength); mName[mLength] = 0;
        mRename = false; beginKeyboard();
    }
    void beginKeyboard() {
        mLength = strlen(mName);
        mPage = NAME; mKeyPage = mCursor = 0; mUpper = false;
    }
    u8 mPage, mSel, mPending, mLength, mKeyPage, mCursor;
    bool mBinding, mUpper, mReplaceConfirm, mRename;
    u32 mSlot, mGeneration, mId, mCrc;
    char mName[32];
    RawPromptInput mInput;
};
static_assert(sizeof(TasProjectTab) <= 80, "TAS menu storage");

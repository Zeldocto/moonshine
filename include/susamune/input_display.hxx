#ifndef _SUSAMUNE_INPUT_DISPLAY_HXX
#define _SUSAMUNE_INPUT_DISPLAY_HXX

#include <Dolphin/types.h>

#include "susamune/creation.hxx"
#include "susamune/susamune_cfg.h"
#include "susamune/practice_input.h"

class Menu;
class TMarioGamePad;
struct PADStatus;

struct InputDisplayLiveCfg {
    u8  startVisible;
    u8  valueMode;
    u8  valueSource;
    u8  valuePlacement;
};
static_assert(sizeof(InputDisplayLiveCfg) == 4,
              "input live config layout changed");

// Live controller overlay and its Creation editor. The visual configuration
// persists separately from Settings' byte-sized values in versioned payloads.
class InputDisplay {
public:
    enum { MENU_ROW_COUNT = 6 };

    void resetDefaults();
    void adopt(const volatile SusamuneInputDisplayCfg *src);
    void adoptStyle(const volatile SusamuneInputStyleCfg *src);
    void stageInto(volatile SusamuneInputDisplayCfg *dst) const;
    void stageStyleInto(volatile SusamuneInputStyleCfg *dst) const;

    void update();
    void draw(Menu *menu, bool force = false) const;
    void drawSnapshot(Menu *menu, const SusamunePracticeInput &input,
                      int x, int y, int scale, const char *label) const;

    bool dirty() const { return mDirty; }
    void clearDirty() { mDirty = false; }

    static int         menuRowCount() { return MENU_ROW_COUNT; }
    static const char *menuRowName(int row);
    const char        *menuRowValue(int row) const;
    void               adjustMenuRow(int row, int dir);

    void beginEditor();
    void updateEditor(TMarioGamePad *pad);
    void drawEditor(Menu *menu) const;
    bool editing() const { return mEditor.editing(); }
    bool visible() const { return mVisible; }

private:
    static CreationStyle defaultStyle();
    void resetLayout();
    void clampLayout();
    void markDirty();
    void drawState(Menu *menu, const PADStatus &raw, float mx, float my,
                   float cx, float cy, bool live) const;

    CreationStyle       mStyle;
    InputDisplayLiveCfg mCfg;
    u8 mColors[SUSAMUNE_INPUT_COLOR_COUNT][3];
    u8 mBackupRgb[SUSAMUNE_INPUT_COLOR_COUNT][3];
    CreationEditor mEditor;
    bool mVisible;
    bool mVisibleBeforeEdit;
    bool mDirty;
    bool mDirtyBeforeEdit;
};
static_assert(sizeof(InputDisplay) == 144, "input display state layout changed");

extern InputDisplay &gInputDisplay;

#endif  // _SUSAMUNE_INPUT_DISPLAY_HXX

#ifndef _SUSAMUNE_MOVEMENT_TIMING_DISPLAY_HXX
#define _SUSAMUNE_MOVEMENT_TIMING_DISPLAY_HXX

class Menu;

namespace MovementTimingDisplay {

void onStageSetup();
void onSavestateLoaded();
void beforeDirect(bool active);
void afterDirect(bool active);
// Shares the wallkick layout; true reserves it for this popup.
bool draw(Menu *menu);

}  // namespace MovementTimingDisplay

#endif

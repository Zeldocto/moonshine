#ifndef MOONSHINE_LAYOUT_PROFILES_HXX
#define MOONSHINE_LAYOUT_PROFILES_HXX

#include "susamune/layout_profile.h"
#include "susamune/settings.hxx"

namespace LayoutProfiles {
bool available();
bool busy();
bool present(u32 slot);
bool damaged(u32 slot);
const char *name(u32 slot);
u32 generation(u32 slot);
bool refresh();
bool save(u32 slot, const char *name, u32 expectedGeneration);
bool load(u32 slot);
const char *poll();
bool layoutSetting(SettingId id);
void capture(MoonshineLayoutPayload *out);
bool apply(const MoonshineLayoutPayload &layout);
}

#endif

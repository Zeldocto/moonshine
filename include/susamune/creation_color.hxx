#ifndef SUSAMUNE_CREATION_COLOR_HXX
#define SUSAMUNE_CREATION_COLOR_HXX

#include <Dolphin/types.h>

namespace CreationColor {

// Hundredths keep repeated edits independent of RGB byte rounding.
struct Hsl { u16 channel[3]; };

Hsl fromRgb(const u8 *rgb);
void toRgb(const Hsl &hsl, u8 *rgb);
u16 adjusted(u16 value, int channel, int delta);
u16 display(const Hsl &hsl, int channel);

}  // namespace CreationColor

#endif

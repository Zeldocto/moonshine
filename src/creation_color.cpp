#include "susamune/creation_color.hxx"

#if defined(__powerpc__)
#pragma clang section text=".foxtrot.text" rodata=".foxtrot.rodata" data=".foxtrot.data" bss=".foxtrot.bss"
#endif

namespace CreationColor {

Hsl fromRgb(const u8 *rgb) {
    int hi = rgb[0], lo = rgb[0];
    for (int i = 1; i < 3; i++) {
        if (rgb[i] > hi) hi = rgb[i];
        if (rgb[i] < lo) lo = rgb[i];
    }
    const int sum = hi + lo, range = hi - lo;
    Hsl hsl = {{0, 0, (u16)((sum * 10000 + 255) / 510)}};
    if (range) {
        const int span = sum < 255 ? sum : 510 - sum;
        hsl.channel[1] = (u16)((range * 10000 + span / 2) / span);
        int hue;
        if (hi == rgb[0]) hue = 6000 * (rgb[1] - rgb[2]) / range;
        else if (hi == rgb[1]) hue = 12000 + 6000 * (rgb[2] - rgb[0]) / range;
        else hue = 24000 + 6000 * (rgb[0] - rgb[1]) / range;
        hsl.channel[0] = (u16)(hue < 0 ? hue + 36000 : hue);
    }
    return hsl;
}

void toRgb(const Hsl &hsl, u8 *rgb) {
    const int hue = hsl.channel[0], light = hsl.channel[2];
    const int span = light < 5000 ? 2 * light : 20000 - 2 * light;
    const int chroma = (span * hsl.channel[1] + 5000) / 10000;
    const int sector = hue / 6000, part = hue % 6000;
    const int cross = (chroma * ((sector & 1) ? 6000 - part : part) + 3000) / 6000;
    const int base = light - chroma / 2;
    int value[3] = {0, 0, 0};
    switch (sector) {
        case 0: value[0] = chroma; value[1] = cross; break;
        case 1: value[0] = cross; value[1] = chroma; break;
        case 2: value[1] = chroma; value[2] = cross; break;
        case 3: value[1] = cross; value[2] = chroma; break;
        case 4: value[0] = cross; value[2] = chroma; break;
        default: value[0] = chroma; value[2] = cross; break;
    }
    for (int i = 0; i < 3; i++) rgb[i] = (u8)(((base + value[i]) * 255 + 5000) / 10000);
}

u16 adjusted(u16 value, int channel, int delta) {
    int next = value + delta * 100;
    if (channel == 0) {
        next %= 36000;
        if (next < 0) next += 36000;
    } else {
        if (next < 0) next = 0;
        if (next > 10000) next = 10000;
    }
    return (u16)next;
}

u16 display(const Hsl &hsl, int channel) {
    return (u16)((hsl.channel[channel] + (channel ? 50 : 0)) / 100);
}

}  // namespace CreationColor

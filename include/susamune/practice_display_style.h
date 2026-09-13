#ifndef SUSAMUNE_PRACTICE_DISPLAY_STYLE_H
#define SUSAMUNE_PRACTICE_DISPLAY_STYLE_H

#define SUSAMUNE_PRACTICE_DISPLAY_STYLE_MAGIC 0x53504453u
#define SUSAMUNE_PRACTICE_DISPLAY_STYLE_VERSION 1u
#define SUSAMUNE_PRACTICE_DISPLAY_COUNT 3u
#define SUSAMUNE_PRACTICE_DISPLAY_COLOR_COUNT 7u
#define SUSAMUNE_PRACTICE_DISPLAY_GB 0u
#define SUSAMUNE_PRACTICE_DISPLAY_JUMP 1u
#define SUSAMUNE_PRACTICE_DISPLAY_BUTTSLIDE 2u
#define SUSAMUNE_CFG_FLAG_PRACTICE_DISPLAY_STYLE 0x01000000u

struct SusamunePracticeDisplayStyle {
    unsigned short x, y;
    unsigned char scale, textA;
    unsigned char bgR, bgG, bgB, bgA;
    unsigned char textBrightness, padding;
    unsigned char rgb[SUSAMUNE_PRACTICE_DISPLAY_COLOR_COUNT][3];
    unsigned char reserved[3];
};

struct SusamunePracticeDisplayStyleCfg {
    unsigned int magic;
    unsigned short version, count;
    struct SusamunePracticeDisplayStyle entries[SUSAMUNE_PRACTICE_DISPLAY_COUNT];
    unsigned char reserved[12];
};

static inline void SusamunePracticeDisplayStyleInit(struct SusamunePracticeDisplayStyleCfg *cfg) {
    unsigned int i, color;
    unsigned char *bytes = (unsigned char *)cfg;
    for (i = 0; i < sizeof(*cfg); ++i) bytes[i] = 0;
    cfg->magic = SUSAMUNE_PRACTICE_DISPLAY_STYLE_MAGIC;
    cfg->version = SUSAMUNE_PRACTICE_DISPLAY_STYLE_VERSION;
    cfg->count = SUSAMUNE_PRACTICE_DISPLAY_COUNT;
    for (i = 0; i < SUSAMUNE_PRACTICE_DISPLAY_COUNT; ++i) {
        struct SusamunePracticeDisplayStyle *style = &cfg->entries[i];
        style->x = 300; style->y = 106;
        style->scale = 90; style->textA = 255;
        style->bgA = 185; style->textBrightness = 100; style->padding = 5;
        for (color = 0; color < sizeof(style->rgb); ++color)
            ((unsigned char *)style->rgb)[color] = 255;
    }
}

#define SUSAMUNE_PRACTICE_DISPLAY_STYLE_CFG_OFFSET 0x1980u
#define SUSAMUNE_PRACTICE_DISPLAY_STYLE_PHYS_PTR \
    ((struct SusamunePracticeDisplayStyleCfg *)(SUSAMUNE_MEM2_CFG_PHYS_BASE + SUSAMUNE_PRACTICE_DISPLAY_STYLE_CFG_OFFSET))
#if defined(IS_EMULATOR) && IS_EMULATOR
#define SUSAMUNE_PRACTICE_DISPLAY_STYLE_LIVE_PTR ((struct SusamunePracticeDisplayStyleCfg *)0x719000A0u)
#else
#define SUSAMUNE_PRACTICE_DISPLAY_STYLE_LIVE_PTR \
    ((struct SusamunePracticeDisplayStyleCfg *)(SUSAMUNE_MEM2_CFG_PPC_BASE + SUSAMUNE_PRACTICE_DISPLAY_STYLE_CFG_OFFSET))
#endif

typedef char susamune_practice_display_style_size[(sizeof(struct SusamunePracticeDisplayStyle) == 36) ? 1 : -1];
typedef char susamune_practice_display_style_cfg_size[(sizeof(struct SusamunePracticeDisplayStyleCfg) == 128) ? 1 : -1];
typedef char susamune_practice_display_rgb_offset[(__builtin_offsetof(struct SusamunePracticeDisplayStyle, rgb) == 12) ? 1 : -1];

#endif

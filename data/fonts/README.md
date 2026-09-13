The Japanese game UI uses a subset of Droid Sans Japanese, distributed under
the Apache License 2.0. `Droid-LICENSE.txt` is preserved from Dolphin's font
distribution. The input `droid-japanese.yay` is Dolphin's `Sys/GC/font_japanese.bin`;
the generator downsamples only the required glyphs to a 16-pixel, four-shade atlas.

The glyph order in `droid-japanese-codepoints.json` follows the Shift-JIS table in
[Dolphin's gc-font-tool.cpp](https://github.com/dolphin-emu/dolphin/blob/master/docs/gc-font-tool.cpp)
(Dolphin contributors and James Cowgill, GPL-2.0-or-later). The font file is from
[Dolphin's font resources](https://github.com/dolphin-emu/dolphin/tree/master/Data/Sys/GC).

Build the bounded catalogue and subset with `scripts/gen_japanese_ui.py`.
No retail Sunshine font or IPL image is included in the output.

`noto-japanese-supplement.json` adds only U+7DBA (綺), which Droid lacks, for
the runner-provided achievement title 綺麗な射線. It contains one precomputed
16×16 four-shade glyph from the existing
[Noto Sans Mono CJK JP variable font](https://github.com/notofonts/noto-cjk/blob/main/Sans/Variable/TTF/Mono/NotoSansMonoCJKjp-VF.ttf),
under the SIL Open Font License 1.1. The full license is preserved in
`launcher/loader/data/OFL-NotoSansCJK.txt` and shipped with both downloads.
The source SHA-256 is
`9a91b2f42ad958fd4295586809f85366f0afa020b85ac70b39916c25bc5cda15`.
The JSON records the rasterization parameters and GX I2 bytes, so ordinary
builds require neither the full font nor a new rasterizer dependency. Its
20-unit advance matches adjacent Droid kanji. The generator rejects any
supplement that would replace an existing Droid glyph.

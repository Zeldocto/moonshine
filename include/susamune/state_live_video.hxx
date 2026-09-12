#pragma once

namespace StateLiveVideo {
typedef __UINTPTR_TYPE__ Address;
struct Range { Address first, last; };

inline bool bufferRange(unsigned int open, unsigned int base, unsigned int work,
                        unsigned int bytes, Range &out) {
    out = {0, 0};
    if (!open) return true;
    if (open != 1 || base < 0x80000000u || base >= 0x81800000u ||
        (base & 31u) || bytes < 0x1000u || bytes > 0x81800000u - base ||
        work < base || work > base + bytes - 0x1000u ||
        base + bytes - work - 0x1000u >= 32u) return false;
    out = {base, base + bytes};
    return true;
}

inline bool readRingRange(unsigned int frameBytes, const Range &buffer, Range &out) {
    out = {0, 0};
    if (!frameBytes || frameBytes > 0x1800000u - 31u ||
        buffer.last < buffer.first + 0x1000u) return false;
    const unsigned int stride = (frameBytes + 31u) & ~31u;
    if (stride > (buffer.last - buffer.first - 0x1000u) / 10u) return false;
    out = {buffer.first, buffer.first + stride * 10u};
    return true;
}

typedef void (*Copy)(void *, void *, const void *, unsigned int);

inline void copyExcept(const Range &keep, void *context, void *destination,
                       const void *source, unsigned int size, Copy copy) {
    unsigned char *dst = static_cast<unsigned char *>(destination);
    const unsigned char *src = static_cast<const unsigned char *>(source);
    const Address first = reinterpret_cast<Address>(destination);
    if (keep.last <= first || keep.first >= first + size) {
        copy(context, destination, source, size);
        return;
    }
    if (first < keep.first) {
        const unsigned int count = keep.first - first;
        copy(context, dst, src, count);
    }
    if (keep.last < first + size) {
        const unsigned int offset = keep.last - first;
        copy(context, dst + offset, src + offset, size - offset);
    }
}
}

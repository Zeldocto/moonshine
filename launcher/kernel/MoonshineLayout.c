#include "MoonshineLayout.h"
#include "SusamuneCfg.h"
#include "string.h"
#include "ff_utf8.h"
#include "susamune/layout_profile.h"

extern u32 GAME_ID;
#ifndef LAYOUT_MAILBOX
#define LAYOUT_MAILBOX MOONSHINE_LAYOUT_PHYS_PTR
#endif

enum { IDLE, SCAN_OPEN, SCAN_READ, SCAN_CLOSE, SCAN_DONE,
       LOAD_OPEN, LOAD_READ, LOAD_CLOSE, SAVE_OPEN, SAVE_WRITE,
       SAVE_SYNC, SAVE_CLOSE, VERIFY_OPEN, VERIFY_READ, VERIFY_CLOSE };
static bool Enabled, Opened, InvalidCopy;
static u32 Phase, Ack, Request[8], ScanSlot, Copy, BestCopy, BestGeneration;
static u32 ExpectedChecksum, ExpectedGeneration, ScanError;
static FIL File;
static struct MoonshineLayoutFile Buffer;
static char Directory[64], Path[88];
static char BestName[MOONSHINE_LAYOUT_NAME_SIZE];
static const char *Region;

typedef char layout_path_fits[
    sizeof("1:/Moonshine data/layouts/layout_pal_5_a.bin") <= sizeof(Path) ? 1 : -1];

static void MakePath(u32 slot, u32 copy)
{
    _sprintf(Path, "%s/layout_%s_%u_%c.bin", Directory, Region, slot + 1u,
        copy ? 'b' : 'a');
}

static void Finish(u32 status)
{
    struct MoonshineLayoutMailbox *m = LAYOUT_MAILBOX;
    if (Opened) { f_close(&File); Opened = false; }
    Phase = IDLE;
    m->status = status;
    Ack = Request[2];
    // Publish the payload and all catalog lines before releasing ownership.
    sync_after_write(&m->ackSeq, sizeof(*m) - 32u);
    m->ackSeq = Ack;
    sync_after_write(&m->ackSeq, 32u);
}

static void PublishSlot(void)
{
    struct MoonshineLayoutMailbox *m = LAYOUT_MAILBOX;
    u32 bit = 1u << ScanSlot;
    m->presentMask &= ~bit;
    m->badMask &= ~bit;
    m->generations[ScanSlot] = BestGeneration;
    memcpy(m->names[ScanSlot], BestName, sizeof(BestName));
    if (BestGeneration) m->presentMask |= bit;
    else if (InvalidCopy || ScanError) m->badMask |= bit;
}

static void BeginScan(u32 slot)
{
    ScanSlot = slot;
    BestCopy = 1;
    BestGeneration = Copy = ScanError = 0;
    InvalidCopy = false;
    memset(BestName, 0, sizeof(BestName));
    Phase = SCAN_OPEN;
}

void MoonshineLayoutInit(void)
{
    struct MoonshineLayoutMailbox *m = LAYOUT_MAILBOX;
    FRESULT result;
    Enabled = Opened = false;
    Phase = Ack = 0;
    Region = GAME_ID == 0x474D534Au ? "jp" :
        GAME_ID == 0x474D5345u ? "us" : GAME_ID == 0x474D5350u ? "pal" : NULL;
    if (!Region) return;
    memset(m, 0, sizeof(*m));
    _sprintf(Directory, "%s" MOONSHINE_LAYOUT_DIRECTORY, SusamuneCfgStoragePrefix());
    if (SusamuneCfgStorageAvailable()) {
        result = f_mkdir_char(Directory);
        Enabled = result == FR_OK || result == FR_EXIST;
    }
    m->magic = MOONSHINE_LAYOUT_MAILBOX_MAGIC;
    m->version = MOONSHINE_LAYOUT_MAILBOX_VERSION;
    m->status = Enabled ? 0u : FR_NOT_READY;
    sync_after_write(m, sizeof(*m));
}

bool MoonshineLayoutPending(void)
{
    if (!Region) return false;
    sync_before_read(LAYOUT_MAILBOX, 32u);
    return Phase != IDLE || LAYOUT_MAILBOX->requestSeq != Ack;
}

void MoonshineLayoutService(void)
{
    struct MoonshineLayoutMailbox *m = LAYOUT_MAILBOX;
    FRESULT result;
    UINT done = 0;
    u32 status, generation;
    if (!Region) return;
    if (Phase == IDLE) {
        sync_before_read(m, 32u);
        memcpy(Request, m, sizeof(Request));
        if (Request[2] == Ack) return;
        if (!Enabled) { Finish(FR_NOT_READY); return; }
        if (Request[0] != MOONSHINE_LAYOUT_MAILBOX_MAGIC ||
            Request[1] != MOONSHINE_LAYOUT_MAILBOX_VERSION ||
            Request[3] < MOONSHINE_LAYOUT_LIST || Request[3] > MOONSHINE_LAYOUT_LOAD ||
            Request[6] || Request[7] ||
            (Request[3] != MOONSHINE_LAYOUT_LIST && Request[4] >= MOONSHINE_LAYOUT_COUNT)) {
            Finish(MOONSHINE_LAYOUT_ERROR_INVALID); return;
        }
        if (Request[3] != MOONSHINE_LAYOUT_LIST &&
            Request[5] != m->generations[Request[4]]) {
            Finish(MOONSHINE_LAYOUT_ERROR_CHANGED); return;
        }
        BeginScan(Request[3] == MOONSHINE_LAYOUT_LIST ? 0u : Request[4]);
        return;
    }
    switch (Phase) {
    case SCAN_OPEN:
        MakePath(ScanSlot, Copy);
        result = f_open_char(&File, Path, FA_READ);
        if (result == FR_NO_FILE || result == FR_NO_PATH) Phase = SCAN_CLOSE;
        else if (result != FR_OK) { ScanError = result; Phase = SCAN_CLOSE; }
        else { Opened = true; Phase = SCAN_READ; }
        return;
    case SCAN_READ:
        if (f_size(&File) != sizeof(Buffer)) InvalidCopy = true;
        else {
            result = f_read(&File, &Buffer, sizeof(Buffer), &done);
            if (result != FR_OK || done != sizeof(Buffer)) ScanError = result ? result : FR_DISK_ERR;
            else if (!MoonshineLayoutValid(&Buffer)) InvalidCopy = true;
            else if (!BestGeneration || (s32)(Buffer.generation - BestGeneration) > 0) {
                BestGeneration = Buffer.generation;
                BestCopy = Copy;
                memcpy(BestName, Buffer.name, sizeof(BestName));
            }
        }
        Phase = SCAN_CLOSE;
        return;
    case SCAN_CLOSE:
        if (Opened) {
            result = f_close(&File); Opened = false;
            if (result != FR_OK) ScanError = result;
        }
        Phase = ++Copy < 2u ? SCAN_OPEN : SCAN_DONE;
        return;
    case SCAN_DONE:
        PublishSlot();
        if (ScanError) { Finish(ScanError); return; }
        if (Request[3] == MOONSHINE_LAYOUT_LIST) {
            if (ScanSlot + 1u < MOONSHINE_LAYOUT_COUNT) BeginScan(ScanSlot + 1u);
            else Finish(0);
            return;
        }
        if (BestGeneration != Request[5]) { Finish(MOONSHINE_LAYOUT_ERROR_CHANGED); return; }
        if (Request[3] == MOONSHINE_LAYOUT_LOAD) {
            if (!BestGeneration) { Finish(InvalidCopy ? MOONSHINE_LAYOUT_ERROR_INVALID : MOONSHINE_LAYOUT_ERROR_EMPTY); return; }
            MakePath(ScanSlot, BestCopy);
            Phase = LOAD_OPEN;
            return;
        }
        sync_before_read(&m->file, sizeof(m->file));
        memcpy(&Buffer, &m->file, sizeof(Buffer));
        generation = BestGeneration + 1u;
        if (!generation) generation = 1u;
        if (!MoonshineLayoutValid(&Buffer) || Buffer.generation != generation) {
            Finish(MOONSHINE_LAYOUT_ERROR_INVALID); return;
        }
        Buffer.checksum = MoonshineLayoutChecksum(&Buffer);
        ExpectedChecksum = Buffer.checksum;
        ExpectedGeneration = Buffer.generation;
        MakePath(ScanSlot, BestCopy ^ 1u);
        Phase = SAVE_OPEN;
        return;
    case SAVE_OPEN:
        result = f_open_char(&File, Path, FA_WRITE | FA_CREATE_ALWAYS);
        if (result != FR_OK) { Finish(result); return; }
        Opened = true; Phase = SAVE_WRITE;
        return;
    case SAVE_WRITE:
        result = f_write(&File, &Buffer, sizeof(Buffer), &done);
        if (result != FR_OK || done != sizeof(Buffer)) { Finish(result ? result : FR_DISK_ERR); return; }
        Phase = SAVE_SYNC;
        return;
    case SAVE_SYNC:
        result = f_sync(&File);
        if (result != FR_OK) { Finish(result); return; }
        Phase = SAVE_CLOSE;
        return;
    case SAVE_CLOSE:
        result = f_close(&File); Opened = false;
        if (result != FR_OK) { Finish(result); return; }
        Phase = VERIFY_OPEN;
        return;
    case LOAD_OPEN:
    case VERIFY_OPEN:
        result = f_open_char(&File, Path, FA_READ);
        if (result != FR_OK) { Finish(result); return; }
        Opened = true;
        Phase = Phase == LOAD_OPEN ? LOAD_READ : VERIFY_READ;
        return;
    case LOAD_READ:
    case VERIFY_READ:
        if (f_size(&File) != sizeof(Buffer)) { Finish(MOONSHINE_LAYOUT_ERROR_INVALID); return; }
        result = f_read(&File, &Buffer, sizeof(Buffer), &done);
        if (result != FR_OK || done != sizeof(Buffer)) { Finish(result ? result : FR_DISK_ERR); return; }
        status = MoonshineLayoutValid(&Buffer) ? 0u : MOONSHINE_LAYOUT_ERROR_INVALID;
        generation = Phase == LOAD_READ ? BestGeneration : ExpectedGeneration;
        if (!status && (Buffer.generation != generation ||
            (Phase == VERIFY_READ && Buffer.checksum != ExpectedChecksum))) status = MOONSHINE_LAYOUT_ERROR_CHANGED;
        if (status) { Finish(status); return; }
        Phase = Phase == LOAD_READ ? LOAD_CLOSE : VERIFY_CLOSE;
        return;
    case LOAD_CLOSE:
    case VERIFY_CLOSE:
        result = f_close(&File); Opened = false;
        if (result != FR_OK) { Finish(result); return; }
        memcpy(&m->file, &Buffer, sizeof(Buffer));
        BestGeneration = Buffer.generation;
        memcpy(BestName, Buffer.name, sizeof(BestName));
        PublishSlot();
        Finish(0);
        return;
    default:
        Finish(MOONSHINE_LAYOUT_ERROR_INVALID);
    }
}

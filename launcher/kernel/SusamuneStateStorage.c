/* Heapless archive service. PPC owns pool/staging until the matching receipt. */
#include "SusamuneStateStorage.h"
#include "Config.h"
#include "SusamuneCfg.h"
#include "string.h"
#include "ff_utf8.h"
#include "susamune/state_storage.h"
#include "susamune/data_paths.h"
#include "susamune/mod_bin.h"

extern u32 GAME_ID;
#ifndef STATE_MAILBOX
#define STATE_MAILBOX ((struct SusamuneStateStorageMailbox *)SUSAMUNE_STATE_STORAGE_PHYS_BASE)
#define STATE_POOL ((u8 *)SUSAMUNE_MEM2_SNAPSHOT_PHYS_BASE)
#define STATE_POOL_EXTRA ((u8 *)SUSAMUNE_STATE_POOL_EXTRA_PHYS_BASE)
#define STATE_STAGING ((u8 *)NIN_MEM2_SEGABOOT_PHYS_BASE)
#endif

enum { IDLE, EXPORT_FIND, OPEN_FILE, HEADER_IO, METADATA_IO, PAYLOAD_IO,
       COMMIT_HEADER, SYNC_FILE, CLOSE_FILE, RENAME_FILE, CATALOG_NEXT, CATALOG_HEADER, MUTATE_FILE, PREPARED_REQUEST };
static bool Enabled, FileOpen, DirOpen;
static u32 Ack, Phase, FileId, Offset, PayloadCrc, ConfigId;
static struct SusamuneStateRequest Request;
static struct SusamuneStateArchiveHeader Header;
static FIL File;
static DIR Scan;
static char Directory[64], Path[96], Temporary[96];
typedef char StateNamePathsFit[
    sizeof("1:" MOONSHINE_DATA_ROOT MOONSHINE_TAS_DIR
           "/tas_4294967295/state_4294967295.name1.tmp") <= 72 ? 1 : -1];
typedef char StateDirectoriesFit[
    sizeof("1:" MOONSHINE_DATA_ROOT MOONSHINE_TAS_DIR "/tas_4294967295") <=
        sizeof(Directory) ? 1 : -1];
static u32 ScanId, ScanSize;
static char RequestName[SUSAMUNE_STATE_NAME_BYTES];
static struct SusamuneTasRequest TasContext;
static struct SusamuneTasManifest TasProject;

static u8 *PoolPiece(u32 offset, u32 *size)
{
    u32 available;
    u8 *result;
    if (offset < SUSAMUNE_STATE_POOL_SIZE) {
        available = SUSAMUNE_STATE_POOL_SIZE - offset;
        result = STATE_POOL + offset;
    } else {
        offset -= SUSAMUNE_STATE_POOL_SIZE;
        available = SUSAMUNE_STATE_POOL_EXTRA_SIZE - offset;
        result = STATE_POOL_EXTRA + offset;
    }
    if (*size > available) *size = available;
    return result;
}

static u32 BootConfigId(void)
{
    const u32 mask = NIN_CFG_CHEATS | NIN_CFG_DEBUGGER | NIN_CFG_DEBUGWAIT |
        NIN_CFG_MEMCARDEMU | NIN_CFG_FORCE_WIDE | NIN_CFG_FORCE_PROG |
        NIN_CFG_REMLIMIT | NIN_CFG_USB | NIN_CFG_MC_MULTI | NIN_CFG_NATIVE_SI |
        NIN_CFG_WIIU_WIDE | NIN_CFG_ARCADE_MODE | NIN_CFG_SKIP_IPL | NIN_CFG_MC_SLOTB;
    const u32 fields[] = {NIN_VERSION, NIN_CFG_VERSION, ncfg->Version, ncfg->Config & mask,
        ncfg->VideoMode, ncfg->Language, ncfg->MaxPads, ncfg->GameID, ncfg->MemCardBlocks,
        (u32)ncfg->VideoScale, (u32)ncfg->VideoOffset, (u32)ncfg->SramOffset,
        ncfg->SkipProgAsk, ncfg->CardDelay, GAME_ID, BI2region};
    u32 crc = SusamuneStateCrc(fields, sizeof(fields));
    return crc ? crc : 1u;
}

static void Paths(u32 id)
{
    _sprintf(Path, "%s/state_%08u.mss", Directory, id);
    _sprintf(Temporary, "%s/state_%08u.tmp", Directory, id);
}

static bool ReadNames(u32 id, u32 crc, struct SusamuneStateNameRecord *latest, u32 *copy)
{
    struct SusamuneStateNameRecord record;
    FIL file;
    char path[72];
    FRESULT result, closed;
    UINT done;
    u32 i, size;
    bool readable = true;
    memset(latest, 0, sizeof(*latest));
    *copy = 1;
    for (i = 0; i < 2; ++i) {
        _sprintf(path, "%s/state_%08u.name%u", Directory, id, i);
        result = f_open_char(&file, path, FA_READ);
        if (result == FR_NO_FILE) continue;
        if (result != FR_OK) { readable = false; continue; }
        size = f_size(&file);
        result = f_read(&file, &record, sizeof(record), &done);
        closed = f_close(&file);
        if (result != FR_OK || closed != FR_OK) { readable = false; continue; }
        if (done != sizeof(record) || size != sizeof(record)) continue;
        if (record.magic == SUSAMUNE_STATE_NAME_MAGIC && record.version > 1u) { readable = false; continue; }
        if (record.magic != SUSAMUNE_STATE_NAME_MAGIC || record.version != 1u ||
            record.archiveId != id || record.archiveChecksum != crc || !record.generation ||
            record.reserved[0] || record.reserved[1] || !SusamuneStateNameValid(record.name) ||
            !record.name[0] || record.checksum != SusamuneStateNameCrc(&record)) continue;
        if (record.generation == latest->generation && memcmp(&record, latest, sizeof(record))) readable = false;
        if (record.generation > latest->generation) { *latest = record; *copy = i; }
    }
    return readable;
}

static void EffectiveName(u32 id, char *name)
{
    struct SusamuneStateNameRecord record;
    u32 copy;
    memcpy(name, Header.name, SUSAMUNE_STATE_NAME_BYTES);
    ReadNames(id, Header.headerCrc, &record, &copy);
    if (record.generation) memcpy(name, record.name, SUSAMUNE_STATE_NAME_BYTES);
}

static u32 WriteName(void)
{
    struct SusamuneStateNameRecord record;
    FIL file;
    char path[72], temporary[72];
    u32 copy;
    UINT done = 0;
    FRESULT result, closed;
    if (!ReadNames(FileId, Header.headerCrc, &record, &copy)) return SUSAMUNE_STATE_IO_ERROR;
    if (record.generation == 0xFFFFFFFFu) return SUSAMUNE_STATE_FULL;
    record.magic = SUSAMUNE_STATE_NAME_MAGIC; record.version = 1;
    record.archiveId = FileId; record.archiveChecksum = Header.headerCrc;
    ++record.generation;
    memcpy(record.name, RequestName, sizeof(record.name));
    record.checksum = SusamuneStateNameCrc(&record);
    copy ^= 1u;
    _sprintf(path, "%s/state_%08u.name%u", Directory, FileId, copy);
    _sprintf(temporary, "%s/state_%08u.name%u.tmp", Directory, FileId, copy);
    result = f_open_char(&file, temporary, FA_WRITE | FA_CREATE_ALWAYS);
    if (result != FR_OK) return SUSAMUNE_STATE_IO_ERROR;
    result = f_write(&file, &record, sizeof(record), &done);
    if (result == FR_OK && done == sizeof(record)) result = f_sync(&file);
    closed = f_close(&file);
    if (result != FR_OK || done != sizeof(record) || closed != FR_OK) return SUSAMUNE_STATE_IO_ERROR;
    // The active name survives any failure while replacing the other generation.
    result = f_unlink_char(path);
    if (result != FR_OK && result != FR_NO_FILE) return SUSAMUNE_STATE_IO_ERROR;
    return f_rename_char(temporary, path) == FR_OK ? SUSAMUNE_STATE_OK : SUSAMUNE_STATE_IO_ERROR;
}

static u32 DeleteArchive(void)
{
    FIL file;
    char marker[72], name[72];
    FRESULT result, closed;
    UINT done = 0;
    u32 i;
    _sprintf(marker, "%s/state_%08u.used", Directory, FileId);
    result = f_open_char(&file, marker, FA_WRITE | FA_CREATE_ALWAYS);
    if (result != FR_OK) return SUSAMUNE_STATE_IO_ERROR;
    result = f_write(&file, &Header, sizeof(Header), &done);
    if (result == FR_OK && done == sizeof(Header)) result = f_sync(&file);
    closed = f_close(&file);
    if (result != FR_OK || done != sizeof(Header) || closed != FR_OK) return SUSAMUNE_STATE_IO_ERROR;
    // Reserve the numeric identity before removing its payload.
    if (f_unlink_char(Path) != FR_OK) return SUSAMUNE_STATE_IO_ERROR;
    for (i = 0; i < 2; ++i) {
        _sprintf(name, "%s/state_%08u.name%u", Directory, FileId, i);
        f_unlink_char(name);
        _sprintf(name, "%s/state_%08u.name%u.tmp", Directory, FileId, i);
        f_unlink_char(name);
    }
    return SUSAMUNE_STATE_OK;
}

static void Finish(u32 status)
{
    struct SusamuneStateStorageMailbox *m = STATE_MAILBOX;
    if (FileOpen) { if (f_close(&File) != FR_OK && status == SUSAMUNE_STATE_OK) status = SUSAMUNE_STATE_IO_ERROR; FileOpen = false; }
    if (DirOpen) { f_closedir(&Scan); DirOpen = false; }
    memset(&m->receipt, 0, sizeof(m->receipt));
    m->receipt.session = Request.session;
    m->receipt.command = Request.command;
    m->receipt.id = Request.id;
    m->receipt.seq = Request.seq;
    if (status == SUSAMUNE_STATE_OK && (Request.command == SUSAMUNE_STATE_CMD_TAS_READ ||
        Request.command == SUSAMUNE_STATE_CMD_TAS_COMMIT || Request.command == SUSAMUNE_STATE_CMD_TAS_RENAME)) {
        m->tasProject = TasProject;
        sync_after_write(&m->tasProject, sizeof(m->tasProject));
        m->receipt.headerCrc = TasProject.checksum;
    }
    if (status == SUSAMUNE_STATE_OK && (Request.command == SUSAMUNE_STATE_CMD_READ_WINDOW || Request.command == SUSAMUNE_STATE_CMD_IMPORT ||
        Request.command == SUSAMUNE_STATE_CMD_EXPORT || Request.command == SUSAMUNE_STATE_CMD_RENAME ||
        Request.command == SUSAMUNE_STATE_CMD_DELETE)) {
        m->header = Header;
        sync_after_write(&m->header, sizeof(m->header));
        if (Request.command == SUSAMUNE_STATE_CMD_READ_WINDOW || Request.command == SUSAMUNE_STATE_CMD_IMPORT || Request.command == SUSAMUNE_STATE_CMD_EXPORT)
            sync_after_write(m->metadata, Header.metadataSize);
        if (Request.command == SUSAMUNE_STATE_CMD_RENAME || Request.command == SUSAMUNE_STATE_CMD_DELETE)
            memcpy(m->resultName, RequestName, sizeof(m->resultName));
        else EffectiveName(FileId, m->resultName);
        sync_after_write(m->resultName, sizeof(m->resultName));
        m->receipt.metadataSize = Header.metadataSize;
        m->receipt.packedSize = Header.packedSize;
        m->receipt.headerCrc = Header.headerCrc;
        m->receipt.reserved = SusamuneStateCrc(m->resultName, sizeof(m->resultName));
        if (Request.command == SUSAMUNE_STATE_CMD_READ_WINDOW) {
            memset(&m->window, 0, sizeof(m->window));
            m->window.offset = Request.poolOffset;
            m->window.size = Offset;
            m->window.checksum = ~PayloadCrc;
            sync_after_write(&m->window, sizeof(m->window));
        }
    }
    sync_after_write(&m->receipt, sizeof(m->receipt));
    m->response.status = status;
    m->response.resultId = FileId;
    m->response.transferred = Offset;
    m->response.ackSeq = Ack = Request.seq;
    sync_after_write(&m->response, sizeof(m->response));
    Phase = IDLE;
}

void SusamuneStateStorageInit(void)
{
    struct SusamuneStateStorageMailbox *m = STATE_MAILBOX;
    FRESULT result;
    Enabled = FileOpen = DirOpen = false;
    Phase = Ack = 0;
    memset(&TasContext, 0, sizeof(TasContext));
    if (!SusamuneStateGameValid(GAME_ID)) return;
    memset(m, 0, sizeof(*m));
    ConfigId = BootConfigId();
    _sprintf(Directory, "%s" MOONSHINE_STATES_DIR, SusamuneCfgStoragePrefix());
    if (SusamuneCfgStorageAvailable()) {
        result = f_mkdir_char(Directory);
        Enabled = result == FR_OK || result == FR_EXIST;
    }
    m->response.magic = SUSAMUNE_STATE_STORAGE_MAGIC;
    m->response.version = SUSAMUNE_STATE_STORAGE_VERSION;
    m->response.available = Enabled;
    m->response.configId = ConfigId;
    m->response.status = Enabled ? SUSAMUNE_STATE_OK : SUSAMUNE_STATE_UNAVAILABLE;
    sync_after_write(m, sizeof(*m));
}

bool SusamuneStateStoragePending(void)
{
    if (!Enabled) return false;
    sync_before_read(&STATE_MAILBOX->request, sizeof(STATE_MAILBOX->request));
    return Phase != IDLE || STATE_MAILBOX->request.seq != Ack;
}

static bool ValidFileSize(u32 size)
{
    return size == sizeof(Header) + Header.metadataSize + Header.packedSize;
}

static u32 CatalogId(const WCHAR *name)
{
    const char prefix[] = "state_", suffix[] = ".mss";
    u32 i, id = 0;
    for (i = 0; i < 6; ++i) if (name[i] != (WCHAR)prefix[i]) return 0;
    for (i = 6; i < 14; ++i) {
        if (name[i] < '0' || name[i] > '9') return 0;
        id = id * 10u + name[i] - '0';
    }
    for (i = 0; i < sizeof(suffix); ++i) if (name[14 + i] != (WCHAR)suffix[i]) return 0;
    return id;
}

static void AddCatalog(void)
{
    struct SusamuneStateCatalog *c = &STATE_MAILBOX->catalog;
    struct SusamuneStateCatalogEntry entry;
    u32 at, i;
    if (!SusamuneStateHeaderValid(&Header) || !ValidFileSize(ScanSize)) return;
    memset(&entry, 0, sizeof(entry));
    entry.id = ScanId; entry.packedSize = Header.packedSize;
    entry.metadataSize = Header.metadataSize; entry.rawSize = Header.rawSize;
    entry.gameId = Header.gameId; entry.buildCrc = Header.buildCrc;
    entry.headerCrc = Header.headerCrc; entry.sceneKey = Header.sceneKey;
    EffectiveName(ScanId, entry.name);
    for (at = 0; at < c->count && c->entries[at].id < entry.id; ++at) {}
    if (c->count == SUSAMUNE_STATE_CATALOG_COUNT) c->more = 1;
    else ++c->count;
    if (at == SUSAMUNE_STATE_CATALOG_COUNT) return;
    for (i = c->count - 1; i > at; --i) c->entries[i] = c->entries[i - 1];
    c->entries[at] = entry;
}

#include "SusamuneTasStorage.inc"

void SusamuneStateStorageService(void)
{
    struct SusamuneStateStorageMailbox *m = STATE_MAILBOX;
    FRESULT result;
    FILINFO info;
    u32 amount, i;
    UINT done;
    u8 *bytes;
    if (!Enabled) return;
    sync_before_read(&m->request, sizeof(m->request));
    sync_before_read(&m->tasRequest, sizeof(m->tasRequest));
    if (Phase != IDLE && (memcmp(&Request, &m->request, sizeof(Request)) ||
        memcmp(&TasContext, &m->tasRequest, sizeof(TasContext)))) {
        Finish(SUSAMUNE_STATE_CANCELLED);
        return;
    }
    if (Phase >= TAS_PHASE_BASE) { TasService(); return; }
    if (Phase == IDLE) {
        if (m->request.seq == Ack) return;
        Request = m->request;
        TasContext = m->tasRequest;
        _sprintf(Directory, "%s" MOONSHINE_STATES_DIR, SusamuneCfgStoragePrefix());
        FileId = Offset = 0;
        if (!Request.seq || !Request.session || !SusamuneTasRequestValid(&TasContext) ||
            (Request.reserved && Request.command != SUSAMUNE_STATE_CMD_READ_WINDOW)) { Finish(SUSAMUNE_STATE_BAD_REQUEST); return; }
        if (TasStart()) return;
        Phase = PREPARED_REQUEST;
    }
    if (Phase == PREPARED_REQUEST) {
        if (Request.command == SUSAMUNE_STATE_CMD_CANCEL) { Finish(SUSAMUNE_STATE_CANCELLED); return; }
        if (Request.command == SUSAMUNE_STATE_CMD_CATALOG) {
            if (Request.id > SUSAMUNE_STATE_MAX_ARCHIVE_ID) { Finish(SUSAMUNE_STATE_BAD_REQUEST); return; }
            memset(&m->catalog, 0, sizeof(m->catalog));
            m->catalog.afterId = m->catalog.nextId = Request.id;
            if (f_opendir_char(&Scan, Directory) != FR_OK) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
            DirOpen = true; Phase = CATALOG_NEXT; return;
        }
        if (Request.command == SUSAMUNE_STATE_CMD_EXPORT) {
            sync_before_read(&m->header, sizeof(m->header));
            Header = m->header;
            if (!SusamuneStateHeaderValid(&Header) || Header.gameId != GAME_ID || Header.configId != ConfigId ||
                Header.packedSize != Request.packedSize || !SusamuneStatePoolRange(Request.poolOffset, Request.packedSize) ||
                !TasTransferHeaderValid()) {
                Finish(SUSAMUNE_STATE_BAD_REQUEST); return;
            }
            sync_before_read(m->metadata, Header.metadataSize);
            if (Header.metadataCrc != SusamuneStateCrc(m->metadata, Header.metadataSize)) { Finish(SUSAMUNE_STATE_BAD_REQUEST); return; }
            if (TasContext.projectId && TasContext.role == SUSAMUNE_TAS_TAPE_ROLE && !TasTapeMetadataValid(false)) {
                Finish(SUSAMUNE_STATE_BAD_REQUEST); return;
            }
            FileId = 1; Phase = EXPORT_FIND; return;
        }
        if (Request.command == SUSAMUNE_STATE_CMD_IMPORT) {
            if (!Request.id || Request.id > SUSAMUNE_STATE_MAX_ARCHIVE_ID ||
                !SusamuneStateImportRange(Request.poolOffset, Request.packedSize)) { Finish(SUSAMUNE_STATE_FULL); return; }
            FileId = Request.id; Paths(FileId); Phase = OPEN_FILE; return;
        }
        if (Request.command == SUSAMUNE_STATE_CMD_READ_WINDOW) {
            if (!Request.id || Request.id > SUSAMUNE_STATE_MAX_ARCHIVE_ID ||
                !SusamuneStateWindowRange(Request.packedSize, Request.poolOffset, Request.reserved)) {
                Finish(SUSAMUNE_STATE_BAD_REQUEST); return;
            }
            FileId = Request.id; Paths(FileId); Phase = OPEN_FILE; return;
        }
        if (Request.command == SUSAMUNE_STATE_CMD_RENAME || Request.command == SUSAMUNE_STATE_CMD_DELETE) {
            if (!Request.id || Request.id > SUSAMUNE_STATE_MAX_ARCHIVE_ID || Request.poolOffset || Request.packedSize) {
                Finish(SUSAMUNE_STATE_BAD_REQUEST); return;
            }
            if (Request.command == SUSAMUNE_STATE_CMD_RENAME) {
                sync_before_read(m->requestName, sizeof(m->requestName));
                memcpy(RequestName, m->requestName, sizeof(RequestName));
                if (!SusamuneStateNameValid(RequestName) || !RequestName[0]) { Finish(SUSAMUNE_STATE_BAD_REQUEST); return; }
            }
            FileId = Request.id; Paths(FileId); Phase = OPEN_FILE; return;
        }
        Finish(SUSAMUNE_STATE_BAD_REQUEST); return;
    }
    if (Phase == EXPORT_FIND) {
        Paths(FileId);
        result = f_stat_char(Path, &info);
        if (result == FR_NO_FILE) result = f_stat_char(Temporary, &info);
        if (result == FR_NO_FILE) {
            char marker[72];
            _sprintf(marker, "%s/state_%08u.used", Directory, FileId);
            result = f_stat_char(marker, &info);
        }
        if (result == FR_NO_FILE) { Phase = OPEN_FILE; return; }
        if (result != FR_OK) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        if (++FileId > SUSAMUNE_STATE_MAX_ARCHIVE_ID) Finish(SUSAMUNE_STATE_FULL);
        return;
    }
    if (Phase == OPEN_FILE) {
        result = f_open_char(&File, Request.command == SUSAMUNE_STATE_CMD_EXPORT ? Temporary : Path,
            Request.command == SUSAMUNE_STATE_CMD_EXPORT ? FA_WRITE | FA_CREATE_NEW : FA_READ);
        if (result != FR_OK) { Finish(result == FR_NO_FILE ? SUSAMUNE_STATE_NOT_FOUND : SUSAMUNE_STATE_IO_ERROR); return; }
        FileOpen = true; Phase = HEADER_IO; return;
    }
    if (Phase == HEADER_IO) {
        if (Request.command == SUSAMUNE_STATE_CMD_EXPORT) result = f_write(&File, &Header, sizeof(Header), &done);
        else result = f_read(&File, &Header, sizeof(Header), &done);
        if (result != FR_OK || done != sizeof(Header)) { Finish(SUSAMUNE_STATE_BAD_FILE); return; }
        if (Request.command == SUSAMUNE_STATE_CMD_IMPORT || Request.command == SUSAMUNE_STATE_CMD_READ_WINDOW) {
            if (!SusamuneStateHeaderValid(&Header) || !ValidFileSize(f_size(&File)) ||
                !TasTransferHeaderValid()) { Finish(SUSAMUNE_STATE_BAD_FILE); return; }
            if (Header.headerCrc != Request.expectedHeaderCrc || Header.packedSize != Request.packedSize) { Finish(SUSAMUNE_STATE_STALE); return; }
            if (Header.gameId != GAME_ID || Header.configId != ConfigId) { Finish(SUSAMUNE_STATE_WRONG_CONFIG); return; }
        }
        if (Request.command == SUSAMUNE_STATE_CMD_RENAME || Request.command == SUSAMUNE_STATE_CMD_DELETE) {
            if (!SusamuneStateHeaderValid(&Header) || !ValidFileSize(f_size(&File))) { Finish(SUSAMUNE_STATE_BAD_FILE); return; }
            if (Header.headerCrc != Request.expectedHeaderCrc) { Finish(SUSAMUNE_STATE_STALE); return; }
            result = f_close(&File); FileOpen = false;
            if (result != FR_OK) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
            Phase = MUTATE_FILE; return;
        }
        Phase = METADATA_IO; return;
    }
    if (Phase == MUTATE_FILE) {
        if (Request.command == SUSAMUNE_STATE_CMD_DELETE) EffectiveName(FileId, RequestName);
        Finish(Request.command == SUSAMUNE_STATE_CMD_RENAME ? WriteName() : DeleteArchive());
        return;
    }
    if (Phase == METADATA_IO) {
        if (Request.command == SUSAMUNE_STATE_CMD_EXPORT) result = f_write(&File, m->metadata, Header.metadataSize, &done);
        else result = f_read(&File, m->metadata, Header.metadataSize, &done);
        if (result != FR_OK || done != Header.metadataSize) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        if (SusamuneStateCrc(m->metadata, Header.metadataSize) != Header.metadataCrc) { Finish(SUSAMUNE_STATE_BAD_FILE); return; }
        if (TasContext.projectId && TasContext.role == SUSAMUNE_TAS_TAPE_ROLE &&
            !TasTapeMetadataValid(Request.command != SUSAMUNE_STATE_CMD_EXPORT)) {
            Finish(SUSAMUNE_STATE_BAD_FILE); return;
        }
        if (Request.command == SUSAMUNE_STATE_CMD_READ_WINDOW &&
            f_lseek(&File, sizeof(Header) + Header.metadataSize + Request.poolOffset) != FR_OK) {
            Finish(SUSAMUNE_STATE_IO_ERROR); return;
        }
        PayloadCrc = 0xFFFFFFFFu; Phase = PAYLOAD_IO; return;
    }
    if (Phase == PAYLOAD_IO) {
        const u32 payloadSize = Request.command == SUSAMUNE_STATE_CMD_READ_WINDOW ? Request.reserved : Header.packedSize;
        amount = payloadSize - Offset;
        if (amount > SUSAMUNE_STATE_CHUNK_SIZE) amount = SUSAMUNE_STATE_CHUNK_SIZE;
        if (Request.command == SUSAMUNE_STATE_CMD_EXPORT) {
            bytes = TasContext.projectId && TasContext.role == SUSAMUNE_TAS_TAPE_ROLE ?
                STATE_STAGING + Offset : PoolPiece(Request.poolOffset + Offset, &amount);
            sync_before_read(bytes, amount);
            PayloadCrc = SusamuneStateCrcUpdate(PayloadCrc, bytes, amount);
            result = f_write(&File, bytes, amount, &done);
        } else {
            if (Offset < SUSAMUNE_STATE_STAGING_SIZE) {
                if (amount > SUSAMUNE_STATE_STAGING_SIZE - Offset) amount = SUSAMUNE_STATE_STAGING_SIZE - Offset;
                bytes = STATE_STAGING + Offset;
            } else bytes = PoolPiece(Request.poolOffset + Offset - SUSAMUNE_STATE_STAGING_SIZE, &amount);
            // The packed tail can share a cache line with an occupied slot.
            sync_before_read(bytes, amount);
            result = f_read(&File, bytes, amount, &done);
            if (result == FR_OK && done == amount) PayloadCrc = SusamuneStateCrcUpdate(PayloadCrc, bytes, amount);
            sync_after_write(bytes, amount);
        }
        if (result != FR_OK || done != amount) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        if (TasContext.projectId && TasContext.role == SUSAMUNE_TAS_TAPE_ROLE && !Offset &&
            (bytes[0] || bytes[1] || bytes[2] || bytes[3])) { Finish(SUSAMUNE_STATE_BAD_FILE); return; }
        Offset += amount;
        if (Offset != payloadSize) return;
        if (Request.command == SUSAMUNE_STATE_CMD_EXPORT) {
            Header.payloadCrc = ~PayloadCrc;
            Header.headerCrc = SusamuneStateHeaderCrc(&Header);
            Phase = COMMIT_HEADER;
        } else {
            if (Request.command != SUSAMUNE_STATE_CMD_READ_WINDOW && ~PayloadCrc != Header.payloadCrc) { Finish(SUSAMUNE_STATE_BAD_FILE); return; }
            Phase = CLOSE_FILE;
        }
        return;
    }
    if (Phase == COMMIT_HEADER) {
        if (f_lseek(&File, 0) != FR_OK || f_write(&File, &Header, sizeof(Header), &done) != FR_OK || done != sizeof(Header)) {
            Finish(SUSAMUNE_STATE_IO_ERROR); return;
        }
        Phase = SYNC_FILE; return;
    }
    if (Phase == SYNC_FILE) {
        if (f_sync(&File) != FR_OK) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        Phase = CLOSE_FILE; return;
    }
    if (Phase == CLOSE_FILE) {
        result = f_close(&File); FileOpen = false;
        if (result != FR_OK) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        if (Request.command == SUSAMUNE_STATE_CMD_IMPORT || Request.command == SUSAMUNE_STATE_CMD_READ_WINDOW) Finish(SUSAMUNE_STATE_OK);
        else Phase = RENAME_FILE;
        return;
    }
    if (Phase == RENAME_FILE) {
        Finish(f_rename_char(Temporary, Path) == FR_OK ? SUSAMUNE_STATE_OK : SUSAMUNE_STATE_IO_ERROR);
        return;
    }
    if (Phase == CATALOG_NEXT) {
        for (i = 0; i < 16; ++i) {
            result = f_readdir(&Scan, &info);
            if (result != FR_OK) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
            if (!info.fname[0]) {
                m->catalog.nextId = m->catalog.count ? m->catalog.entries[m->catalog.count - 1].id : Request.id;
                sync_after_write(&m->catalog, sizeof(m->catalog));
                Finish(SUSAMUNE_STATE_OK); return;
            }
            ScanId = CatalogId(info.fname);
            if (!ScanId || ScanId <= Request.id || (info.fattrib & AM_DIR)) continue;
            ScanSize = info.fsize; Paths(ScanId);
            if (f_open_char(&File, Path, FA_READ) != FR_OK) continue;
            FileOpen = true; Phase = CATALOG_HEADER; return;
        }
        return;
    }
    if (Phase == CATALOG_HEADER) {
        result = f_read(&File, &Header, sizeof(Header), &done);
        if (result == FR_OK && done == sizeof(Header)) AddCatalog();
        f_close(&File); FileOpen = false; Phase = CATALOG_NEXT;
    }
}

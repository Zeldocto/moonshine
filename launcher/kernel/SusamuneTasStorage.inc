/* Included by the archive worker; project requests exclusively own its I/O. */
enum { TAS_PHASE_BASE = 32, TAS_PREFLIGHT = TAS_PHASE_BASE, TAS_FIND,
       TAS_SCAN, TAS_SCAN_PROJECT, TAS_VERIFY_OPEN, TAS_VERIFY_HEADER,
       TAS_VERIFY_METADATA, TAS_VERIFY_PAYLOAD, TAS_WRITE, TAS_SYNC,
       TAS_CLOSE, TAS_PUBLISH, TAS_REMOVE, TAS_CLEANUP };
enum { TAS_DELETED_MAGIC = 0x4D535444u };
struct TasDeleted {
    u32 magic, version, projectId, generation, manifestCrc, reserved[2], checksum;
};
static struct SusamuneTasManifest TasCopies[2];
static struct TasDeleted TasTombstone;
static bool TasValid[2];
static u32 TasLatest, TasId, TasPart, TasRemoveIndex;
static char TasRoot[32];
typedef char TasRootFits[
    sizeof("1:" MOONSHINE_DATA_ROOT MOONSHINE_TAS_DIR) <= sizeof(TasRoot) ? 1 : -1];

static u32 TasPartId(const struct SusamuneTasManifest *project, u32 part)
{
    return part == SUSAMUNE_TAS_TAPE_ROLE ? project->tape.componentId : project->components[part].componentId;
}

static bool TasHeaderMatches(const struct SusamuneStateArchiveHeader *header,
                             const struct SusamuneTasManifest *project, u32 part)
{
    const bool tape = part == SUSAMUNE_TAS_TAPE_ROLE;
    if (header->gameId != project->gameId || header->buildCrc != project->buildCrc ||
        header->configId != project->configId) return false;
    if (tape) return SusamuneTasTapeHeaderValid(header) && header->sceneKey == project->sceneKey &&
        header->headerCrc == project->tape.headerCrc && header->packedSize == project->tape.packedBytes;
    return header->snapshotVersion != SUSAMUNE_TAS_TAPE_SNAPSHOT &&
        header->sceneKey == project->components[part].sceneKey &&
        header->headerCrc == project->components[part].headerCrc &&
        header->packedSize == project->components[part].packedBytes;
}

static bool TasTransferHeaderValid(void)
{
    if (!TasContext.projectId) return Header.snapshotVersion != SUSAMUNE_TAS_TAPE_SNAPSHOT;
    if (TasContext.role == SUSAMUNE_TAS_TAPE_ROLE) {
        if (!SusamuneTasTapeHeaderValid(&Header) || Request.poolOffset ||
            Request.command == SUSAMUNE_STATE_CMD_READ_WINDOW) return false;
    } else if (Header.snapshotVersion == SUSAMUNE_TAS_TAPE_SNAPSHOT) return false;
    return Request.command == SUSAMUNE_STATE_CMD_EXPORT || TasHeaderMatches(&Header, &TasProject, TasContext.role);
}

static bool TasTapeMetadataValid(bool projectBound)
{
    const struct SusamuneTasTakeData *take = (const struct SusamuneTasTakeData *)STATE_MAILBOX->metadata;
    if (!SusamuneTasTapeMetadataValid(&Header, take)) return false;
    return !projectBound || (take->frames == TasProject.tapeFrames &&
        !memcmp(take->originKey, TasProject.startKey, sizeof(take->originKey)));
}

static void TasDirectory(u32 id)
{
    _sprintf(TasRoot, "%s" MOONSHINE_TAS_DIR, SusamuneCfgStoragePrefix());
    _sprintf(Directory, "%s/tas_%08u", TasRoot, id);
}

static bool TasMissing(FRESULT result)
{
    return result == FR_NO_FILE || result == FR_NO_PATH;
}

static u32 TasReadLatest(u32 id, bool *empty)
{
    FIL file;
    FILINFO info;
    FRESULT result, closed;
    UINT done;
    u32 i, present = 0;
    *empty = false;
    TasDirectory(id);
    TasValid[0] = TasValid[1] = false;
    memset(TasCopies, 0, sizeof(TasCopies));
    result = f_stat_char(Directory, &info);
    if (TasMissing(result)) return SUSAMUNE_STATE_NOT_FOUND;
    if (result != FR_OK) return SUSAMUNE_STATE_IO_ERROR;
    if (!(info.fattrib & AM_DIR)) return SUSAMUNE_STATE_BAD_FILE;
    _sprintf(Path, "%s/project.deleted", Directory);
    result = f_open_char(&file, Path, FA_READ);
    if (result == FR_OK) {
        const u32 size = f_size(&file);
        result = f_read(&file, &TasTombstone, sizeof(TasTombstone), &done);
        closed = f_close(&file);
        if (result != FR_OK || closed != FR_OK) return SUSAMUNE_STATE_IO_ERROR;
        if (size != sizeof(TasTombstone) || done != size ||
            TasTombstone.magic != TAS_DELETED_MAGIC || TasTombstone.version != 1 ||
            TasTombstone.projectId != id || !TasTombstone.generation ||
            TasTombstone.reserved[0] || TasTombstone.reserved[1] ||
            TasTombstone.checksum != SusamuneStateCrc(&TasTombstone, sizeof(TasTombstone) - 4))
            return SUSAMUNE_STATE_BAD_FILE;
        return SUSAMUNE_STATE_NOT_FOUND;
    }
    if (!TasMissing(result)) return SUSAMUNE_STATE_IO_ERROR;
    for (i = 0; i < 2; ++i) {
        _sprintf(Path, "%s/project.%c", Directory, 'a' + i);
        result = f_open_char(&file, Path, FA_READ);
        if (TasMissing(result)) continue;
        if (result != FR_OK) return SUSAMUNE_STATE_IO_ERROR;
        ++present;
        const u32 size = f_size(&file);
        result = f_read(&file, &TasCopies[i], sizeof(TasCopies[i]), &done);
        closed = f_close(&file);
        if (result != FR_OK || closed != FR_OK) return SUSAMUNE_STATE_IO_ERROR;
        if (done >= 8 && TasCopies[i].magic == SUSAMUNE_TAS_MAGIC &&
            TasCopies[i].version > SUSAMUNE_TAS_VERSION) return SUSAMUNE_STATE_BAD_FILE;
        TasValid[i] = size == sizeof(TasCopies[i]) && done == size &&
            SusamuneTasManifestValid(&TasCopies[i]) && TasCopies[i].projectId == id;
    }
    if (!TasValid[0] && !TasValid[1]) {
        if (present) return SUSAMUNE_STATE_BAD_FILE;
        *empty = true;
        TasLatest = 1;
        return SUSAMUNE_STATE_OK;
    }
    if (TasValid[0] && TasValid[1] && TasCopies[0].generation == TasCopies[1].generation &&
        memcmp(&TasCopies[0], &TasCopies[1], sizeof(TasCopies[0]))) return SUSAMUNE_STATE_BAD_FILE;
    TasLatest = TasValid[1] && (!TasValid[0] || TasCopies[1].generation > TasCopies[0].generation) ? 1 : 0;
    return SUSAMUNE_STATE_OK;
}

static bool TasStart(void)
{
    struct SusamuneStateStorageMailbox *m = STATE_MAILBOX;
    const bool operation = Request.command >= SUSAMUNE_STATE_CMD_TAS_BEGIN;
    if (!operation && !TasContext.projectId) return false;
    if (operation) {
        if (Request.command > SUSAMUNE_STATE_CMD_TAS_DELETE || TasContext.projectId ||
            Request.id > SUSAMUNE_STATE_MAX_ARCHIVE_ID || Request.poolOffset || Request.packedSize) {
            Finish(SUSAMUNE_STATE_BAD_REQUEST); return true;
        }
        if (Request.command == SUSAMUNE_STATE_CMD_TAS_BEGIN || Request.command == SUSAMUNE_STATE_CMD_TAS_RENAME) {
            sync_before_read(m->requestName, sizeof(m->requestName));
            memcpy(RequestName, m->requestName, sizeof(RequestName));
            if (!SusamuneStateNameValid(RequestName) || !RequestName[0]) {
                Finish(SUSAMUNE_STATE_BAD_REQUEST); return true;
            }
        }
        if (Request.command == SUSAMUNE_STATE_CMD_TAS_BEGIN) {
            FRESULT result;
            if (Request.id || Request.expectedHeaderCrc) { Finish(SUSAMUNE_STATE_BAD_REQUEST); return true; }
            TasDirectory(1);
            result = f_mkdir_char(TasRoot);
            if (result != FR_OK && result != FR_EXIST) { Finish(SUSAMUNE_STATE_IO_ERROR); return true; }
            TasId = 1; Phase = TAS_FIND; return true;
        }
        if (Request.command == SUSAMUNE_STATE_CMD_TAS_CATALOG) {
            if (Request.expectedHeaderCrc) { Finish(SUSAMUNE_STATE_BAD_REQUEST); return true; }
            TasDirectory(1);
            memset(&m->catalog, 0, sizeof(m->catalog));
            m->catalog.afterId = m->catalog.nextId = Request.id;
            FRESULT result = f_opendir_char(&Scan, TasRoot);
            if (TasMissing(result)) {
                sync_after_write(&m->catalog, sizeof(m->catalog)); Finish(SUSAMUNE_STATE_OK); return true;
            }
            if (result != FR_OK) { Finish(SUSAMUNE_STATE_IO_ERROR); return true; }
            DirOpen = true; Phase = TAS_SCAN; return true;
        }
        if (!Request.id) { Finish(SUSAMUNE_STATE_BAD_REQUEST); return true; }
        TasId = FileId = Request.id;
        if (Request.command == SUSAMUNE_STATE_CMD_TAS_COMMIT) {
            sync_before_read(&m->tasProject, sizeof(m->tasProject));
            TasProject = m->tasProject;
            if (!SusamuneTasManifestValid(&TasProject) || TasProject.projectId != TasId) {
                Finish(SUSAMUNE_STATE_BAD_REQUEST); return true;
            }
        }
    } else {
        if ((Request.command != SUSAMUNE_STATE_CMD_EXPORT && Request.command != SUSAMUNE_STATE_CMD_IMPORT &&
             Request.command != SUSAMUNE_STATE_CMD_READ_WINDOW) || TasContext.componentId != Request.id ||
            (Request.command == SUSAMUNE_STATE_CMD_EXPORT && Request.id)) {
            Finish(SUSAMUNE_STATE_BAD_REQUEST); return true;
        }
        TasId = TasContext.projectId;
    }
    Phase = TAS_PREFLIGHT;
    return true;
}

static void TasPreparePublish(bool deleted)
{
    if (deleted) {
        memset(&TasTombstone, 0, sizeof(TasTombstone));
        TasTombstone.magic = TAS_DELETED_MAGIC; TasTombstone.version = 1;
        TasTombstone.projectId = TasId; TasTombstone.generation = TasProject.generation;
        TasTombstone.manifestCrc = TasProject.checksum;
        TasTombstone.checksum = SusamuneStateCrc(&TasTombstone, sizeof(TasTombstone) - 4);
        _sprintf(Path, "%s/project.deleted", Directory);
        _sprintf(Temporary, "%s/project.deleted.tmp", Directory);
    } else {
        _sprintf(Path, "%s/project.%c", Directory, 'a' + (TasLatest ^ 1));
        _sprintf(Temporary, "%s/project.%c.tmp", Directory, 'a' + (TasLatest ^ 1));
    }
    Phase = TAS_WRITE;
}

static void TasPreflight(void)
{
    bool empty;
    const u32 status = TasReadLatest(TasId, &empty);
    const struct SusamuneTasManifest *latest = &TasCopies[TasLatest];
    if (status != SUSAMUNE_STATE_OK) { Finish(status); return; }
    if (TasContext.projectId) {
        if (TasContext.projectGeneration != (empty ? 0 : latest->generation) ||
            TasContext.expectedProjectCrc != (empty ? 0 : latest->checksum)) { Finish(SUSAMUNE_STATE_STALE); return; }
        if (Request.command == SUSAMUNE_STATE_CMD_EXPORT) {
            sync_before_read(&STATE_MAILBOX->header, sizeof(STATE_MAILBOX->header));
            const struct SusamuneStateArchiveHeader *h = &STATE_MAILBOX->header;
            if (!empty && (h->gameId != latest->gameId || h->buildCrc != latest->buildCrc ||
                h->configId != latest->configId ||
                ((TasContext.role == 0 || TasContext.role == SUSAMUNE_TAS_TAPE_ROLE) && h->sceneKey != latest->sceneKey))) {
                Finish(SUSAMUNE_STATE_WRONG_CONFIG); return;
            }
        } else {
            const bool tape = TasContext.role == SUSAMUNE_TAS_TAPE_ROLE;
            const u32 crc = tape ? latest->tape.headerCrc : latest->components[TasContext.role].headerCrc;
            const u32 packed = tape ? latest->tape.packedBytes : latest->components[TasContext.role].packedBytes;
            if (empty || TasPartId(latest, TasContext.role) != Request.id || crc != Request.expectedHeaderCrc ||
                packed != Request.packedSize) { Finish(SUSAMUNE_STATE_STALE); return; }
            TasProject = *latest;
        }
        Phase = PREPARED_REQUEST; return;
    }
    if (Request.command == SUSAMUNE_STATE_CMD_TAS_READ) {
        if (empty) { Finish(SUSAMUNE_STATE_NOT_FOUND); return; }
        if (Request.expectedHeaderCrc && Request.expectedHeaderCrc != latest->checksum) { Finish(SUSAMUNE_STATE_STALE); return; }
        TasProject = *latest; Finish(SUSAMUNE_STATE_OK); return;
    }
    if (Request.expectedHeaderCrc != (empty ? 0 : latest->checksum)) { Finish(SUSAMUNE_STATE_STALE); return; }
    if (Request.command == SUSAMUNE_STATE_CMD_TAS_COMMIT) {
        if ((!empty && latest->generation == 0xFFFFFFFFu) ||
            TasProject.generation != (empty ? 1 : latest->generation + 1)) { Finish(SUSAMUNE_STATE_STALE); return; }
        if (TasProject.gameId != GAME_ID || TasProject.configId != ConfigId ||
            (!empty && (TasProject.gameId != latest->gameId || TasProject.buildCrc != latest->buildCrc ||
             TasProject.configId != latest->configId || TasProject.sceneKey != latest->sceneKey ||
             memcmp(TasProject.startKey, latest->startKey, sizeof(TasProject.startKey))))) {
            Finish(SUSAMUNE_STATE_WRONG_CONFIG); return;
        }
        TasPart = 0; Phase = TAS_VERIFY_OPEN; return;
    }
    if (empty) { Finish(SUSAMUNE_STATE_NOT_FOUND); return; }
    TasProject = *latest;
    if (Request.command == SUSAMUNE_STATE_CMD_TAS_RENAME) {
        if (TasProject.generation == 0xFFFFFFFFu) { Finish(SUSAMUNE_STATE_FULL); return; }
        ++TasProject.generation;
        memcpy(TasProject.name, RequestName, sizeof(TasProject.name));
        TasProject.checksum = SusamuneTasManifestCrc(&TasProject);
        TasPreparePublish(false);
    } else TasPreparePublish(true);
}

static void TasAddCatalog(void)
{
    struct SusamuneStateCatalog *catalog = &STATE_MAILBOX->catalog;
    const struct SusamuneTasManifest *project = &TasCopies[TasLatest];
    struct SusamuneStateCatalogEntry entry;
    u32 i, at;
    memset(&entry, 0, sizeof(entry));
    entry.id = project->projectId; entry.gameId = project->gameId;
    entry.buildCrc = project->buildCrc; entry.sceneKey = project->sceneKey;
    entry.headerCrc = project->checksum; entry.metadataSize = sizeof(*project);
    entry.rawSize = project->tapeFrames;
    entry.packedSize = project->tape.packedBytes;
    memcpy(entry.name, project->name, sizeof(entry.name));
    for (i = 0; i < SUSAMUNE_TAS_COMPONENTS; ++i) entry.packedSize += project->components[i].packedBytes;
    for (at = 0; at < catalog->count && catalog->entries[at].id < entry.id; ++at) {}
    if (catalog->count == SUSAMUNE_STATE_CATALOG_COUNT) catalog->more = 1;
    else ++catalog->count;
    if (at == SUSAMUNE_STATE_CATALOG_COUNT) return;
    for (i = catalog->count - 1; i > at; --i) catalog->entries[i] = catalog->entries[i - 1];
    catalog->entries[at] = entry;
}

static u32 TasDirectoryId(const WCHAR *name)
{
    u32 i, id = 0;
    const char prefix[] = "tas_";
    for (i = 0; i < 4; ++i) if (name[i] != (WCHAR)prefix[i]) return 0;
    for (i = 4; i < 12; ++i) {
        if (name[i] < '0' || name[i] > '9') return 0;
        id = id * 10 + name[i] - '0';
    }
    return name[12] ? 0 : id;
}

static void TasService(void)
{
    struct SusamuneStateStorageMailbox *m = STATE_MAILBOX;
    FRESULT result;
    FILINFO info;
    UINT done;
    u32 amount, i;
    if (Phase == TAS_PREFLIGHT) { TasPreflight(); return; }
    if (Phase == TAS_FIND) {
        TasDirectory(TasId);
        result = f_stat_char(Directory, &info);
        if (TasMissing(result)) {
            result = f_mkdir_char(Directory);
            if (result == FR_OK) { FileId = TasId; Finish(SUSAMUNE_STATE_OK); return; }
            if (result != FR_EXIST) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        } else if (result != FR_OK) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        if (++TasId > SUSAMUNE_STATE_MAX_ARCHIVE_ID) Finish(SUSAMUNE_STATE_FULL);
        return;
    }
    if (Phase == TAS_SCAN) {
        for (i = 0; i < 16; ++i) {
            result = f_readdir(&Scan, &info);
            if (result != FR_OK) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
            if (!info.fname[0]) {
                m->catalog.nextId = m->catalog.count ? m->catalog.entries[m->catalog.count - 1].id : Request.id;
                sync_after_write(&m->catalog, sizeof(m->catalog)); Finish(SUSAMUNE_STATE_OK); return;
            }
            TasId = TasDirectoryId(info.fname);
            if (!TasId || TasId <= Request.id || !(info.fattrib & AM_DIR)) continue;
            Phase = TAS_SCAN_PROJECT; return;
        }
        return;
    }
    if (Phase == TAS_SCAN_PROJECT) {
        bool empty;
        const u32 status = TasReadLatest(TasId, &empty);
        if (status == SUSAMUNE_STATE_IO_ERROR) { Finish(status); return; }
        if (status == SUSAMUNE_STATE_OK && !empty) TasAddCatalog();
        Phase = TAS_SCAN; return;
    }
    if (Phase == TAS_VERIFY_OPEN) {
        while (TasPart < SUSAMUNE_TAS_COMPONENTS && !TasProject.components[TasPart].componentId) ++TasPart;
        if (TasPart > SUSAMUNE_TAS_TAPE_ROLE) { TasPreparePublish(false); return; }
        Paths(TasPartId(&TasProject, TasPart));
        result = f_open_char(&File, Path, FA_READ);
        if (result != FR_OK) { Finish(TasMissing(result) ? SUSAMUNE_STATE_NOT_FOUND : SUSAMUNE_STATE_IO_ERROR); return; }
        FileOpen = true; Phase = TAS_VERIFY_HEADER; return;
    }
    if (Phase == TAS_VERIFY_HEADER) {
        result = f_read(&File, &Header, sizeof(Header), &done);
        if (result != FR_OK || done != sizeof(Header)) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        if (!SusamuneStateHeaderValid(&Header) || !ValidFileSize(f_size(&File)) ||
            !TasHeaderMatches(&Header, &TasProject, TasPart)) {
            Finish(SUSAMUNE_STATE_BAD_FILE); return;
        }
        Phase = TAS_VERIFY_METADATA; return;
    }
    if (Phase == TAS_VERIFY_METADATA) {
        result = f_read(&File, m->metadata, Header.metadataSize, &done);
        if (result != FR_OK || done != Header.metadataSize) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        if (SusamuneStateCrc(m->metadata, Header.metadataSize) != Header.metadataCrc) { Finish(SUSAMUNE_STATE_BAD_FILE); return; }
        if (TasPart == SUSAMUNE_TAS_TAPE_ROLE && !TasTapeMetadataValid(true)) { Finish(SUSAMUNE_STATE_BAD_FILE); return; }
        Offset = 0; PayloadCrc = 0xFFFFFFFFu; Phase = TAS_VERIFY_PAYLOAD; return;
    }
    if (Phase == TAS_VERIFY_PAYLOAD) {
        amount = Header.packedSize - Offset;
        if (amount > SUSAMUNE_STATE_CHUNK_SIZE) amount = SUSAMUNE_STATE_CHUNK_SIZE;
        sync_before_read(STATE_STAGING, amount);
        result = f_read(&File, STATE_STAGING, amount, &done);
        sync_after_write(STATE_STAGING, amount);
        if (result != FR_OK || done != amount) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        if (TasPart == SUSAMUNE_TAS_TAPE_ROLE && !Offset &&
            (STATE_STAGING[0] || STATE_STAGING[1] || STATE_STAGING[2] || STATE_STAGING[3])) {
            Finish(SUSAMUNE_STATE_BAD_FILE); return;
        }
        PayloadCrc = SusamuneStateCrcUpdate(PayloadCrc, STATE_STAGING, amount);
        Offset += amount;
        if (Offset != Header.packedSize) return;
        if (~PayloadCrc != Header.payloadCrc) { Finish(SUSAMUNE_STATE_BAD_FILE); return; }
        result = f_close(&File); FileOpen = false;
        if (result != FR_OK) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        ++TasPart; Phase = TAS_VERIFY_OPEN; return;
    }
    if (Phase == TAS_WRITE) {
        result = f_open_char(&File, Temporary, FA_WRITE | FA_CREATE_ALWAYS);
        if (result != FR_OK) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        FileOpen = true;
        const bool deleted = Request.command == SUSAMUNE_STATE_CMD_TAS_DELETE;
        amount = deleted ? sizeof(TasTombstone) : sizeof(TasProject);
        result = f_write(&File, deleted ? (const void *)&TasTombstone : (const void *)&TasProject, amount, &done);
        if (result != FR_OK || done != amount) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        Phase = TAS_SYNC; return;
    }
    if (Phase == TAS_SYNC) {
        if (f_sync(&File) != FR_OK) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        Phase = TAS_CLOSE; return;
    }
    if (Phase == TAS_CLOSE) {
        result = f_close(&File); FileOpen = false;
        if (result != FR_OK) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        Phase = TAS_PUBLISH; return;
    }
    if (Phase == TAS_PUBLISH) {
        // Only the inactive generation is removed; the current one stays valid.
        result = f_unlink_char(Path);
        if (result != FR_OK && !TasMissing(result)) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        if (f_rename_char(Temporary, Path) != FR_OK) { Finish(SUSAMUNE_STATE_IO_ERROR); return; }
        FileId = TasId;
        if (Request.command == SUSAMUNE_STATE_CMD_TAS_DELETE) { TasRemoveIndex = 0; Phase = TAS_REMOVE; return; }
        TasRemoveIndex = 0; Phase = TAS_CLEANUP; return;
    }
    if (Phase == TAS_CLEANUP) {
        const u32 outgoing = TasLatest ^ 1;
        while (TasValid[outgoing] && TasRemoveIndex <= SUSAMUNE_TAS_TAPE_ROLE) {
            const u32 id = TasPartId(&TasCopies[outgoing], TasRemoveIndex++);
            bool retained = !id;
            for (i = 0; i <= SUSAMUNE_TAS_TAPE_ROLE; ++i)
                if (TasPartId(&TasProject, i) == id || TasPartId(&TasCopies[TasLatest], i) == id) retained = true;
            if (retained) continue;
            Paths(id);
            // Publication already succeeded; leftover cleanup must not undo it.
            f_unlink_char(Path);
            return;
        }
        Finish(SUSAMUNE_STATE_OK); return;
    }
    if (Phase == TAS_REMOVE) {
        if (TasRemoveIndex < 8) {
            const u32 copy = TasRemoveIndex / 4, part = TasRemoveIndex % 4;
            ++TasRemoveIndex;
            if (!TasValid[copy] || !TasPartId(&TasCopies[copy], part)) return;
            Paths(TasPartId(&TasCopies[copy], part));
        } else if (TasRemoveIndex < 12) {
            const u32 index = TasRemoveIndex++ - 8;
            _sprintf(Path, index < 2 ? "%s/project.%c" : "%s/project.%c.tmp", Directory, 'a' + (index & 1));
        } else { Finish(SUSAMUNE_STATE_OK); return; }
        result = f_unlink_char(Path);
        if (result != FR_OK && !TasMissing(result)) Finish(SUSAMUNE_STATE_IO_ERROR);
    }
}

#include <stdio.h>
#include <string.h>

#include "ff_utf8.h"
#include "MoonshineData.h"
#include "susamune/data_paths.h"

#define DATA_PATH_SIZE 512
#define DATA_MARKER MOONSHINE_DATA_ROOT "/.layout-v1"

static FRESULT EnsureDataDirectory(const char *path)
{
    FILINFO info;
    FRESULT result = f_stat_char(path, &info);
    if (result == FR_OK)
        return (info.fattrib & AM_DIR) ? FR_OK : FR_EXIST;
    if (result != FR_NO_FILE && result != FR_NO_PATH)
        return result;
    result = f_mkdir_char(path);
    if (result == FR_EXIST)
    {
        result = f_stat_char(path, &info);
        if (result == FR_OK && !(info.fattrib & AM_DIR))
            return FR_EXIST;
    }
    return result;
}

static FRESULT JoinDataPath(char *out, const char *parent, const char *leaf)
{
    int length = snprintf(out, DATA_PATH_SIZE, "%s/%s", parent, leaf);
    return length > 0 && length < DATA_PATH_SIZE ? FR_OK : FR_INVALID_NAME;
}

static FRESULT PreserveCollision(const char *source, const char *device)
{
    char path[DATA_PATH_SIZE];
    FILINFO info;
    unsigned int index;
    FRESULT result;
    snprintf(path, sizeof(path), "%s:" MOONSHINE_DATA_ROOT MOONSHINE_BACKUPS_DIR, device);
    result = EnsureDataDirectory(path);
    if (result != FR_OK)
        return result;
    for (index = 1; index <= 9999; ++index)
    {
        snprintf(path, sizeof(path), "%s:" MOONSHINE_DATA_ROOT
            MOONSHINE_BACKUPS_DIR "/migration_%04u", device, index);
        result = f_stat_char(path, &info);
        if (result == FR_NO_FILE)
        {
            result = EnsureDataDirectory(path);
            if (result != FR_OK)
                return result;
            /* Keep the original leaf so a conflicting setting/report is identifiable. */
            {
                const char *leaf = strrchr(source, '/');
                char destination[DATA_PATH_SIZE];
                result = JoinDataPath(destination, path, leaf ? leaf + 1 : source);
                if (result == FR_OK)
                    result = f_rename_char(source, destination);
            }
            return result;
        }
        if (result != FR_OK)
            return result;
    }
    return FR_DENIED;
}

static FRESULT MoveDataTree(const char *source, const char *destination,
    const char *device, unsigned int depth)
{
    FILINFO from, to;
    FRESULT result = f_stat_char(source, &from);
    if (result == FR_NO_FILE || result == FR_NO_PATH)
        return FR_OK;
    if (result != FR_OK)
        return result;
    result = f_stat_char(destination, &to);
    if (result == FR_NO_FILE || result == FR_NO_PATH)
        return f_rename_char(source, destination);
    if (result != FR_OK)
        return result;
    if (!(from.fattrib & AM_DIR) || !(to.fattrib & AM_DIR))
        return PreserveCollision(source, device);
    if (depth >= 8)
        return FR_INVALID_NAME;

    /* Reopen after each move: mutating an open FAT directory can skip entries. */
    for (;;)
    {
        DIR directory;
        FILINFO child;
        char oldPath[DATA_PATH_SIZE], newPath[DATA_PATH_SIZE];
        result = f_opendir_char(&directory, source);
        if (result != FR_OK)
            return result;
        do {
            result = f_readdir(&directory, &child);
        } while (result == FR_OK && child.fname[0] == '.' &&
            (child.fname[1] == 0 || (child.fname[1] == '.' && child.fname[2] == 0)));
        if (result == FR_OK && child.fname[0])
        {
            const char *leaf = wchar_to_char(child.fname);
            result = JoinDataPath(oldPath, source, leaf);
            if (result == FR_OK)
                result = JoinDataPath(newPath, destination, leaf);
        }
        if (f_closedir(&directory) != FR_OK && result == FR_OK)
            result = FR_DISK_ERR;
        if (result != FR_OK)
            return result;
        if (!child.fname[0])
            return f_unlink_char(source);
        result = MoveDataTree(oldPath, newPath, device, depth + 1);
        if (result != FR_OK)
            return result;
    }
}

static FRESULT MoveLegacyData(const char *device, const char *oldLeaf,
    const char *newLeaf)
{
    char source[DATA_PATH_SIZE], destination[DATA_PATH_SIZE];
    int a = snprintf(source, sizeof(source), "%s:/%s", device, oldLeaf);
    int b = snprintf(destination, sizeof(destination), "%s:" MOONSHINE_DATA_ROOT
        "/%s", device, newLeaf);
    if (a <= 0 || a >= DATA_PATH_SIZE || b <= 0 || b >= DATA_PATH_SIZE)
        return FR_INVALID_NAME;
    return MoveDataTree(source, destination, device, 0);
}

static FRESULT MoveLegacyLibrary(const char *device, const char *oldLeaf,
    const char *newLeaf)
{
    char source[DATA_PATH_SIZE], destination[DATA_PATH_SIZE];
    FILINFO info;
    DIR directory;
    int empty;
    FRESULT result;
    snprintf(source, sizeof(source), "%s:/%s", device, oldLeaf);
    snprintf(destination, sizeof(destination), "%s:" MOONSHINE_DATA_ROOT "/%s", device, newLeaf);
    result = f_stat_char(source, &info);
    if (result == FR_NO_FILE || result == FR_NO_PATH) return FR_OK;
    if (result != FR_OK) return result;
    result = f_stat_char(destination, &info);
    if (result == FR_NO_FILE || result == FR_NO_PATH)
        return f_rename_char(source, destination);
    if (result != FR_OK) return result;
    if (!(info.fattrib & AM_DIR)) return PreserveCollision(source, device);
    result = f_opendir_char(&directory, destination);
    if (result != FR_OK) return result;
    do {
        result = f_readdir(&directory, &info);
    } while (result == FR_OK && info.fname[0] == '.' &&
        (info.fname[1] == 0 || (info.fname[1] == '.' && info.fname[2] == 0)));
    empty = result == FR_OK && !info.fname[0];
    if (f_closedir(&directory) != FR_OK && result == FR_OK) result = FR_DISK_ERR;
    if (result != FR_OK) return result;
    /* Independent catalogs can reuse IDs; merging their members would mix owners. */
    if (!empty) return PreserveCollision(source, device);
    result = f_unlink_char(destination);
    return result == FR_OK ? f_rename_char(source, destination) : result;
}

static FRESULT DataPathExists(const char *path, int *exists)
{
    FILINFO info;
    FRESULT result = f_stat_char(path, &info);
    *exists = result == FR_OK;
    return result == FR_NO_FILE || result == FR_NO_PATH ? FR_OK : result;
}

static FRESULT ReadMigrationDecision(const char *path, int *exists, int *copy)
{
    FIL file;
    char decision[4];
    UINT count = 0;
    int sized;
    FRESULT result = f_open_char(&file, path, FA_READ | FA_OPEN_EXISTING);
    *exists = result == FR_OK;
    if (result == FR_NO_FILE || result == FR_NO_PATH) return FR_OK;
    if (result != FR_OK) return result;
    sized = f_size(&file) == sizeof(decision);
    result = f_read(&file, decision, sizeof(decision), &count);
    if (f_close(&file) != FR_OK && result == FR_OK) result = FR_DISK_ERR;
    if (result != FR_OK) return result;
    if (!sized || count != sizeof(decision)) return FR_INT_ERR;
    *copy = !memcmp(decision, "COPY", sizeof(decision));
    return *copy || !memcmp(decision, "KEEP", sizeof(decision)) ? FR_OK : FR_INT_ERR;
}

static FRESULT WriteMigrationDecision(const char *path, int copy)
{
    char temporary[DATA_PATH_SIZE];
    FIL file;
    UINT count = 0;
    int exists, checked;
    FRESULT result;
    snprintf(temporary, sizeof(temporary), "%s.tmp", path);
    result = f_open_char(&file, temporary, FA_WRITE | FA_CREATE_ALWAYS);
    if (result != FR_OK) return result;
    result = f_write(&file, copy ? "COPY" : "KEEP", 4, &count);
    if (result == FR_OK && count != 4) result = FR_DISK_ERR;
    if (result == FR_OK) result = f_sync(&file);
    if (f_close(&file) != FR_OK && result == FR_OK) result = FR_DISK_ERR;
    if (result != FR_OK) return result;
    result = ReadMigrationDecision(temporary, &exists, &checked);
    if (result != FR_OK) return result;
    if (!exists || checked != copy) return FR_INT_ERR;
    return f_rename_char(temporary, path);
}

static FRESULT MigrateDataFamily(const char *device, const char *family,
    const char *oldStem, const char *newStem,
    const char *const *suffixes, unsigned int count)
{
    char marker[64], staged[64];
    char source[DATA_PATH_SIZE], destination[DATA_PATH_SIZE];
    unsigned int i;
    int exists, decided, copy = 1, legacy = 0;
    FRESULT result;
    if (!strcmp(family, "ini"))
        snprintf(marker, sizeof(marker), "%s:" MOONSHINE_DATA_ROOT "/.ini-migration", device);
    else
        snprintf(marker, sizeof(marker), "%s:" MOONSHINE_DATA_ROOT "/.migrate_%s", device, family);
    snprintf(staged, sizeof(staged), "%s:" MOONSHINE_DATA_ROOT
        MOONSHINE_BACKUPS_DIR "/legacy_%s", device, family);
    result = ReadMigrationDecision(marker, &decided, &copy);
    if (result != FR_OK) return result;
    if (!decided)
    {
        for (i = 0; i < count; ++i)
        {
            snprintf(source, sizeof(source), "%s:/%s%s", device, oldStem, suffixes[i]);
            result = DataPathExists(source, &exists);
            if (result != FR_OK) return result;
            legacy |= exists;
            snprintf(destination, sizeof(destination), "%s:" MOONSHINE_DATA_ROOT "/%s%s", device, newStem, suffixes[i]);
            result = DataPathExists(destination, &exists);
            if (result != FR_OK) return result;
            if (exists) copy = 0;
        }
        if (!legacy) return FR_OK;
        result = DataPathExists(staged, &exists);
        if (result != FR_OK) return result;
        if (exists) return FR_EXIST;
        /* Pin the family before moving a sibling; a retry must not reinterpret our own .bak. */
        result = WriteMigrationDecision(marker, copy);
        if (result != FR_OK) return result;
    }
    snprintf(destination, sizeof(destination), "%s:" MOONSHINE_DATA_ROOT MOONSHINE_BACKUPS_DIR, device);
    result = EnsureDataDirectory(destination);
    if (result != FR_OK) return result;
    result = EnsureDataDirectory(staged);
    if (result != FR_OK) return result;
    for (i = 0; i < count; ++i)
    {
        snprintf(source, sizeof(source), "%s:/%s%s", device, oldStem, suffixes[i]);
        snprintf(destination, sizeof(destination), "%s/%s%s", staged, oldStem, suffixes[i]);
        result = MoveDataTree(source, destination, device, 0);
        if (result != FR_OK) return result;
    }
    if (!copy) return FR_OK;
    for (i = 0; i < count; ++i)
    {
        snprintf(source, sizeof(source), "%s/%s%s", staged, oldStem, suffixes[i]);
        result = DataPathExists(source, &exists);
        if (result != FR_OK) return result;
        if (!exists) continue;
        snprintf(destination, sizeof(destination), "%s:" MOONSHINE_DATA_ROOT "/%s%s", device, newStem, suffixes[i]);
        result = DataPathExists(destination, &exists);
        if (result != FR_OK) return result;
        if (exists) return FR_EXIST;
        result = f_rename_char(source, destination);
        if (result != FR_OK) return result;
    }
    return f_unlink_char(staged);
}

static FRESULT MigrateData(const char *device)
{
    static const char *const regions[] = { "jp", "us", "pal" };
    static const char *const iniSuffixes[] = { ".bak", ".tmp", "" };
    static const char *const pairSuffixes[] = { "_a.bin", "_b.bin" };
    static const char *const crashSuffixes[] = { ".bin", ".core", ".txt" };
    static const char *const directories[][2] = {
        { "susamune_ghosts", "ghosts" },
        { "moonshine_states", "states" },
        { "moonshine_tas", "tas" },
        { "Moonshine_Theme", "theme" },
        { "susamune_backups", "backups" },
    };
    char oldLeaf[80], newLeaf[80], family[40], path[64];
    unsigned int i, region, version, copy;
    FRESULT result;
    for (i = 0; i < sizeof(directories) / sizeof(directories[0]); ++i)
    {
        result = i < 3 ? MoveLegacyLibrary(device, directories[i][0], directories[i][1]) :
            MoveLegacyData(device, directories[i][0], directories[i][1]);
        if (result != FR_OK) return result;
    }
    result = MigrateDataFamily(device, "ini", "susamune.ini", "moonshine.ini", iniSuffixes, 3);
    if (result != FR_OK) return result;
    for (region = 0; region < 3; ++region)
    {
        for (version = 1; version <= 2; ++version)
        {
            snprintf(family, sizeof(family), "pbs_v%u_%s", version, regions[region]);
            snprintf(oldLeaf, sizeof(oldLeaf), "susamune_%s", family);
            snprintf(newLeaf, sizeof(newLeaf), "moonshine_%s", family);
            result = MigrateDataFamily(device, family, oldLeaf, newLeaf, pairSuffixes, 2);
            if (result != FR_OK) return result;
        }
        snprintf(family, sizeof(family), "stage_targets_%s", regions[region]);
        snprintf(oldLeaf, sizeof(oldLeaf), "susamune_%s", family);
        snprintf(newLeaf, sizeof(newLeaf), "moonshine_%s", family);
        result = MigrateDataFamily(device, family, oldLeaf, newLeaf, pairSuffixes, 2);
        if (result != FR_OK) return result;
    }
    for (version = 1; version <= 9; ++version)
    {
        snprintf(family, sizeof(family), "il_stats_v%u", version);
        snprintf(oldLeaf, sizeof(oldLeaf), "susamune_%s", family);
        snprintf(newLeaf, sizeof(newLeaf), "moonshine_%s", family);
        result = MigrateDataFamily(device, family, oldLeaf, newLeaf, pairSuffixes, 2);
        if (result != FR_OK) return result;
    }
    for (version = 1; version <= 2; ++version)
    {
        snprintf(family, sizeof(family), "stage_playlists_v%u", version);
        snprintf(oldLeaf, sizeof(oldLeaf), "susamune_%s", family);
        snprintf(newLeaf, sizeof(newLeaf), "moonshine_%s", family);
        result = MigrateDataFamily(device, family, oldLeaf, newLeaf, pairSuffixes, 2);
        if (result != FR_OK) return result;
    }
    result = MigrateDataFamily(device, "progress_v1", "susamune_progress_v1",
        "moonshine_progress_v1", pairSuffixes, 2);
    if (result != FR_OK) return result;
    snprintf(path, sizeof(path), "%s:" MOONSHINE_DATA_ROOT MOONSHINE_CRASH_DIRECTORY, device);
    result = EnsureDataDirectory(path);
    if (result != FR_OK) return result;
    for (copy = 0; copy < 2; ++copy)
    {
        snprintf(family, sizeof(family), "crash_%c", 'a' + copy);
        snprintf(oldLeaf, sizeof(oldLeaf), "susamune_crash_%c", 'a' + copy);
        snprintf(newLeaf, sizeof(newLeaf), "crashes/moonshine_crash_%c", 'a' + copy);
        result = MigrateDataFamily(device, family, oldLeaf, newLeaf, crashSuffixes, 3);
        if (result != FR_OK) return result;
    }
    return FR_OK;
}

FRESULT MoonshineDataPrepare(const char *device)
{
    char path[64], temporary[64], marker[4];
    FIL file;
    UINT count;
    FRESULT result;
    if (device == NULL || (strcmp(device, "sd") != 0 && strcmp(device, "usb") != 0))
        return FR_INVALID_NAME;
    snprintf(path, sizeof(path), "%s:" DATA_MARKER, device);
    result = f_open_char(&file, path, FA_READ | FA_OPEN_EXISTING);
    if (result == FR_OK)
    {
        int valid = f_size(&file) == sizeof(marker);
        result = f_read(&file, marker, sizeof(marker), &count);
        if (f_close(&file) != FR_OK && result == FR_OK) result = FR_DISK_ERR;
        if (result != FR_OK) return result;
        if (valid && count == sizeof(marker) && memcmp(marker, "MSD1", sizeof(marker)) == 0)
            return FR_OK;
    }
    else if (result != FR_NO_FILE && result != FR_NO_PATH)
        return result;
    snprintf(path, sizeof(path), "%s:" MOONSHINE_DATA_ROOT, device);
    result = EnsureDataDirectory(path);
    if (result != FR_OK) return result;
    result = MigrateData(device);
    if (result != FR_OK) return result;
    snprintf(path, sizeof(path), "%s:" DATA_MARKER, device);
    snprintf(temporary, sizeof(temporary), "%s:" DATA_MARKER ".tmp", device);
    result = f_open_char(&file, temporary, FA_WRITE | FA_CREATE_ALWAYS);
    if (result != FR_OK) return result;
    result = f_write(&file, "MSD1", 4, &count);
    if (result == FR_OK && count != 4) result = FR_DISK_ERR;
    if (result == FR_OK) result = f_sync(&file);
    if (f_close(&file) != FR_OK && result == FR_OK) result = FR_DISK_ERR;
    if (result == FR_OK)
    {
        result = f_unlink_char(path);
        if (result == FR_NO_FILE || result == FR_NO_PATH) result = FR_OK;
        if (result == FR_OK) result = f_rename_char(temporary, path);
    }
    return result;
}

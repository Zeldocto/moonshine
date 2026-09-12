#include <stdio.h>

#include "SusamuneGhostDirs.h"
#include "ff_utf8.h"
#include "susamune/ghost_format.h"
#include "susamune/ghost_storage.h"
#include "susamune/data_paths.h"

static bool EnsureDirectory(const char *path)
{
	FRESULT ret = f_mkdir_char(path);
	return ret == FR_OK || ret == FR_EXIST;
}

bool SusamuneGhostEnsureDirectories(const char *device)
{
	static const char *const regions[] = { "jp", "us", "pal" };
	char path[72];
	u32 region;
	u32 profile;

	snprintf(path, sizeof(path), "%s:" MOONSHINE_DATA_ROOT MOONSHINE_GHOSTS_DIR "", device);
	if (!EnsureDirectory(path))
		return false;
	snprintf(path, sizeof(path), "%s:" MOONSHINE_DATA_ROOT MOONSHINE_GHOSTS_DIR "/%s", device,
	         SUSAMUNE_GHOST_IMPORT_DIRECTORY);
	if (!EnsureDirectory(path))
		return false;

	for (region = 0; region < sizeof(regions) / sizeof(regions[0]); region++)
	{
		snprintf(path, sizeof(path), "%s:" MOONSHINE_DATA_ROOT MOONSHINE_GHOSTS_DIR "/%s",
		         device, regions[region]);
		if (!EnsureDirectory(path))
			return false;

		for (profile = 0; profile < SUSAMUNE_GHOST_PROFILE_COUNT; profile++)
		{
			snprintf(path, sizeof(path), "%s:" MOONSHINE_DATA_ROOT MOONSHINE_GHOSTS_DIR "/%s/p%u",
			         device, regions[region], profile);
			if (!EnsureDirectory(path))
				return false;
		}
	}

	snprintf(path, sizeof(path), "%s:" MOONSHINE_DATA_ROOT MOONSHINE_GHOSTS_DIR "/%s", device,
	         SUSAMUNE_GHOST_SHARE_DIRECTORY);
	if (!EnsureDirectory(path))
		return false;
	for (region = 0; region < sizeof(regions) / sizeof(regions[0]); region++)
	{
		snprintf(path, sizeof(path), "%s:" MOONSHINE_DATA_ROOT MOONSHINE_GHOSTS_DIR "/%s/%s",
		         device, SUSAMUNE_GHOST_SHARE_DIRECTORY, regions[region]);
		if (!EnsureDirectory(path))
			return false;
		for (profile = 0; profile < SUSAMUNE_GHOST_PROFILE_COUNT; profile++)
		{
			snprintf(path, sizeof(path), "%s:" MOONSHINE_DATA_ROOT MOONSHINE_GHOSTS_DIR "/%s/%s/p%u",
			         device, SUSAMUNE_GHOST_SHARE_DIRECTORY, regions[region],
			         profile);
			if (!EnsureDirectory(path))
				return false;
		}
	}
	return true;
}

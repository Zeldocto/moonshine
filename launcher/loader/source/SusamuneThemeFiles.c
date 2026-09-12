#include <stdio.h>
#include <string.h>

#include "ff_utf8.h"
#include "SusamuneThemeFiles.h"
#include "susamune/data_paths.h"

FRESULT SusamuneThemeFindFile(char *out, size_t outSize, const char *device,
	const char *leaf, FILINFO *info)
{
	int written;
	FRESULT result;

	if (out == NULL || outSize == 0 || device == NULL || leaf == NULL || info == NULL)
		return FR_INVALID_NAME;
	if ((strcmp(device, "sd") != 0 && strcmp(device, "usb") != 0) ||
	    (strcmp(leaf, "background.png") != 0 && strcmp(leaf, "bgm.mp3") != 0))
		return FR_INVALID_NAME;
	written = snprintf(out, outSize, "%s:" MOONSHINE_DATA_ROOT MOONSHINE_THEME_DIR "/%s", device, leaf);
	if (written <= 0 || (size_t)written >= outSize)
		return FR_INVALID_NAME;
	result = f_stat_char(out, info);
	if (result == FR_NO_FILE || result == FR_NO_PATH)
	{
		char marker[64];
		FILINFO markerInfo;
		FRESULT markerResult;
		snprintf(marker, sizeof(marker), "%s:" MOONSHINE_DATA_ROOT "/.layout-v1", device);
		markerResult = f_stat_char(marker, &markerInfo);
		/* The first pre-IOS draw may precede migration; this lookup stays read-only. */
		if (markerResult == FR_NO_FILE || markerResult == FR_NO_PATH)
		{
			written = snprintf(out, outSize, "%s:/Moonshine_Theme/%s", device, leaf);
			if (written <= 0 || (size_t)written >= outSize)
				return FR_INVALID_NAME;
			return f_stat_char(out, info);
		}
	}
	return result;
}

FRESULT SusamuneThemeEnsureDirectory(const char *device)
{
	char path[64];
	FILINFO info;
	FRESULT result;

	if (device == NULL || (strcmp(device, "sd") != 0 && strcmp(device, "usb") != 0))
		return FR_INVALID_NAME;
	snprintf(path, sizeof(path), "%s:" MOONSHINE_DATA_ROOT MOONSHINE_THEME_DIR "", device);
	result = f_stat_char(path, &info);
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

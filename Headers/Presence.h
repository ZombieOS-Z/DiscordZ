#ifndef DISCORDZ_PRESENCE_H
#define DISCORDZ_PRESENCE_H

#include <zsharp_c.h>

#ifdef __cplusplus
extern "C" {
#endif

int DiscordZ_SetPresence(
    const char *details,
    const char *state,
    const char *clientName
);

int DiscordZ_ClearPresence(
    const char *clientName
);
int DiscordZ_RegisterPresence(ZSharpCSyntaxRegistry *registry,
                             char *error, size_t error_size);
int DiscordZ_CallPresence(uint32_t abi_version, const char *function,
    const ZSharpCValue *arguments, size_t argument_count,
    ZSharpCValue *result, char *error, size_t error_size);

#ifdef __cplusplus
}
#endif

#endif

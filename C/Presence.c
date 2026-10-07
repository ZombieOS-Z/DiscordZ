#include "Headers/Presence.h"
#include <zsharp_c.h>
#include <string.h>

int DiscordZ_RegisterPresence(ZSharpCSyntaxRegistry *registry, char *error, size_t error_size)
{
    return registry->add_statement(registry->context, "Discord.setPresence({detail}, {state}, {clientName})", "discord_setPresence", error, error_size) &&
    registry->add_statement(registry->context, "Discord.clearPresence({clientName})", "discord_clearPresence", error, error_size);
}

int DiscordZ_CallPresence(uint32_t abi_version, const char *function, const ZSharpCValue *arguments, size_t argument_count, ZSharpCValue *result, char *error, size_t error_size)
{
    if (abi_version != ZSHARP_C_ABI_VERSION) {
        return 0;
    }

    if (strcmp(function, "discord_setPresence") == 0) {
        if (argument_count != 3 || arguments[0].type != ZSHARP_C_TEXT || arguments[1].type != ZSHARP_C_TEXT || arguments[2].type != ZSHARP_C_TEXT) {
            return 0;
        }

        if(!DiscordZ_SetPresence(arguments[0].text, arguments[1].text, arguments[2].text)) {
            return 0;
        }

        result->type = ZSHARP_C_NULL;
        return 1;
    }
    if (strcmp(function, "discord_clearPresence") == 0 && argument_count == 1 &&
        arguments[0].type == ZSHARP_C_TEXT) {
        if (!DiscordZ_ClearPresence(arguments[0].text)) return 0;
        result->type = ZSHARP_C_NULL;
        return 1;
    }
    return 0;
}

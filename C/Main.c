#include "Headers/Main.h"
#include "Headers/Presence.h"
#include "Headers/BotExtensions.h"
#include <zsharp_c.h>
#include <string.h>

ZSHARP_C_EXPORT int zsharp_c_register_v1(ZSharpCSyntaxRegistry *registry, char *error, size_t error_size) {
        return registry->add_statement(registry->context,
            "Discord.Init({appId}, {clientName})", "discord_init", error, error_size) &&
            registry->add_statement(registry->context,
            "Discord.Shutdown({clientName})", "discord_shutdown", error, error_size) &&
            registry->add_expression(registry->context,
            "Discord.client({clientName})", "discord_client_name", error, error_size) &&
            registry->add_expression(registry->context,
            "Discord.client", "discord_client", error, error_size) &&
            DiscordZ_RegisterPresence(registry, error, error_size) &&
            DiscordZ_RegisterBot(registry, error, error_size);
    }

ZSHARP_C_EXPORT int zsharp_c_call_v1(uint32_t abi_version, const char *function, const ZSharpCValue *arguments, size_t argument_count, ZSharpCValue *result, char *error, size_t error_size)
{
    if (abi_version != ZSHARP_C_ABI_VERSION) {
        return 0;
    }
    if (strncmp(function, "discord_event_", 14) == 0)
        return DiscordZ_CallEvents(function, arguments, argument_count, result, error, error_size);
    if (strncmp(function, "discord_webhook_", 16) == 0)
        return DiscordZ_CallWebhooks(function, arguments, argument_count, result, error, error_size);

    if (strcmp(function, "discord_init") == 0) {
        if (argument_count != 2 || arguments[0].type != ZSHARP_C_TEXT || arguments[1].type != ZSHARP_C_TEXT) {
            return 0;
        }

        if(!DiscordZ_Init(arguments[0].text, arguments[1].text)) {
            return 0;
        }

        result->type = ZSHARP_C_NULL;
        return 1;
    }

    if (strcmp(function, "discord_client_name") == 0) {
        if (argument_count != 1 || arguments[0].type != ZSHARP_C_TEXT) {
            return 0;
        }

        result->type = ZSHARP_C_STATUS;
        result->number = DiscordZ_ClientExists(arguments[0].text);
        return 1;
    }
    if (strcmp(function, "discord_shutdown") == 0) {
        if (argument_count == 1 && arguments[0].type == ZSHARP_C_TEXT) {
        DiscordZ_Shutdown(arguments[0].text);
        result->type = ZSHARP_C_NULL;
        return 1;
     }
    }

    if (strcmp(function, "discord_client") == 0) {
        if (argument_count != 0) {
            return 0;
        }

        result->type = ZSHARP_C_STATUS;
        result->number = DiscordZ_HasClient();
        return 1;
    }

    if (strncmp(function, "discord_bot_", 12) == 0) {
        return DiscordZ_CallBot(abi_version, function, arguments, argument_count, result, error, error_size);
    }

    return DiscordZ_CallPresence(abi_version, function, arguments, argument_count, result, error, error_size);
    return 0;
}

ZSHARP_C_EXPORT int zsharp_c_register_v2(ZSharpCSyntaxRegistryV2 *registry, char *error, size_t size) {
    return zsharp_c_register_v1(&registry->v1, error, size) &&
        DiscordZ_RegisterEvents(registry, error, size) &&
        DiscordZ_RegisterWebhooks(registry, error, size);
}

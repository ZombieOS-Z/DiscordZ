#include "Headers/Main.h"
#include "Headers/Bot.h"
#include <zsharp_c.h>
#include <string.h>
#include <stdio.h>

extern const char* DiscordZ_BotError(void);
extern int DiscordZ_BotSelfTest(void);

static int bot_failure(char *error, size_t error_size, const char *fallback) {
    const char *detail = DiscordZ_BotError();
    if (error && error_size) snprintf(error, error_size, "%s", detail && *detail ? detail : fallback);
    return 0;
}

int DiscordZ_RegisterBot(ZSharpCSyntaxRegistry *registry, char *error, size_t error_size) {
        return registry->add_statement(registry->context,
            "Discord.Bot.Login({token})", "discord_bot_login", error, error_size) &&
            registry->add_statement(registry->context,
            "Discord.Bot.Shutdown", "discord_bot_shutdown", error, error_size) &&
            registry->add_statement(registry->context,
            "Discord.Bot.Status({status}, {activity}, {details})", "discord_bot_status", error, error_size);
    }

int DiscordZ_CallBot(uint32_t abi_version, const char *function, const ZSharpCValue *arguments, size_t argument_count, ZSharpCValue *result, char *error, size_t error_size)
{
    if (abi_version != ZSHARP_C_ABI_VERSION) {
        if (error && error_size) snprintf(error, error_size, "DiscordZ C ABI mismatch");
        return 0;
    }

    printf("[DiscordZ (C)] Call received for function: %s\n", function);

    if (strcmp(function, "discord_bot_self_test") == 0) {
        if (argument_count != 0) return 0;
        if (!DiscordZ_BotSelfTest()) return bot_failure(error, error_size, "Bot self-test failed");
        result->type = ZSHARP_C_STATUS; result->number = 1;
        return 1;
    }

    if (strcmp(function, "discord_bot_login") == 0) {
        if (argument_count != 1 || arguments[0].type != ZSHARP_C_TEXT) {
            if (error && error_size) snprintf(error, error_size, "Bot.Login requires one text token");
            return 0;
        }

        printf("[DiscordZ (C)] Attempting to log in to bot.\n");

        if(!DiscordZ_BotLogin(arguments[0].text)) {
            return bot_failure(error, error_size, "Bot login startup failed");
        }

        printf("[DiscordZ (C)] Bot connection started; DISCORDZ_READY confirms login.\n");

        result->type = ZSHARP_C_NULL;
        return 1;
    }

    if (strcmp(function, "discord_bot_shutdown") == 0) {
        if (argument_count != 0) {
            return 0;
        }
        if (!DiscordZ_BotShutdown()) return bot_failure(error, error_size, "Bot shutdown failed");
        result->type = ZSHARP_C_NULL;
        return 1;
    }

    if (strcmp(function, "discord_bot_status") == 0) {
        if (argument_count != 3 || arguments[0].type != ZSHARP_C_TEXT || arguments[1].type != ZSHARP_C_TEXT || arguments[2].type != ZSHARP_C_TEXT) {
            return 0;
        }

        if (!DiscordZ_BotStatus(arguments[0].text, arguments[1].text, arguments[2].text))
            return bot_failure(error, error_size, "Bot status update failed");
        result->type = ZSHARP_C_NULL;
        return 1;
    }
    return 0;
}

#include "Headers/BotExtensions.h"
#include <stdio.h>

int DiscordZ_RegisterWebhooks(ZSharpCSyntaxRegistryV2 *registry, char *error, size_t size) {
    return registry->add_declaration(registry->v1.context, "Webhook", 2, "discord_webhook_bind", error, size) &&
        registry->v1.add_expression(registry->v1.context, "Discord.Webhook({name})", "discord_webhook_reference", error, size);
}

int DiscordZ_CallWebhooks(const char *function, const ZSharpCValue *arguments, size_t count,
    ZSharpCValue *result, char *error, size_t size) {
    int ok = DiscordZ_WebhooksNative(function, arguments, count, result);
    if (!ok) snprintf(error, size, "%s", DiscordZ_BotError());
    return ok;
}

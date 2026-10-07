#include "Headers/BotExtensions.h"
#include <string>
#include <cstring>

extern "C" int DiscordZ_WebhooksNative(const char* function, const ZSharpCValue* args,
    size_t count, ZSharpCValue* result) {
    static thread_local std::string reference;
    if (!strcmp(function, "discord_webhook_bind"))
        return DiscordZ_PythonCall("Webhooks", "bind", args, count, result);
    if (!strcmp(function, "discord_webhook_reference") && count == 1 && args[0].type == ZSHARP_C_TEXT) {
        ZSharpCValue ignored;
        if (!DiscordZ_PythonCall("Webhooks", "exists", args, count, &ignored) || !ignored.number) return 0;
        reference = "@discordz-webhook:"; reference += args[0].text;
        result->type = ZSHARP_C_TEXT; result->text = reference.c_str(); return 1;
    }
    return 0;
}

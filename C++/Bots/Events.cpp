#include "Headers/BotExtensions.h"
#include <vector>
#include <string>
#include <mutex>
#include <cstring>
#include <cstdio>

static std::recursive_mutex eventMutex;
static thread_local uint64_t currentEvent;
static thread_local std::string target;
static thread_local std::vector<std::string> texts;
static thread_local std::vector<ZSharpCValue> values;

extern "C" int DiscordZ_EventsNative(const char* function, const ZSharpCValue* args,
    size_t count, ZSharpCValue* result) {
    const char* prefix = "@discordz-webhook:";
    if (!strcmp(function, "discord_event_offline_start") && count == 0)
        return DiscordZ_PythonCall("Events", "start_offline", nullptr, 0, result);
    if (!strcmp(function, "discord_event_offline_messages_start") && count == 0)
        return DiscordZ_PythonCall("Events", "start_messages_offline", nullptr, 0, result);
    if (!strcmp(function, "discord_event_message"))
        return DiscordZ_PythonCall("Events", "bind_message", args, count, result);
    if (!strcmp(function, "discord_event_prefix"))
        return DiscordZ_PythonCall("Events", "set_prefixes", args, count, result);
    if (!strcmp(function, "discord_event_permission"))
        return DiscordZ_PythonCall("Events", "set_permissions", args, count, result);
    if (!strcmp(function, "discord_event_bot_permission"))
        return DiscordZ_PythonCall("Events", "set_bot_permissions", args, count, result);
    if (!strcmp(function, "discord_event_cooldown"))
        return DiscordZ_PythonCall("Events", "set_cooldown", args, count, result);
    if (!strcmp(function, "discord_event_delete")) {
        if (count != 2 || args[0].type != ZSHARP_C_TEXT || args[1].type != ZSHARP_C_TEXT) return 0;
        ZSharpCValue inputs[3] = {};
        inputs[0].type = ZSHARP_C_NUMBER; inputs[0].number = (double)currentEvent;
        inputs[1] = args[0]; inputs[2] = args[1];
        return DiscordZ_PythonCall("Events", "delete_message", inputs, 3, result);
    }
    bool replyToExecutor = !strcmp(function, "discord_event_print_reply") ||
        !strcmp(function, "discord_event_print_webhook_reply");
    if (replyToExecutor || !strcmp(function, "discord_event_print") || !strcmp(function, "discord_event_print_webhook")) {
        if (!count || count > 2 || args[0].type != ZSHARP_C_TEXT ||
            (count == 2 && args[1].type != ZSHARP_C_TEXT)) return 0;
        const char* reference = args[count - 1].text;
        if (!strncmp(reference, prefix, strlen(prefix))) {
            ZSharpCValue inputs[4] = {};
            inputs[0] = args[count - 1];
            inputs[1] = count == 2 ? args[0] : ZSharpCValue{};
            inputs[2].type = ZSHARP_C_NUMBER; inputs[2].number = (double)currentEvent;
            inputs[0].text += strlen(prefix);
            inputs[3].type = ZSHARP_C_STATUS; inputs[3].number = replyToExecutor;
            return DiscordZ_PythonCall("Webhooks", "send", inputs, 4, result);
        }
        if (count != 1) return 0;
        ZSharpCValue inputs[3] = {};
        inputs[0].type = ZSHARP_C_NUMBER; inputs[0].number = (double)currentEvent;
        inputs[1] = args[0];
        inputs[2].type = ZSHARP_C_STATUS; inputs[2].number = replyToExecutor;
        return DiscordZ_PythonCall("Events", "reply", inputs, 3, result);
    }
    const char* kind = !strcmp(function, "discord_event_hybrid") ? "hybrid" :
        !strcmp(function, "discord_event_slash") ? "slash" : !strcmp(function, "discord_event_msg") ? "msg" : nullptr;
    if (!kind || count < 2 || count % 2) return 0;
    for (size_t i = 0; i < count; i++) if (args[i].type != ZSHARP_C_TEXT) return 0;
    std::vector<ZSharpCValue> inputs(count + 1);
    inputs[0].type = ZSHARP_C_TEXT; inputs[0].text = kind;
    for (size_t i = 0; i < count; i++) inputs[i + 1] = args[i];
    return DiscordZ_PythonCall("Events", "bind", inputs.data(), inputs.size(), result);
}

extern "C" ZSHARP_C_EXPORT int zsharp_c_service_v1(int operation, ZSharpCEventV1* event,
    char* error, size_t size) {
    ZSharpCValue result = {};
    if (!DiscordZ_PythonReady()) return 0;
    if (operation == ZSHARP_C_SERVICE_ACTIVE) {
        if (!DiscordZ_PythonCall("Bot", "active", nullptr, 0, &result)) {
            snprintf(error, size, "%s", DiscordZ_BotError()); return -1;
        }
        bool botActive = result.number != 0;
        if (!DiscordZ_PythonCall("Events", "active", nullptr, 0, &result)) {
            snprintf(error, size, "%s", DiscordZ_BotError()); return -1;
        }
        return botActive || result.number != 0;
    }
    if (operation == ZSHARP_C_SERVICE_SHUTDOWN) {
        return DiscordZ_PythonCall("Bot", "shutdown", nullptr, 0, &result);
    }
    if (operation == ZSHARP_C_SERVICE_COMPLETE) {
        ZSharpCValue inputs[2] = {};
        inputs[0].type = ZSHARP_C_NUMBER; inputs[0].number = (double)event->id;
        inputs[1].type = ZSHARP_C_TEXT; inputs[1].text = error;
        int ok = DiscordZ_PythonCall("Events", "complete", inputs, 2, &result);
        currentEvent = 0; texts.clear(); values.clear(); target.clear();
        eventMutex.unlock(); return ok;
    }
    if (operation != ZSHARP_C_SERVICE_POLL) return -1;
    eventMutex.lock();
    {
        ZSharpCValue owner = {}; owner.type = ZSHARP_C_TEXT; owner.text = event->target;
        if (!DiscordZ_PythonCall("Events", "native_poll", &owner, 1, &result)) goto failed;
    }
    currentEvent = (uint64_t)result.number;
    if (!currentEvent) { eventMutex.unlock(); return 0; }
    event->id = currentEvent;
    if (!DiscordZ_PythonCall("Events", "native_target", nullptr, 0, &result)) goto failed;
    target = result.text;
    if (!DiscordZ_PythonCall("Events", "native_count", nullptr, 0, &result) || result.number > 64) goto failed;
    values.resize((size_t)result.number); texts.resize(values.size());
    for (size_t i = 0; i < values.size(); i++) {
        ZSharpCValue index = {}; index.type = ZSHARP_C_NUMBER; index.number = (double)i;
        if (!DiscordZ_PythonCall("Events", "native_argument", &index, 1, &values[i])) goto failed;
        if (values[i].type == ZSHARP_C_TEXT) { texts[i] = values[i].text; values[i].text = texts[i].c_str(); }
    }
    event->target = target.c_str(); event->arguments = values.data(); event->argument_count = values.size();
    return 1; // Hold the lock until COMPLETE; another ZVM task cannot steal this context.
failed:
    snprintf(error, size, "%s", DiscordZ_BotError()); currentEvent = 0;
    eventMutex.unlock(); return -1;
}

#include "Headers/BotExtensions.h"
#include <stdio.h>
#include <string.h>

int DiscordZ_RegisterEvents(ZSharpCSyntaxRegistryV2 *registry, char *error, size_t size) {
    ZSharpCSyntaxRegistry *v1 = &registry->v1;
    return registry->add_declaration(v1->context, "discord_command_hybrid", 1, "discord_event_hybrid", error, size) &&
        registry->add_declaration(v1->context, "discord_command_slash", 1, "discord_event_slash", error, size) &&
        registry->add_declaration(v1->context, "discord_command_msg", 1, "discord_event_msg", error, size) &&
        registry->add_declaration(v1->context, "discord_event_message", 1, "discord_event_message", error, size) &&
        registry->add_declaration(v1->context, "Discord.Prefix", ZSHARP_C_FUNCTION_OPTION, "discord_event_prefix", error, size) &&
        registry->add_declaration(v1->context, "Discord.RequirePermission", ZSHARP_C_FUNCTION_OPTION, "discord_event_permission", error, size) &&
        registry->add_declaration(v1->context, "Discord.RequireBotPermission", ZSHARP_C_FUNCTION_OPTION, "discord_event_bot_permission", error, size) &&
        registry->add_declaration(v1->context, "Discord.Cooldown", ZSHARP_C_FUNCTION_DURATION_OPTION, "discord_event_cooldown", error, size) &&
        v1->add_statement(v1->context, "Discord.Bot.DeleteUserMessage({channel}, {message})", "discord_event_delete", error, size) &&
        v1->add_statement(v1->context, "Discord.Print({text}).replyToExecutor", "discord_event_print_reply", error, size) &&
        v1->add_statement(v1->context, "Discord.Print({text}, {webhook}).replyToExecutor", "discord_event_print_webhook_reply", error, size) &&
        v1->add_statement(v1->context, "Discord.Print({text})", "discord_event_print", error, size) &&
        v1->add_statement(v1->context, "Discord.Print({text}, {webhook})", "discord_event_print_webhook", error, size);
}

int DiscordZ_CallEvents(const char *function, const ZSharpCValue *arguments, size_t count,
    ZSharpCValue *result, char *error, size_t size) {
    int ok = DiscordZ_EventsNative(function, arguments, count, result);
    if (!ok) snprintf(error, size, "%s", DiscordZ_BotError());
    return ok;
}

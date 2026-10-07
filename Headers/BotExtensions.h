#ifndef DISCORDZ_BOT_EXTENSIONS_H
#define DISCORDZ_BOT_EXTENSIONS_H
#include <zsharp_c.h>
#ifdef __cplusplus
extern "C" {
#endif
int DiscordZ_RegisterEvents(ZSharpCSyntaxRegistryV2 *, char *, size_t);
int DiscordZ_RegisterBot(ZSharpCSyntaxRegistry *, char *, size_t);
int DiscordZ_CallBot(uint32_t, const char *, const ZSharpCValue *, size_t, ZSharpCValue *, char *, size_t);
int DiscordZ_RegisterWebhooks(ZSharpCSyntaxRegistryV2 *, char *, size_t);
int DiscordZ_CallEvents(const char *, const ZSharpCValue *, size_t, ZSharpCValue *, char *, size_t);
int DiscordZ_CallWebhooks(const char *, const ZSharpCValue *, size_t, ZSharpCValue *, char *, size_t);
int DiscordZ_EventsNative(const char *, const ZSharpCValue *, size_t, ZSharpCValue *);
int DiscordZ_WebhooksNative(const char *, const ZSharpCValue *, size_t, ZSharpCValue *);
int DiscordZ_PythonCall(const char *, const char *, const ZSharpCValue *, size_t, ZSharpCValue *);
int DiscordZ_PythonReady(void);
const char *DiscordZ_BotError(void);
#ifdef __cplusplus
}
#endif
#endif

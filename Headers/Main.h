#ifndef DISCORDZ_MAIN_H
#define DISCORDZ_MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

int DiscordZ_Init(
    const char *applicationId,
    const char *clientName
);

int DiscordZ_Shutdown(
    const char *clientName
);

void DiscordZ_Tick(void);
int DiscordZ_HasClient(void);
int DiscordZ_ClientExists(const char *clientName);

#ifdef __cplusplus
}
namespace discordpp { class Client; }
discordpp::Client* DiscordZ_GetClient(const char* clientName);
#endif

#endif

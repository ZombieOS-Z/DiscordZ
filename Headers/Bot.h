#ifdef __cplusplus
extern "C" {
#endif

int DiscordZ_BotLogin(const char* token);
int DiscordZ_BotShutdown();
int DiscordZ_BotStatus(
    const char* status,
    const char* activity,
    const char* details
);

#ifdef __cplusplus
}
#endif
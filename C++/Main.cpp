#include "Headers/Main.h"
#define DISCORDPP_IMPLEMENTATION
#include <Discord/discordpp.h>

#include <cstdint>
#include <memory>
#include <string>
#include <unordered_map>
#include <windows.h>

static std::unordered_map<
    std::string,
    std::unique_ptr<discordpp::Client>
> clients;

int DiscordZ_HasClient()
{
    return clients.empty() ? 0 : 1;
}

int DiscordZ_ClientExists(const char* clientName)
{
    if (!clientName || !*clientName)
        return 0;

    return clients.find(clientName) != clients.end()
        ? 1
        : 0;
}

int DiscordZ_Shutdown(const char* clientName)
{
    if (!clientName || !*clientName)
        return 0;
    return clients.erase(clientName) ? 1 : 0;
}

int DiscordZ_Init(const char* applicationId, const char* clientName)
{
    if (!applicationId || !*applicationId || !clientName || !*clientName || DiscordZ_ClientExists(clientName)) {
        return 0;
    }
    
    uint64_t aid = std::stoull(applicationId);

    auto newClient = std::make_unique<discordpp::Client>();
    newClient->SetApplicationId(aid);
    newClient->SetGameWindowPid(GetCurrentProcessId());

    clients[clientName] = std::move(newClient);
    return 1;
}

discordpp::Client* DiscordZ_GetClient(const char* clientName)
{
    if (!clientName || !*clientName)
        return nullptr;

    auto it = clients.find(clientName);
    if (it == clients.end())
        return nullptr;

    return it->second.get();
}

void DiscordZ_Tick()
{
    discordpp::RunCallbacks();
}
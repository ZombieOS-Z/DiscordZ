#include "Headers/Main.h"
#include "Headers/Presence.h"
#include <Discord/discordpp.h>
#include <iostream>
#include <string>

int DiscordZ_SetPresence(
    const char* details,
    const char* state,
    const char* clientName
)
{
    discordpp::Client* client =
        DiscordZ_GetClient(clientName);

    if (!client)
        return 0;

    discordpp::Activity activity;

    activity.SetType(
        discordpp::ActivityTypes::Playing
    );

    if (details && *details)
        activity.SetDetails(details);

    if (state && *state)
        activity.SetState(state);

    std::string clientNameCopy = clientName;

    client->UpdateRichPresence(
        std::move(activity),
        [clientNameCopy](discordpp::ClientResult result) {
            if (result.Successful()) {
                std::cout << "[DiscordZ] Rich Presence updated.\n";
            }
            else {
                std::cerr << "[DiscordZ] Failed to update Rich Presence.";
                std::cerr << "Client: "
                          << clientNameCopy
                          << '\n';
            }
        }
    );
    return 1;
}

int DiscordZ_ClearPresence(const char* clientName)
{
    discordpp::Client* client = DiscordZ_GetClient(clientName);

    if (!client) {
        return 0;
    }

    client->ClearRichPresence();

    return 1;
}

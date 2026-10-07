#ifndef DISCORDZ_MAIN_INTERNAL_HPP
#define DISCORDZ_MAIN_INTERNAL_HPP

#include <Discord/discordpp.h>

discordpp::Client *DiscordZ_GetClient(
    const char *clientName
);

#endif
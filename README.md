# DiscordZ

DiscordZ is the official package for connecting **Z# and Discord**. Write bots,
commands, automatic message moderation, rich embeds, and desktop Rich Presence
in Z#. C registers the Z# syntax, C++ handles native integration, and Python
with discord.py handles bots.

## Requirements

- **Z# 1.2.1.0 or newer.** Earlier releases lack the required C declarations,
  callback and service-lifetime features. This Z# version is currently unreleased.
- The current native build targets **Windows x64**. Other platforms need their
  own compatible native modules and dependencies.
- Bots use the selected ZVM's bundled **Python 3.13** and DiscordZ's prepared
  dependencies; a correctly prepared release does not need separate Python.
- Rich Presence uses the Discord Social SDK and Discord desktop client.

Public use requires a released Z# 1.2.1.0 and a published DiscordZ package.
The version below matches this checkout, not an already-published Store release.

## Installation

Add the desired published release to `project.zsettings`:

```javascript
Dependencies (
 discordz:0.0.0.0
):
```

Replace the version with your selected release. Z# installs dependencies when
running a project script or packaging an app/game, using a matching local
`.zpackage` in `Dependencies/` before downloading from ZOS Store.

Import the module in each room that uses DiscordZ:

```javascript
import c:discordz.C.Main():
```

Use that explicit import: wildcard C imports currently do not load its syntax.

## Quick start: bots

Create an application in the [Discord Developer Portal](https://discord.com/developers/applications),
configure its bot, and invite it to a test server with the `bot` and
`applications.commands` scopes. Enable **Message Content Intent** for message
commands or message events. Give the bot only the permissions it needs.

Create a local `.env` containing only the raw bot token, not `TOKEN=...`.
Never commit or distribute it.

```javascript
zsharp = type.script

noticed room Bot[] (
 import c:discordz.C.Main():

 noticed discord_command_hybrid Ping[] (
  Discord.Prefix("?", "!", "*"):
  Discord.Cooldown(5s):
  Discord.Print("Pong!").replyToExecutor:
 )

 noticed brain Start[] (
  Discord.Bot.Login(File.read(".env")):
  Discord.Bot.Status("online", "playing", "Made with Z#"):
 )

 noticed brain Shutdown[] (
  Discord.Bot.Shutdown:
 )
)
```

From the project directory, run `zsharp run Bot.zsharp`. Login is asynchronous;
`DISCORDZ_READY` confirms connection, not Login's return. Status updates wait for
readiness. The active bot keeps its host alive after Start returns. Shutdown or
closing the host ends it. Discord controls slash-command sync availability.

## Commands and replies

| Declaration | Invocation |
| --- | --- |
| `discord_command_slash` | `/command` |
| `discord_command_msg` | Prefix command, such as `!command` |
| `discord_command_hybrid` | Both forms |

Parameters use normal Z# `text`, `number`, and `status` declarations. Discord
command/option names are lowercased; Z# parameter bindings retain their spelling.

`Discord.Prefix("?", "!", "*"):` configures a command's message prefixes.
At least one nonempty literal text is required when present, with no fixed
prefix-count limit. Omit it for `!`; slash-only commands cannot declare prefixes.

`Discord.Print("text"):` sends normally in the callback's channel.
`.replyToExecutor` references the triggering message without pinging its author.
Slash callbacks respond through their interaction.

## Permissions and cooldowns

Put configuration before executable statements:

```javascript
noticed discord_command_slash DeleteMessage[text ChannelID, text MessageID] (
 Discord.RequirePermission("manage_messages"):
 Discord.RequireBotPermission("manage_messages"):
 Discord.Cooldown(5s):
 Discord.Bot.DeleteUserMessage(ChannelID, MessageID):
)
```

Permission names follow discord.py, such as `administrator` and
`manage_messages`. Multiple names may be supplied; all are required. Checks use
effective channel permissions and report missing permissions, but cannot grant
them. Deletion checks the bot's Manage Messages permission automatically.

Cooldowns use `wait`-style literals: `5s`, `5ms`, `0.5s`, or `0ms` to disable.
They are per user per command, shared between a hybrid command's two forms.
Discord IDs must be **text**, so large IDs keep all their digits.

## Message events and moderation

```javascript
noticed discord_event_message MessageReceived[
 text userMessage, text channelID, text messageID
] (
 if[Regex.test(userMessage, "\\bBLOCKED_WORD\\b", "i")] (
  Discord.Bot.DeleteUserMessage(channelID, messageID):
 ) else (
 )
)
```

Exactly three text parameters receive message contents, channel ID and message
ID, in that order. New non-bot messages trigger the event automatically;
bot/webhook messages are ignored to prevent loops. Event-only bots work too.

Replace the harmless BLOCKED_WORD pattern with your filter. `Regex.test` returns
alive/dead; `Regex.matches` returns an array. Test for false positives before
enabling deletion. Enable Message Content Intent and Manage Messages.

Events run before prefix commands; a deleted triggering message does not proceed
to other handlers or commands. Deletion is limited to the callback's server,
not DMs. The queue is bounded to 256 events with a 120-second callback timeout;
moderation is not guaranteed under overload.

## Rich embeds

Inside a room, define a named, URL-free template:

```javascript
Webhook Announcement (
 content: "Hello from DiscordZ!":
 embeds (
  Main (
   title: "An announcement":
   description: "This embed was written in Z#.":
   color: #3366FF:
  )
 )
):
```

Send it inside a command or message event:

```javascript
Discord.Print(Discord.Webhook("Announcement")):
Discord.Print("Custom content", Discord.Webhook("Announcement")):
```

Templates send as the bot; they do not automatically create server webhooks or
require webhook URLs. Author, footer, fields, images, thumbnails and mention
controls are supported. See [Bot.zsharp](Z%23%20Examples/Bot.zsharp).

## Desktop Rich Presence

Use a Discord application's Application ID—not a bot token:

```javascript
zsharp = type.script

noticed room Presence[] (
 import c:discordz.C.Main():

 noticed brain Start[] (
  Discord.Init("YOUR_APPLICATION_ID", "main"):
  Discord.setPresence("Exploring the world", "Chapter 1", "main"):
  wait(30s):
 )

 noticed brain Shutdown[] (
  Discord.Shutdown("main"):
 )
)
```

Detail is the top line; state is the bottom line. Client names identify your
initialized clients. `Discord.clearPresence("main"):` clears a presence;
`Discord.client` and `Discord.client("main")` test clients. Keep the host running
while you want the presence active.

## Building from source

The current build uses Visual Studio 2022 C++ tools, Python 3.13 development
headers/import library, Z#'s C headers, and the Discord SDK files in `Discord/`.
Defaults in Build.ps1 are local development paths; supply your own:

```powershell
.\Build.ps1 `
 -ZSharpHeaders "C:\path\to\ZSharp\native\include" `
 -PythonRoot "C:\path\to\Python313" `
 -ZVM "C:\path\to\ZVM\bin\zsharp.exe"
```

The compiler-setup path currently assumes Visual Studio Community's standard
installation location; adjust it for another installation. The script builds
`C/Main.zc.dll`, copies the Discord runtime DLL, prepares `Python/vendor`, and
runs offline smoke tests. Use `-SkipDependencyInstall` only when dependencies
are already prepared. Bot execution uses Python beside the selected ZVM.

## Publishing safely

The included `.zignore` excludes `.env`, examples, build artifacts, SDK build
inputs, and Python caches from runtime packages. These stay available in the
source repository. Git's `.gitignore` is separate: only `.zignore` controls the
Z# package contents. Use a ZVM build with `.zignore` support; older builds do not
apply these rules.

For an extra release-safety check, prepare a separate clean folder containing the intended source,
`project.zsettings`, native modules/runtime DLLs, Python files/dependencies, and
third-party notices. Exclude tokens, `.env`, private configuration, object files,
caches and unrelated build artifacts. Choose the release number in settings:

```powershell
zsharp package pack "C:\path\to\DiscordZ-release" DiscordZ
```

The result is `Packages/DiscordZ.zpackage` inside that release project.
Dependency packages contain readable source by default; no unbytecoded flag is
needed. Inspect the archive before uploading. Publish Z# 1.2.1.0 before asking
users to install DiscordZ.

Before making the source public, add your intended license for DiscordZ's own
code and retain applicable third-party license/SDK notices. This checkout does
not currently contain a top-level DiscordZ license file.

## Examples and future work

- [Bot example](Z%23%20Examples/Bot.zsharp)
- [Presence example](Z%23%20Examples/Presences.zsharp)
- [Detailed commands, events and embeds](BOT_COMMANDS.md)

This first version focuses on bots and presences. Buttons, dropdowns, modals,
voice/audio, additional events and broader moderation actions are future work.
Offline tests cover source and bytecode integration, but do not replace testing
permissions and behavior in your own server.

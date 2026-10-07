# DiscordZ commands and webhooks

## Permissions, cooldowns and deletion

Put these declarations at the beginning of any message, slash or hybrid command:

```javascript
Discord.RequirePermission("manage_messages"):
Discord.RequireBotPermission("manage_messages"):
Discord.Cooldown(5s):
```

Permission names use discord.py's names (for example `administrator`,
`manage_messages`, `ban_members`). Multiple names can be supplied and all are
required. Unknown names are rejected. Checks use current effective channel
permissions, including channel overrides; administrator permissions are honored.
Permission-restricted commands cannot run in DMs. Rejections name the missing
permissions; slash rejections are ephemeral. This cannot grant permissions—an
authorized server administrator must change the role/channel settings.

Cooldowns use the same literal units as `wait`: `5s`, `5ms`, `0.5s`, or `0ms`
(disabled). They apply per user per command, shared between a hybrid command's
slash and message forms, across servers. A rejected permission check does not
consume the cooldown. Cooldowns reset when the host stops. Declare each kind of
configuration at most once, before executable statements.

`Discord.Bot.DeleteUserMessage(ChannelID, MessageID):` deletes one message in the
active command's server. IDs must be decimal **text**, not floating-point numbers.
The action checks the bot's Manage Messages permission in the target channel
even without a RequireBotPermission declaration. Declared user permissions are
also rechecked for that channel. Missing permissions or an already-deleted message
produce a readable error rather than deleting anything or stopping the bot.
An unsuccessful deletion returns from the action; subsequent command statements
still execute, so do not unconditionally announce successful deletion.

Deletion is available inside command callbacks and message events.

## New-message events and automatic moderation

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

Exactly three text parameters are required, in that order: message contents,
channel ID, message ID. Their variable names are your choice. IDs preserve all
digits. Event bodies run automatically for new non-bot messages—including DMs
and messages that are not commands—and do not run at startup. Bot/webhook
messages are ignored to avoid response loops. Edits, deletions, reactions and
member events are not covered by this declaration.

Enable **Message Content Intent** in the developer portal. DiscordZ enables
the corresponding client intent when message handlers exist. An event-only
bot works without declaring any commands. Call Login normally in Start.

Handlers run through the same ZVM callback queue, before prefix commands. If
a handler successfully deletes the triggering message (or it is already gone),
remaining handlers and prefix command processing for that message are skipped.
Otherwise all registered handlers run in registration order and commands still
work. The queue has 256 entries and a 120-second callback timeout; overflow or
timeout reports a local diagnostic without logging message contents. This is
bounded processing, not a guarantee to moderate every message under overload.

`Discord.Print(...)` sends in the event's channel; `.replyToExecutor` references
the triggering message. URL-free embed templates work here too. DeleteUserMessage
checks the bot's permissions even in automatic moderation. It cannot delete DM
messages or messages in a different server from the triggering event.

`Regex.test` returns alive/dead and is the correct form for an if condition.
`Regex.matches` returns an array, not a status. Replace the harmless BLOCKED_WORD
pattern with your filter, and test for false positives before enabling deletion.

Requires the Z# **1.2.1.0 development build**, its bundled Python 3.13 runtime,
and `C/Main.zc.dll` rebuilt using `Build.ps1`. The build compiles the Main,
Presence, Bot, Events and Webhooks C/C++ sources and checks the Python dependencies.
`Build.ps1 -SkipDependencyInstall` reuses already-prepared Python dependencies.

Import the module explicitly: `import c:discordz.C.Main():`.
Wildcard C imports do not currently load its custom syntax registrations.

## Commands

```javascript
zsharp = type.script

noticed room Bot[] (
 import c:discordz.C.Main():

 noticed discord_command_hybrid Hello[text Name] (
  Discord.Print("Hello, " + Name):
 )

 noticed brain Start[] (
  Discord.Bot.Login(File.read(".env")):
  Discord.Bot.Status("online", "playing", "Ready for commands"):
 )

 noticed brain Shutdown[] (
  Discord.Bot.Shutdown:
 )
)
```

For this example `.env` contains the raw bot token, not a `TOKEN=...` assignment.
Do not commit that file. Status changes wait for readiness; they can be requested
before the connection finishes.

- `discord_command_hybrid` registers both `/hello` and `!hello`.
- `discord_command_slash` registers only `/hello`.
- `discord_command_msg` registers only `!hello`.

Names and Discord option names are lowercased, while Z# parameter bindings retain
their spelling. Parameters use the normal Z# declaration form. Text, number and
status parameters are supported; other types produce a registration error.
Prefix commands default to `!`. Put `Discord.Prefix("?", "!", "*"):` at the
beginning of a message/hybrid command body to configure that command's prefixes.
At least one nonempty literal text prefix is required; there is no fixed count
limit. Use one declaration per command, before executable statements. Prefixes
are registered before login, not when the body executes. They do not affect
other commands or the slash version of a hybrid command. Slash-only commands
reject this declaration. Enable **Message Content Intent** in the Discord developer
portal for message/hybrid commands. Invite the bot with `bot` and
`applications.commands` scopes for slash commands. The bot syncs its registered
slash commands during login; Discord controls when those commands appear.

Bodies run on a ZVM task thread, not the Python network thread. Slash commands are
deferred while their bodies run. `Discord.Print(text):` sends normally in the active
command's channel. `Discord.Print(text).replyToExecutor:` explicitly references
the invoking prefix-command message without pinging its author. Slash commands
still respond through their interaction. Both forms also support URL-free embed
templates, including the two-argument content override. Explicit URL webhooks
cannot use `.replyToExecutor`. Outside a command printing raises an error.
Commands have a 120-second dispatch
timeout and a bounded 256-event inbox. Native calls that block the ZVM task also
delay callbacks.

An active bot keeps a console script alive after `Start[]` returns. Explicit
`Discord.Bot.Shutdown:` releases it. Closing its hosting game/window cancels the
tasks and stops the bot. Closing/killing the host process also kills its embedded
bot thread. No standalone bot daemon is installed.

## Named webhooks

Declare each webhook directly inside the room:

```javascript
Webhook ReleaseNotice (
 content: "A new release is available!":
 tts: dead:
 embeds (
  Release (
   title: "Release":
   description: "Release details":
   url: "https://example.com/releases":
   color: #3366FF:
   timestamp: "2026-10-07T12:00:00Z":
   author ( name: "Publisher": iconURL: "https://example.com/author.png": )
   thumbnail: "https://example.com/thumb.png":
   image: "https://example.com/image.png":
   fields (
    Version ( name: "Version": value: "1.2.1.0": inline: alive: )
   )
   footer ( text: "DiscordZ": iconURL: "https://example.com/footer.png": )
  )
 )
 allowedMentions ( everyone: dead: users: []: roles: []: )
):
```

No webhook URL is required. Inside a command, send the declared content and
embeds **as the bot** in that command's channel using
`Discord.Print(Discord.Webhook("ReleaseNotice")):`.
Slash commands use the interaction follow-up; prefix commands use the bot's normal
message sender. This does not create a server webhook or require Manage Webhooks.
The sender name/avatar come from the bot profile, not per-message fields.
Use `Discord.Print("Replacement content", Discord.Webhook("ReleaseNotice")):`
to replace only its plain content, keeping its embeds. At least content or one
embed is required when sending. Mentions default off; Discord message/embed limits
are checked before sending. A URL-free template requires an active command context.

For compatibility, an explicit `url: File.read("webhook-url.txt"):` still sends
through that existing webhook instead. Only HTTPS Discord webhook endpoints are
accepted in this optional mode; it supports `username`/`avatarURL` overrides and
does not require bot login. Errors do not print secret webhook URLs. Automatic
server-webhook creation is not implemented; the default is direct bot sending.

Declarations and evaluated configuration persist through Z# bytecode. Keep source
expressions such as `File.read(...)` for secrets rather than literal URLs/tokens
when distributing the program.

## Offline checks

`build/checks/CommandsSmoke.zsharp` exercises all three command types, typed
parameters, ZVM event dispatch after Start returns, replies, and nested webhook
payloads using fake contexts and a mocked sender. It performs no Discord login or
HTTP request. `BotSmoke.zsharp` checks readiness/status ordering and shutdown.
These checks do not replace a real Discord-server test.

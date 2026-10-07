"""Thread-safe command inbox. ZVM owns execution; Discord owns network I/O."""
import asyncio
import inspect
import json
import queue
import threading
import math
import time
import discord
from discord.ext import commands

_lock = threading.RLock()
_definitions = {}
_message_events = {}

def bind_message(name, callback, *parameters):
    if len(parameters) != 6 or any(parameters[i] != "text" for i in (1, 3, 5)):
        raise ValueError("discord_event_message requires exactly three text parameters: message text, channel ID, message ID")
    names = parameters[::2]
    if any(not name.isidentifier() for name in names) or len(set(names)) != 3:
        raise ValueError("Message-event parameter names must be unique identifiers")
    definition = (name, tuple(parameters))
    with _lock:
        if callback in _message_events and _message_events[callback] != definition:
            raise ValueError("Duplicate Discord message event")
        _message_events[callback] = definition
    return True

def has_events():
    with _lock: return bool(_message_events)

class MessageContext:
    def __init__(self, bot, message):
        self.bot = bot
        self.message = message
        self.author = message.author
        self.channel = message.channel
        self.guild = message.guild
        self.deleted = False

    async def send(self, *args, **options):
        return await self.channel.send(*args, **options)

    async def reply(self, *args, **options):
        return await self.message.reply(*args, **options)

async def dispatch_message(bot, message):
    if message.author.bot: return False
    with _lock: targets = list(_message_events)
    context = MessageContext(bot, message)
    values = [message.content, str(message.channel.id), str(message.id)]
    for target in targets:
        try:
            await _invoke(target, context, values)
        except (queue.Full, asyncio.TimeoutError, RuntimeError) as error:
            # Never log message contents or token-bearing native errors.
            print("[DiscordZ] Message event failed: " + type(error).__name__, flush=True)
        if context.deleted: break
    return context.deleted
_prefixes = {}
_permissions = {}
_bot_permissions = {}
_cooldowns = {}
_cooldown_users = {}
_last_cooldown_cleanup = 0

def _known_callback(callback):
    if not any(target == callback for _, target, _ in _definitions.values()):
        raise ValueError("Unknown Discord command configuration target")

def _set_permissions(storage, callback, permissions):
    if not permissions or any(not isinstance(p, str) or p not in discord.Permissions.VALID_FLAGS for p in permissions):
        raise ValueError("RequirePermission requires valid Discord permission names, such as manage_messages")
    with _lock:
        _known_callback(callback)
        if callback in storage: raise ValueError("Use one permission declaration of each kind per command")
        storage[callback] = tuple(dict.fromkeys(permissions))
    return True

def set_permissions(callback, *permissions):
    return _set_permissions(_permissions, callback, permissions)

def set_bot_permissions(callback, *permissions):
    return _set_permissions(_bot_permissions, callback, permissions)

def set_cooldown(callback, milliseconds):
    if isinstance(milliseconds, bool) or not isinstance(milliseconds, (int, float)) or not math.isfinite(milliseconds) or milliseconds < 0:
        raise ValueError("Discord.Cooldown requires a finite nonnegative duration")
    with _lock:
        _known_callback(callback)
        if callback in _cooldowns: raise ValueError("Use one Discord.Cooldown declaration per command")
        _cooldowns[callback] = milliseconds / 1000
    return True

def _permission_error(required, actual, subject):
    if getattr(actual, "administrator", False): return None
    missing = [p for p in required if not getattr(actual, p, False)]
    if missing:
        labels = ", ".join(p.replace("_", " ").title() for p in missing)
        return subject + (" require " if subject == "You" else " requires ") + labels + ". Enable this permission in the server/channel settings."

def command_rejection(callback, context):
    global _last_cooldown_cleanup
    with _lock:
        user_required = _permissions.get(callback, ())
        bot_required = _bot_permissions.get(callback, ())
        cooldown = _cooldowns.get(callback, 0)
    if (user_required or bot_required) and getattr(context, "guild", None) is None:
        return "This command requires server permissions and cannot run in a direct message."
    error = _permission_error(user_required, getattr(context, "permissions", None), "You")
    if error: return error
    actual_bot = getattr(context, "bot_permissions", None)
    if actual_bot is None: actual_bot = getattr(context, "app_permissions", None)
    error = _permission_error(bot_required, actual_bot, "Bot")
    if error: return error
    if cooldown:
        user = getattr(context, "author", None) or getattr(context, "user", None)
        if user is None: return "Cannot determine the command executor for its cooldown."
        now = time.monotonic()
        key = (callback, user.id)
        with _lock:
            if now - _last_cooldown_cleanup > 60:
                for expired in [k for k, end in _cooldown_users.items() if end <= now]:
                    del _cooldown_users[expired]
                _last_cooldown_cleanup = now
            end = _cooldown_users.get(key, 0)
            if end > now: return f"Command is on cooldown. Try again in {end - now:.3f}s."
            _cooldown_users[key] = now + cooldown
    return None

async def _send_command_error(context, message):
    options = {"allowed_mentions": discord.AllowedMentions.none()}
    if hasattr(context, "response"):
        if context.response.is_done(): await context.followup.send(message, ephemeral=True, **options)
        else: await context.response.send_message(message, ephemeral=True, **options)
    elif getattr(context, "interaction", None) is not None:
        await _report_command_error(context.interaction, message)
    else:
        await context.send(message, **options)

async def _report_command_error(context, message):
    try:
        await _send_command_error(context, message)
    except (discord.HTTPException, asyncio.TimeoutError):
        # A bot without Send Messages still needs a useful local diagnostic.
        print("[DiscordZ] " + message + " Could not send the error response; check the bot's channel access and Send Messages permission.", flush=True)

def set_prefixes(callback, *prefixes):
    if not prefixes or any(not isinstance(p, str) or not p for p in prefixes):
        raise ValueError("Discord.Prefix requires one or more nonempty text prefixes")
    with _lock:
        matching = [(name, kind) for name, (kind, target, _) in _definitions.items() if target == callback]
        if len(matching) != 1 or matching[0][1] == "slash":
            raise ValueError("Discord.Prefix is only valid in a message or hybrid command")
        name = matching[0][0]
        if name in _prefixes: raise ValueError("Use one Discord.Prefix declaration per command")
        _prefixes[name] = tuple(dict.fromkeys(prefixes))
    return True

def command_prefix(bot, message):
    # Resolve both prefix and command, so another command cannot borrow its prefixes.
    content = message.content
    with _lock:
        definitions = list(_definitions.items())
        prefixes = dict(_prefixes)
    matches = set()
    for name, (kind, _, _) in definitions:
        if kind == "slash": continue
        for prefix in prefixes.get(name, ("!",)):
            if content.startswith(prefix):
                tail = content[len(prefix):]
                if tail.split(maxsplit=1) and tail.split(maxsplit=1)[0] == name:
                    matches.add(prefix)
    return sorted(matches, key=lambda p: (-len(p), p))
_pending = {}
_pending_callbacks = {}
_inbox = queue.Queue(maxsize=256)
_next_id = 0
_native_event = None
_offline_thread = None
_offline_failure = None

def bind(kind, name, callback, *parameters):
    if len(parameters) % 2: raise ValueError("Invalid command parameter metadata")
    return register(name, kind, callback, [
        {"name": parameters[i], "type": parameters[i + 1]}
        for i in range(0, len(parameters), 2)])

def has_commands():
    with _lock: return bool(_definitions)

def needs_message_content():
    with _lock: return bool(_message_events) or any(kind != "slash" for kind, _, _ in _definitions.values())

def native_poll(owner=""):
    global _native_event
    _native_event = None
    with _inbox.mutex:
        index = 0
        while index < len(_inbox.queue):
            event = _inbox.queue[index]
            with _lock: pending = event["id"] in _pending
            if not pending:
                del _inbox.queue[index]
                _inbox.not_full.notify()
                continue
            if not owner or event["callback"].startswith(owner + ":"):
                _native_event = event
                del _inbox.queue[index]
                _inbox.not_full.notify()
                break
            index += 1
    return float(_native_event["id"]) if _native_event else 0.0

def native_target(): return _native_event["callback"]
def native_count(): return float(len(_native_event["arguments"]))
def native_argument(index): return _native_event["arguments"][int(index)]

def active():
    if _offline_failure is not None: raise RuntimeError(_offline_failure)
    with _lock:
        return bool(_pending) or (_offline_thread is not None and _offline_thread.is_alive())

def start_offline():
    """Integration fixture only: no tokens, sockets, or Discord connection."""
    global _offline_thread, _offline_failure
    import Webhooks
    seen = []
    original_send = Webhooks._send
    async def fake_send(payload):
        assert payload["content"] == "offline webhook"
        assert payload["embeds"][0]["title"] == "Offline embed"
        seen.append("webhook")
    Webhooks._send = fake_send
    class Context:
        author = type("User", (), {"id": 123})()
        guild = type("Guild", (), {"id": 1})()
        permissions = discord.Permissions(manage_messages=True)
        bot_permissions = discord.Permissions(manage_messages=True)
        async def reply(self, text=None, **options):
            assert options.pop("mention_author") is False
            seen.append("reference")
            await self.send(text, **options)
        async def send(self, text=None, **options):
            if options:
                assert options["content"] == "offline webhook"
                assert options["embeds"][0].title == "Offline embed"
                assert options["allowed_mentions"].everyone is False
                seen.append("webhook")
            else:
                assert text == "offline command"
                seen.append("reply")
    class Response:
        done = False
        def is_done(self): return self.done
        async def defer(self): self.done = True
    class Interaction:
        def __init__(self):
            self.response = Response()
            self.followup = Context()
    async def exercise():
        with _lock: definitions = list(_definitions.items())
        assert len(definitions) == 3
        assert _cooldowns["CommandsSmoke:CommandsSmoke:HybridTest"] == 5
        assert _cooldowns["CommandsSmoke:CommandsSmoke:MessageTest"] == 0.005
        assert _permissions["CommandsSmoke:CommandsSmoke:HybridTest"] == ("manage_messages",)
        assert _bot_permissions["CommandsSmoke:CommandsSmoke:HybridTest"] == ("manage_messages",)
        # Verify discord.py accepts generated typed hybrid, slash and prefix commands.
        import discord
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        install(bot)
        assert bot.get_command("hybridtest") and bot.get_command("messagetest")
        assert bot.tree.get_command("slashtest") and bot.tree.get_command("hybridtest")
        class Message:
            def __init__(self, content): self.content = content
        assert command_prefix(bot, Message("?hybridtest hi")) == ["?"]
        assert command_prefix(bot, Message("*hybridtest hi")) == ["*"]
        assert command_prefix(bot, Message("??messagetest hi")) == ["??"]
        assert command_prefix(bot, Message("!messagetest hi")) == []
        assert command_prefix(bot, Message("?messagetest hi")) == []
        assert command_prefix(bot, Message("!slashtest hi")) == []
        await bot.close()
        for _, (kind, callback, parameters) in definitions:
            values = [{"text": "offline command", "number": 10.0, "status": True}[p["type"]] for p in parameters]
            context = Interaction() if kind == "slash" else Context()
            await _invoke(callback, context, values)
            if kind == "slash": assert context.response.is_done()
        assert seen.count("reply") == 3 and seen.count("webhook") == 3
        assert seen.count("reference") == 2
    def run():
        global _offline_failure
        try: asyncio.run(exercise())
        except Exception as exc: _offline_failure = type(exc).__name__ + ": " + str(exc)
        finally: Webhooks._send = original_send
    _offline_failure = None
    _offline_thread = threading.Thread(target=run, name="DiscordZOfflineEvents", daemon=True)
    _offline_thread.start()
    return True

def start_messages_offline():
    """Native callback integration fixture: no Discord login or network calls."""
    global _offline_thread, _offline_failure
    from types import SimpleNamespace
    deleted, processed = [], []
    guild = SimpleNamespace(id=1, me=object())
    async def remove(message_id): deleted.append(message_id)
    class Partial:
        def __init__(self, message_id): self.id = message_id
        async def delete(self): await remove(self.id)
    class Channel:
        id = 1234567890123456789
        def __init__(self): self.guild = guild
        def permissions_for(self, member): return discord.Permissions(manage_messages=True)
        def get_partial_message(self, message_id): return Partial(message_id)
        async def send(self, *args, **kwargs): raise AssertionError("Unexpected send in successful moderation fixture")
    channel = Channel()
    def message(content, message_id, bot=False):
        return SimpleNamespace(content=content, id=message_id, guild=guild, channel=channel,
                               author=SimpleNamespace(bot=bot, id=12))
    async def exercise():
        assert len(_message_events) == 1 and not _definitions
        bot = commands.Bot(command_prefix=command_prefix, help_command=None, intents=discord.Intents.default())
        bot.get_channel = lambda channel_id: channel if channel_id == channel.id else None
        async def process(message): processed.append(message.id)
        bot.process_commands = process
        install(bot)
        await bot.on_message(message("BLOCKED_WORD", 2234567890123456789))
        await bot.on_message(message("ordinary message", 3234567890123456789))
        await bot.on_message(message("BLOCKED_WORD", 4234567890123456789, True))
        assert deleted == [2234567890123456789]
        assert processed == [3234567890123456789]
        await bot.close()
    def run():
        global _offline_failure
        try: asyncio.run(exercise())
        except Exception as error: _offline_failure = type(error).__name__ + ": " + str(error)
    _offline_failure = None
    _offline_thread = threading.Thread(target=run, name="DiscordZOfflineMessages", daemon=True)
    _offline_thread.start()
    return True

def register(name, kind, callback, parameters):
    parameters = json.loads(parameters) if isinstance(parameters, str) else parameters
    key = name.lower()
    if kind not in ("hybrid", "slash", "msg"):
        raise ValueError("Unknown Discord command kind")
    if not key or len(key) > 32 or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in key):
        raise ValueError("Discord command names must be 1-32 lowercase letters, digits, '-' or '_'")
    converted = []
    for parameter in parameters:
        if parameter["type"] not in ("text", "number", "status"):
            raise ValueError("Discord command parameters support text, number and status")
        if not parameter["name"].isidentifier():
            raise ValueError("Invalid command parameter name")
        converted.append(dict(parameter))
    if len({p["name"].lower() for p in converted}) != len(converted):
        raise ValueError("Duplicate command parameter")
    if any(p["name"].lower() == "context" for p in converted):
        raise ValueError("Command parameter name 'context' is reserved")
    with _lock:
        if key in _definitions:
            if _definitions[key] == (kind, callback, converted): return True
            raise ValueError("Duplicate Discord command: " + key)
        _definitions[key] = (kind, callback, converted)
    return True

async def _invoke(callback, context, values):
    global _next_id
    loop = asyncio.get_running_loop()
    # Acknowledge slash commands before the VM performs potentially slow work.
    if hasattr(context, "response") and not context.response.is_done():
        await context.response.defer()
    future = loop.create_future()
    with _lock:
        _next_id += 1
        event_id = _next_id
        _pending[event_id] = (loop, future, context)
        _pending_callbacks[event_id] = callback
    try:
        _inbox.put_nowait({"id": event_id, "callback": callback, "arguments": list(values)})
        await asyncio.wait_for(future, timeout=120)
    finally:
        with _lock:
            _pending.pop(event_id, None)
            _pending_callbacks.pop(event_id, None)

def install(bot):
    from discord import app_commands
    with _lock:
        definitions = list(_definitions.items())
    for name, (kind, target, parameters) in definitions:
        def make_handler(target, parameters):
            async def handler(context, *arguments, **keywords):
                rejection = command_rejection(target, context)
                if rejection:
                    await _report_command_error(context, rejection)
                    return
                values = arguments or tuple(keywords[p["name"].lower()] for p in parameters)
                try:
                    await _invoke(target, context, values)
                except (RuntimeError, asyncio.TimeoutError):
                    # Native errors may contain tokens or URLs: never echo their raw text.
                    await _report_command_error(context, "Command failed. Check the host console for details.")
            types = {"text": str, "number": float, "status": bool}
            handler.__signature__ = inspect.Signature([
                commands.Parameter("context", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                *[commands.Parameter(p["name"].lower(), inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                   annotation=types[p["type"]]) for p in parameters]])
            return handler
        handler = make_handler(target, parameters)
        if kind == "slash":
            bot.tree.add_command(app_commands.Command(name=name, description="Run " + name,
                                                       callback=handler))
        else:
            factory = commands.hybrid_command if kind == "hybrid" else commands.command
            bot.add_command(factory(name=name, description="Run " + name)(handler))
    async def prefix_error(context, error):
        if isinstance(error, commands.CommandNotFound): return
        message = "Invalid or missing command arguments. Check the command's required parameters." if isinstance(error, commands.UserInputError) else "Command failed. Check the host console for details."
        await _report_command_error(context, message)
    async def slash_error(interaction, error):
        await _report_command_error(interaction, "Invalid arguments or command failure. Check the host console for details.")
    bot.add_listener(prefix_error, "on_command_error")
    bot.tree.on_error = slash_error
    @bot.event
    async def on_message(message):
        if message.author.bot: return
        if not await dispatch_message(bot, message):
            await bot.process_commands(message)
    return True

def poll():
    while True:
        try:
            event = _inbox.get_nowait()
        except queue.Empty:
            return ""
        with _lock:
            if event["id"] in _pending:
                return json.dumps(event)

def _submit(event_id, operation):
    with _lock:
        record = _pending.get(int(event_id))
    if record is None:
        raise RuntimeError("Discord action is outside an active command or message event")
    loop, future, context = record
    async def run():
        return await operation(context)
    result = asyncio.run_coroutine_threadsafe(run(), loop).result(timeout=15)
    return True if result is None else result

def reply(event_id, text, reply_to_executor=False):
    if len(text) > 2000:
        raise ValueError("Discord messages may contain at most 2000 characters")
    async def send(context):
        if hasattr(context, "followup"):
            await context.followup.send(text)
        elif reply_to_executor and getattr(context, "interaction", None) is None:
            await context.reply(text, mention_author=False)
        else:
            await context.send(text)
    return _submit(event_id, send)

def reply_payload(event_id, payload, reply_to_executor=False):
    import Webhooks
    options = Webhooks.message_options(payload)
    async def send(context):
        if hasattr(context, "followup"):
            await context.followup.send(**options)
        elif reply_to_executor and getattr(context, "interaction", None) is None:
            await context.reply(**options, mention_author=False)
        else:
            await context.send(**options)
    return _submit(event_id, send)

def delete_message(event_id, channel_id, message_id):
    # Snowflakes are text, not floating-point Z# numbers (which can lose bits).
    for value in (channel_id, message_id):
        if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or not 0 < int(value) < 2**64:
            raise ValueError("Discord message/channel IDs must be positive decimal text IDs")
    async def remove(context):
        client = getattr(context, "bot", None) or getattr(context, "client", None)
        if client is None: raise RuntimeError("Bot is not initialized")
        channel = client.get_channel(int(channel_id))
        try:
            if channel is None: channel = await client.fetch_channel(int(channel_id))
            guild = getattr(channel, "guild", None)
            if guild is None:
                await _report_command_error(context, "DeleteUserMessage requires a server message.")
                return False
            if getattr(getattr(context, "guild", None), "id", None) != guild.id:
                await _report_command_error(context, "Cannot delete message: target must be in the command's server.")
                return False
            with _lock:
                required = _permissions.get(_pending_callbacks.get(int(event_id)), ())
            user = getattr(context, "author", None) or getattr(context, "user", None)
            if required:
                error = _permission_error(required, channel.permissions_for(user), "You")
                if error:
                    await _report_command_error(context, error)
                    return False
            member = guild.me
            if member is None: member = await guild.fetch_member(client.user.id)
            error = _permission_error(("manage_messages",), channel.permissions_for(member), "Cannot delete message: bot")
            if error:
                print("[DiscordZ] " + error, flush=True)
                await _report_command_error(context, error)
                return False
            await channel.get_partial_message(int(message_id)).delete()
            if isinstance(context, MessageContext) and int(channel_id) == context.channel.id and int(message_id) == context.message.id:
                context.deleted = True
        except discord.Forbidden:
            await _report_command_error(context, "Cannot delete message: bot requires View Channel and Manage Messages in the target channel.")
            return False
        except discord.NotFound:
            if isinstance(context, MessageContext) and int(channel_id) == context.channel.id and int(message_id) == context.message.id:
                context.deleted = True
            await _report_command_error(context, "Cannot delete message: message or channel no longer exists.")
            return False
        return True
    return _submit(event_id, remove)

def complete(event_id, error=""):
    with _lock:
        record = _pending.get(int(event_id))
    if record is None:
        return True
    loop, future, _ = record
    def finish():
        if not future.done():
            if error:
                future.set_exception(RuntimeError(error))
            else:
                future.set_result(True)
    loop.call_soon_threadsafe(finish)
    return True

def shutdown():
    with _lock:
        pending = list(_pending.values())
        _pending.clear()
        _pending_callbacks.clear()
        _cooldown_users.clear()
    for loop, future, _ in pending:
        if not loop.is_closed():
            loop.call_soon_threadsafe(future.cancel)
    while not _inbox.empty():
        try: _inbox.get_nowait()
        except queue.Empty: break
    return True

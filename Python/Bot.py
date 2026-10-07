"""Asynchronous DiscordZ bot; Python paths are configured by the native bridge."""
import os
import sys
_dll_directory = os.add_dll_directory(sys.base_prefix) if os.name == "nt" else None
import asyncio
import threading
import discord
import Events

_lock = threading.RLock()
_thread = _loop = _client = None
_failure = None
_start_task = None
_pending_status = None
_presence_lock = None

async def _apply_status(client, presence_lock):
    # Serialize updates on the bot's loop; recheck readiness after reconnects.
    async with presence_lock:
        with _lock:
            if client is not _client or not client.is_ready() or _pending_status is None:
                return
            status, activity, details = _pending_status
        types = {"playing": discord.ActivityType.playing, "watching": discord.ActivityType.watching,
                 "listening": discord.ActivityType.listening, "competing": discord.ActivityType.competing}
        await client.change_presence(status=discord.Status.__members__[status],
                                     activity=discord.Activity(type=types[activity], name=details))

def login(token):
    """Start connecting. on_ready, not this return value, confirms login."""
    global _thread, _loop, _client, _failure, _presence_lock
    with _lock:
        if _thread is not None and _thread.is_alive():
            raise RuntimeError("Discord bot is already running")
        _failure = None
        _loop = asyncio.new_event_loop()
        if Events.has_commands() or Events.has_events():
            from discord.ext import commands
            class CommandBot(commands.Bot):
                async def setup_hook(self):
                    Events.install(self)
                    if Events.has_commands(): await self.tree.sync()
            intents = discord.Intents.default()
            intents.message_content = Events.needs_message_content()
            _client = CommandBot(command_prefix=Events.command_prefix, intents=intents)
        else:
            _client = discord.Client(intents=discord.Intents.default())
        _presence_lock = asyncio.Lock()
        loop, client = _loop, _client
        presence_lock = _presence_lock
        @client.event
        async def on_ready():
            await _apply_status(client, presence_lock)
            print("DISCORDZ_READY", flush=True)
            print(f"Logged in as {client.user}", flush=True)
        def run():
            global _failure, _start_task
            asyncio.set_event_loop(loop)
            try:
                _start_task = loop.create_task(client.start(token))
                loop.run_until_complete(_start_task)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                _failure = type(exc).__name__
                print(f"[DiscordZ] Bot stopped: {_failure}", file=sys.stderr, flush=True)
            finally:
                loop.run_until_complete(client.close())
                pending = asyncio.all_tasks(loop)
                for task in pending: task.cancel()
                if pending: loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()
        _thread = threading.Thread(target=run, name="DiscordZBot", daemon=True)
        _thread.start()
        return True

def shutdown():
    global _thread, _loop, _client, _pending_status, _presence_lock
    Events.shutdown()
    with _lock:
        thread, loop, client = _thread, _loop, _client
        if thread is None:
            _pending_status = None
            return True
    # on_ready also takes _lock; holding it through join would deadlock startup.
    if thread.is_alive() and loop is not None and not loop.is_closed():
        async def close():
            if _start_task is not None and not _start_task.done():
                _start_task.cancel()
            await client.close()
        future = asyncio.run_coroutine_threadsafe(close(), loop)
        try: future.result(timeout=5)
        except Exception: pass
    thread.join(timeout=5)
    if thread.is_alive(): raise RuntimeError("Bot shutdown timed out")
    with _lock:
        if _thread is thread:
            _thread = _loop = _client = None
            _pending_status = _presence_lock = None
    return True

def active():
    with _lock:
        return _thread is not None and _thread.is_alive()

def set_status(status, activity, details):
    global _pending_status
    with _lock:
        statuses = discord.Status.__members__
        types = {"playing": discord.ActivityType.playing, "watching": discord.ActivityType.watching,
                 "listening": discord.ActivityType.listening, "competing": discord.ActivityType.competing}
        if status not in statuses or activity not in types:
            raise ValueError("Unsupported Discord status/activity")
        _pending_status = (status, activity, details)
        if _loop is None or _client is None or not _client.is_ready():
            return True
        future = asyncio.run_coroutine_threadsafe(_apply_status(_client, _presence_lock), _loop)
    # Never hold the thread lock while waiting for an event-loop coroutine.
    future.result(timeout=5)
    return True

def self_test():
    """No credentials or network; check native extensions and lifecycle."""
    import ssl
    import audioop
    import aiohttp
    assert ssl.OPENSSL_VERSION and discord.__version__ and aiohttp.__version__
    assert audioop.mul(b"\0\0", 2, 1) == b"\0\0"
    assert shutdown()
    # Replace the client only within this offline test; no Discord requests.
    ready = threading.Event()
    changes = []
    class FakeClient:
        def __init__(self, **kwargs):
            self.closed = False
            self.ready_state = False
            self.event_loop_wait = None
        def event(self, function):
            setattr(self, function.__name__, function)
            return function
        def is_ready(self): return self.ready_state and not self.closed
        async def start(self, token):
            self.event_loop_wait = asyncio.Event()
            self.ready_state = True
            self.user = "offline-test"
            await self.on_ready()
            ready.set()
            if not self.closed: await self.event_loop_wait.wait()
        async def close(self):
            self.closed = True
            if self.event_loop_wait is not None: self.event_loop_wait.set()
        async def change_presence(self, **kwargs):
            assert self.is_ready()
            changes.append(kwargs["activity"].name)
    original = discord.Client
    discord.Client = FakeClient
    try:
        for _ in range(2):
            ready.clear()
            changes.clear()
            assert set_status("online", "playing", "Before login")
            assert set_status("online", "playing", "Latest before login")
            assert not changes
            assert login("OFFLINE_TEST_ONLY")
            assert ready.wait(3)
            try:
                login("OFFLINE_TEST_ONLY")
                raise AssertionError("Duplicate login was accepted")
            except RuntimeError:
                pass
            assert set_status("online", "playing", "Offline test")
            assert changes == ["Latest before login", "Offline test"]
            assert shutdown()
            assert _thread is None
    finally:
        shutdown()
        discord.Client = original
    return True

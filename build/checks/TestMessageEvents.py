import asyncio
import types
import unittest
from unittest.mock import AsyncMock, patch
import discord
from discord.ext import commands
import Events

class MessageEventTests(unittest.TestCase):
    def setUp(self):
        Events._message_events.clear()
        Events._definitions.clear()
        Events._prefixes.clear()
        Events._permissions.clear()
        Events._bot_permissions.clear()
        Events._cooldowns.clear()
        Events._cooldown_users.clear()
        Events.shutdown()

    def bind(self, target="Test:Room:Message"):
        Events.bind_message("Message", target, "userMessage", "text", "channelID", "text", "messageID", "text")

    def message(self, bot=False):
        return types.SimpleNamespace(content="ordinary message", id=1234567890123456789,
            channel=types.SimpleNamespace(id=2234567890123456789), guild=None,
            author=types.SimpleNamespace(id=12, bot=bot))

    def test_registration_and_intents(self):
        self.bind()
        self.assertTrue(Events.has_events())
        self.assertTrue(Events.needs_message_content())
        self.assertFalse(Events.has_commands())
        self.bind()  # identical registration is idempotent
        self.assertEqual(len(Events._message_events), 1)
        for parameters in [(), ("x", "text"), ("a", "number", "b", "text", "c", "text"),
                           ("a", "text", "a", "text", "c", "text")]:
            with self.assertRaises(ValueError): Events.bind_message("Bad", "Other:Room:Message", *parameters)

    def test_exact_payload_and_bot_filter(self):
        self.bind()
        async def exercise():
            with patch.object(Events, "_invoke", new_callable=AsyncMock) as invoke:
                self.assertFalse(await Events.dispatch_message(object(), self.message()))
                self.assertEqual(invoke.call_args.args[2],
                    ["ordinary message", "2234567890123456789", "1234567890123456789"])
                await Events.dispatch_message(object(), self.message(True))
                invoke.assert_awaited_once()
        asyncio.run(exercise())

    def test_multiple_handlers_and_delete_stops_commands(self):
        self.bind()
        self.bind("Other:Room:Message")
        async def exercise():
            bot = commands.Bot(command_prefix="!", help_command=None, intents=discord.Intents.default())
            bot.process_commands = AsyncMock()
            Events.install(bot)
            with patch.object(Events, "_invoke", new_callable=AsyncMock) as invoke:
                await bot.on_message(self.message())
                self.assertEqual(invoke.await_count, 2)
                bot.process_commands.assert_awaited_once()
            bot.process_commands.reset_mock()
            async def delete(target, context, values): context.deleted = True
            with patch.object(Events, "_invoke", side_effect=delete) as invoke:
                await bot.on_message(self.message())
                invoke.assert_awaited_once()
                bot.process_commands.assert_not_awaited()
            await bot.close()
        asyncio.run(exercise())

    def test_queue_cancellation_cleanup(self):
        async def exercise():
            task = asyncio.create_task(Events._invoke("Test:Room:Message", object(), ["text", "1", "2"]))
            await asyncio.sleep(0)
            self.assertEqual(len(Events._pending), 1)
            Events.shutdown()
            with self.assertRaises(asyncio.CancelledError): await task
            self.assertFalse(Events._pending)
            self.assertFalse(Events._pending_callbacks)
            self.assertTrue(Events._inbox.empty())
        asyncio.run(exercise())

    def test_overflow_is_reported_without_message_content(self):
        self.bind()
        async def exercise():
            with patch.object(Events, "_invoke", side_effect=Events.queue.Full), patch("builtins.print") as output:
                self.assertFalse(await Events.dispatch_message(object(), self.message()))
                self.assertNotIn("ordinary message", str(output.call_args))
                self.assertIn("Full", str(output.call_args))
        asyncio.run(exercise())

if __name__ == "__main__": unittest.main()

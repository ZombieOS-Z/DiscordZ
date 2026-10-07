import asyncio
import types
import unittest
from unittest.mock import patch, AsyncMock
import discord
import Events

class ModerationTests(unittest.TestCase):
    def setUp(self):
        for store in (Events._definitions, Events._permissions, Events._bot_permissions,
                      Events._cooldowns, Events._cooldown_users): store.clear()
        Events.register("test", "msg", "Test:Room:Command", [])
        self.target = "Test:Room:Command"
        self.context = types.SimpleNamespace(guild=types.SimpleNamespace(id=1),
            author=types.SimpleNamespace(id=12), permissions=discord.Permissions.none(),
            bot_permissions=discord.Permissions.none(), send=AsyncMock())

    def test_permissions(self):
        Events.set_permissions(self.target, "manage_messages")
        Events.set_bot_permissions(self.target, "manage_messages")
        self.assertIn("You require Manage Messages", Events.command_rejection(self.target, self.context))
        self.context.permissions.manage_messages = True
        self.assertIn("Bot requires Manage Messages", Events.command_rejection(self.target, self.context))
        self.context.bot_permissions.manage_messages = True
        self.assertIsNone(Events.command_rejection(self.target, self.context))
        self.context.guild = None
        self.assertIn("direct message", Events.command_rejection(self.target, self.context))

    def test_administrator_and_invalid_permissions(self):
        Events.set_permissions(self.target, "manage_messages")
        self.context.permissions.administrator = True
        self.assertIsNone(Events.command_rejection(self.target, self.context))
        for permissions in [(), ("not_real",), (42,)]:
            with self.assertRaises(ValueError): Events.set_bot_permissions(self.target, *permissions)

    def test_cooldowns(self):
        Events.set_cooldown(self.target, 5)
        with patch.object(Events.time, "monotonic", return_value=100):
            self.assertIsNone(Events.command_rejection(self.target, self.context))
            self.assertIn("0.005s", Events.command_rejection(self.target, self.context))
            self.context.author.id = 13
            self.assertIsNone(Events.command_rejection(self.target, self.context))
            Events.register("other", "msg", "Test:Room:Other", [])
            Events.set_cooldown("Test:Room:Other", 5000)
            self.assertIsNone(Events.command_rejection("Test:Room:Other", self.context))
        with patch.object(Events.time, "monotonic", return_value=100.006):
            self.assertIsNone(Events.command_rejection(self.target, self.context))
        for value in (-1, float("inf"), float("nan"), "5s", True):
            with self.assertRaises(ValueError): Events.set_cooldown("Test:Room:Other", value)

    def test_denied_does_not_consume_cooldown(self):
        Events.set_permissions(self.target, "manage_messages")
        Events.set_cooldown(self.target, 5000)
        Events.command_rejection(self.target, self.context)
        self.assertEqual(Events._cooldown_users, {})

    def test_slash_rejection_is_ephemeral(self):
        context = types.SimpleNamespace(response=types.SimpleNamespace(is_done=lambda: False,
                                        send_message=AsyncMock()))
        asyncio.run(Events._report_command_error(context, "Bot requires Manage Messages"))
        self.assertTrue(context.response.send_message.call_args.kwargs["ephemeral"])

    def test_handler_checks_before_dispatch(self):
        from discord.ext import commands
        Events.set_permissions(self.target, "manage_messages")
        async def exercise():
            bot = commands.Bot(command_prefix="!", help_command=None, intents=discord.Intents.default())
            Events.install(bot)
            with patch.object(Events, "_invoke", new_callable=AsyncMock) as invoke:
                await bot.get_command("test").callback(self.context)
                invoke.assert_not_awaited()
                self.assertIn("Manage Messages", self.context.send.call_args.args[0])
                self.context.permissions.manage_messages = True
                await bot.get_command("test").callback(self.context)
                invoke.assert_awaited_once()
            await bot.close()
        asyncio.run(exercise())

    def test_delete_checks_permission_and_exact_id(self):
        permission = discord.Permissions.none()
        message = types.SimpleNamespace(delete=AsyncMock())
        seen = []
        def partial(message_id): seen.append(message_id); return message
        channel = types.SimpleNamespace(guild=types.SimpleNamespace(id=1, me=object()),
                     permissions_for=lambda member: permission, get_partial_message=partial)
        self.context.bot = types.SimpleNamespace(get_channel=lambda value: channel)
        def submit(event, operation): return asyncio.run(operation(self.context))
        with patch.object(Events, "_submit", side_effect=submit):
            self.assertFalse(Events.delete_message(1, "123", "1234567890123456789"))
            message.delete.assert_not_awaited()
            self.assertIn("Manage Messages", self.context.send.call_args.args[0])
            permission.manage_messages = True
            self.assertTrue(Events.delete_message(1, "123", "1234567890123456789"))
            self.assertEqual(seen, [1234567890123456789])
            message.delete.assert_awaited_once()
            channel.guild.id = 2
            self.assertFalse(Events.delete_message(1, "123", "1234567890123456789"))
            message.delete.assert_awaited_once()
        for value in ("0", "-1", "abc", str(2**64), 123):
            with self.assertRaises(ValueError): Events.delete_message(1, "123", value)

if __name__ == "__main__": unittest.main()

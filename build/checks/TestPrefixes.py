import types
import unittest
import Events
import asyncio
import discord
from discord.ext import commands

class PrefixTests(unittest.TestCase):
    def setUp(self):
        Events._definitions.clear()
        Events._prefixes.clear()
        Events.register("help", "msg", "Test:Room:Help", [])
        Events.register("ping", "hybrid", "Test:Room:Ping", [])
        Events.register("slash", "slash", "Test:Room:Slash", [])

    def resolve(self, text):
        return Events.command_prefix(None, types.SimpleNamespace(content=text))

    def test_default(self):
        self.assertEqual(self.resolve("!help"), ["!"])
        self.assertEqual(self.resolve("?help"), [])
        self.assertEqual(self.resolve("!helpful"), [])

    def test_many_and_isolation(self):
        prefixes = tuple("p" + str(i) + ":" for i in range(100)) + ("?", "??", "*")
        Events.set_prefixes("Test:Room:Help", *prefixes)
        for p in prefixes: self.assertEqual(self.resolve(p + "help hi"), [p])
        self.assertEqual(self.resolve("?ping"), [])
        self.assertEqual(self.resolve("!ping"), ["!"])
        self.assertEqual(self.resolve("!help"), [])

    def test_invalid(self):
        for args in [(), ("",), (3,)]:
            with self.assertRaises(ValueError): Events.set_prefixes("Test:Room:Help", *args)
        with self.assertRaises(ValueError): Events.set_prefixes("Test:Room:Slash", "?")
        with self.assertRaises(ValueError): Events.set_prefixes("missing", "?")
        Events.set_prefixes("Test:Room:Help", "?")
        with self.assertRaises(ValueError): Events.set_prefixes("Test:Room:Help", "!")

    def test_discord_context_routing(self):
        Events.set_prefixes("Test:Room:Help", "?", "??", "*")
        async def exercise():
            bot = commands.Bot(command_prefix=Events.command_prefix,
                               help_command=None, intents=discord.Intents.default())
            bot._connection.user = types.SimpleNamespace(id=100)
            Events.install(bot)
            for text, expected in [("?help", "help"), ("??help", "help"),
                                   ("*help", "help"), ("!ping", "ping"),
                                   ("!help", None), ("?ping", None), ("!slash", None)]:
                message = types.SimpleNamespace(content=text, author=types.SimpleNamespace(id=200),
                                                _state=bot._connection)
                context = await bot.get_context(message)
                self.assertEqual(context.command.name if context.command else None, expected)
            await bot.close()
        asyncio.run(exercise())

if __name__ == "__main__": unittest.main()

"""No-network payload validation tests."""
import pathlib
import sys
import unittest

root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "Python"))
sys.path.insert(0, str(root / "Python" / "vendor"))
import Webhooks

URL = "https://discord.com/api/webhooks/123/OFFLINE_TEST_ONLY"

class WebhookTests(unittest.TestCase):
    def setUp(self): Webhooks._definitions.clear()

    def test_nested_fields(self):
        Webhooks.bind("Test", "url", URL, "content", "text", "embeds.Release.title", "Title",
                      "embeds.Release.color", "#3366FF", "embeds.Release.fields.One.name", "Name",
                      "embeds.Release.fields.One.value", "Value", "allowedMentions.everyone", False,
                      "allowedMentions.users", '["123"]')
        payload = Webhooks._definitions["Test"]
        self.assertEqual(payload["embeds"][0]["color"], 0x3366FF)
        self.assertEqual(payload["embeds"][0]["fields"][0]["value"], "Value")
        self.assertEqual(payload["allowed_mentions"]["parse"], [])
        self.assertEqual(payload["allowed_mentions"]["users"], ["123"])

    def test_invalid_endpoint(self):
        for url in ("http://discord.com/api/webhooks/123/x", "https://example.com/x", URL + "?secret=TEST"):
            with self.assertRaisesRegex(ValueError, "HTTPS Discord"):
                Webhooks.register("Test", {"url": url, "content": "x"})

    def test_url_free_template(self):
        Webhooks.bind("BotMessage", "content", "Hello", "embeds.Main.title", "Bot embed")
        self.assertNotIn("url", Webhooks._definitions["BotMessage"])
        options = Webhooks.message_options(Webhooks._definitions["BotMessage"])
        self.assertEqual(options["content"], "Hello")
        self.assertEqual(options["embeds"][0].title, "Bot embed")
        self.assertFalse(options["allowed_mentions"].everyone)
        with self.assertRaisesRegex(RuntimeError, "outside an active command"):
            Webhooks.send("BotMessage")

    def test_limits_and_duplicates(self):
        with self.assertRaises(ValueError): Webhooks.register("Test", {"url": URL, "content": "x" * 2001})
        with self.assertRaises(ValueError): Webhooks.register("Test", {"url": URL, "embeds": [{"title": "x" * 257}]})
        with self.assertRaises(ValueError): Webhooks.bind("Test", "url", URL, "content", "a", "content", "b")
        Webhooks.register("Test", {"url": URL, "content": "x"})
        with self.assertRaisesRegex(ValueError, "Duplicate webhook"):
            Webhooks.register("Test", {"url": URL, "content": "y"})

    def test_overrides_and_error_redaction(self):
        Webhooks.register("Test", {"url": URL})
        sent = []
        original = Webhooks._send
        async def fake(payload): sent.append(payload["content"])
        Webhooks._send = fake
        try:
            with self.assertRaisesRegex(ValueError, "requires content"):
                Webhooks.send("Test")
            Webhooks.send("Test", "override")
            self.assertEqual(sent, ["override"])
            async def failure(payload): raise RuntimeError(payload["url"])
            Webhooks._send = failure
            with self.assertRaises(RuntimeError) as error: Webhooks.send("Test", "override")
            self.assertNotIn("OFFLINE_TEST_ONLY", str(error.exception))
        finally: Webhooks._send = original

if __name__ == "__main__": unittest.main()

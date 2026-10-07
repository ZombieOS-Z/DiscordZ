"""Named Discord webhook payloads; never log URLs or authentication tokens."""
import asyncio
import copy
import json
import re
import threading
import aiohttp
import discord

_lock = threading.RLock()
_definitions = {}
_url = re.compile(r"https://(?:discord\.com|discordapp\.com)/api(?:/v\d+)?/webhooks/\d+/[A-Za-z0-9._-]+\Z")

def exists(name):
    with _lock: return name in _definitions

def bind(name, *fields):
    if len(fields) % 2: raise ValueError("Invalid webhook field metadata")
    root = {}
    aliases = {"avatarURL": "avatar_url", "iconURL": "icon_url", "allowedMentions": "allowed_mentions"}
    for i in range(0, len(fields), 2):
        path, value = fields[i:i + 2]
        parts = [aliases.get(p, p) for p in path.split(".")]
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict): raise ValueError("Conflicting webhook field: " + path)
        if parts[-1] in node: raise ValueError("Duplicate webhook field: " + path)
        node[parts[-1]] = value
    embeds = root.get("embeds", {})
    if not isinstance(embeds, dict): raise ValueError("embeds must contain named blocks")
    root["embeds"] = list(embeds.values())
    for embed in root["embeds"]:
        for field in ("thumbnail", "image"):
            if field in embed and isinstance(embed[field], str): embed[field] = {"url": embed[field]}
        if "fields" in embed: embed["fields"] = list(embed["fields"].values())
        if isinstance(embed.get("color"), str): embed["color"] = int(embed["color"].lstrip("#"), 16)
    mentions = root.get("allowed_mentions", {})
    everyone = mentions.pop("everyone", False)
    mentions["parse"] = ["everyone"] if everyone else []
    for key in ("users", "roles"):
        values = mentions.get(key, [])
        mentions[key] = json.loads(values) if isinstance(values, str) else values
    root["allowed_mentions"] = mentions
    return register(name, root)

def register(name, payload):
    payload = json.loads(payload) if isinstance(payload, str) else payload
    payload = copy.deepcopy(payload)
    if "url" in payload and not _url.fullmatch(payload["url"]):
        raise ValueError("Webhook URL must be an HTTPS Discord webhook URL")
    if len(payload.get("content", "")) > 2000:
        raise ValueError("Webhook content exceeds 2000 characters")
    embeds = payload.get("embeds", [])
    if len(embeds) > 10:
        raise ValueError("A webhook may contain at most 10 embeds")
    total = 0
    for embed in embeds:
        for key, limit in (("title", 256), ("description", 4096)):
            value = embed.get(key, "")
            if len(value) > limit: raise ValueError("Embed " + key + " is too long")
            total += len(value)
        fields = embed.get("fields", [])
        if len(fields) > 25: raise ValueError("An embed may have at most 25 fields")
        for field in fields:
            if len(field.get("name", "")) > 256 or len(field.get("value", "")) > 1024:
                raise ValueError("Embed field is too long")
            total += len(field.get("name", "")) + len(field.get("value", ""))
        for key, member, limit in (("author", "name", 256), ("footer", "text", 2048)):
            value = embed.get(key, {}).get(member, "")
            if len(value) > limit: raise ValueError("Embed " + key + " is too long")
            total += len(value)
        discord.Embed.from_dict(embed)
    if total > 6000: raise ValueError("Combined embeds exceed 6000 characters")
    with _lock:
        if name in _definitions:
            if _definitions[name] == payload: return True
            raise ValueError("Duplicate webhook: " + name)
        _definitions[name] = payload
    return True

def message_options(payload):
    mentions = payload.get("allowed_mentions", {"parse": []})
    return {"embeds": [discord.Embed.from_dict(e) for e in payload.get("embeds", [])],
            "content": payload.get("content"), "tts": bool(payload.get("tts", False)),
            "allowed_mentions": discord.AllowedMentions(
                everyone="everyone" in mentions.get("parse", []),
                users=[discord.Object(id=int(i)) for i in mentions.get("users", [])],
                roles=[discord.Object(id=int(i)) for i in mentions.get("roles", [])])}

async def _send(payload):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        webhook = discord.Webhook.from_url(payload["url"], session=session)
        options = message_options(payload)
        options["wait"] = True
        for key in ("content", "username", "avatar_url"):
            if key in payload: options[key] = payload[key]
        await webhook.send(**options)

def send(name, override=None, event_id=0, reply_to_executor=False):
    with _lock:
        if name not in _definitions: raise ValueError("Unknown webhook: " + name)
        payload = copy.deepcopy(_definitions[name])
    if override is not None:
        if len(override) > 2000: raise ValueError("Webhook content exceeds 2000 characters")
        payload["content"] = override
    if not payload.get("content") and not payload.get("embeds"):
        raise ValueError("A webhook send requires content or embeds")
    if "url" not in payload:
        import Events
        return Events.reply_payload(event_id, payload, reply_to_executor)
    if reply_to_executor:
        raise ValueError("External URL webhooks cannot reply to a command executor; use a URL-free template")
    try:
        asyncio.run(_send(payload))
    except Exception as exc:
        # aiohttp exceptions can contain token-bearing request URLs.
        raise RuntimeError("Discord webhook send failed: " + type(exc).__name__) from None
    return True

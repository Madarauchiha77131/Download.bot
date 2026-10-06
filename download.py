#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║  UNIVERSAL VIDEO DOWNLOADER — Telegram Bot                       ║
║  YouTube · TikTok · Instagram · Facebook · and more              ║
║                                                                  ║
║  • Premium (custom) emoji in every text and button               ║
║  • Animated welcome + live progress                              ║
║  • Force-join with re-verification                               ║
║  • Full-featured admin panel                                     ║
║  • Built-in health server (Render ready)                         ║
║                                                                  ║
║  Run:   python download.py                                       ║
║  Env:   BOT_TOKEN (required)  — everything else has defaults     ║
╚══════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import csv
import html
import io
import logging
import os
import platform as pyplatform
import re
import shutil
import sys
import tempfile
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote

import aiohttp
import aiosqlite
from aiohttp import web
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.enums import ChatAction, ChatMemberStatus, ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

# ════════════════════════════════════════════════════════════════════
#  CONFIG
# ════════════════════════════════════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()          # ← set on Render
OWNER_ID = int(os.getenv("OWNER_ID", "8200980090"))
DEFAULT_CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002740009398"))
DEFAULT_CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/+2Fxg6o4jEKAxOGQ1")
DEFAULT_API_BASE = os.getenv("API_BASE", "https://fvz.onrender.com")

PORT = int(os.getenv("PORT", "10000"))                   # Render injects PORT
DB_PATH = os.getenv("DB_PATH", "bot_data.db")
SELF_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
TZ_OFFSET = float(os.getenv("TZ_OFFSET_HOURS", "6"))     # Bangladesh = UTC+6
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", "6"))
TASK_TIMEOUT = int(os.getenv("TASK_TIMEOUT", "420"))     # seconds
FAIL_OPEN = os.getenv("FAIL_OPEN", "1") == "1"           # let users in if the bot can't verify the channel
BOT_BRAND = os.getenv("BOT_BRAND", "Universal Video Downloader")

START_TIME = time.time()
TZ = timezone(timedelta(hours=TZ_OFFSET))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("downloader")
logging.getLogger("aiogram.event").setLevel(logging.WARNING)

# ════════════════════════════════════════════════════════════════════
#  PREMIUM EMOJI REGISTRY      name → (custom_emoji_id, fallback)
# ════════════════════════════════════════════════════════════════════
EMOJI: dict[str, tuple[str, str]] = {
    # ── Platforms (provided) ──
    "youtube": ("5069108689810490417", "▶️"),
    "facebook": ("5933728045067145810", "📘"),
    "instagram": ("6039590179935620964", "📸"),
    "tiktok": ("6021412619913532794", "🎵"),
    # ── UI ──
    "download": ("5406745015365943482", "⬇"),
    "link": ("5271604874419647061", "🔗"),
    "ok": ("5895514131896733546", "✅"),
    "no": ("5210952531676504517", "❌"),
    "warn": ("5447644880824181073", "⚠"),
    "bell": ("5458603043203327669", "🔔"),
    "shield": ("5902016123972358349", "🛡"),
    "rocket": ("6041705726206808304", "🚀"),
    "bolt": ("5893450623449305489", "⚡"),
    "stats": ("5231200819986047254", "📊"),
    "user": ("5902335789798265487", "👤"),
    "megaphone": ("5424818078833715060", "📣"),
    "ban": ("5240241223632954241", "🚫"),
    "lock": ("5296369303661067030", "🔐"),
    "gear": ("5893161718179173515", "⚙"),
    "trash": ("5445267414562389170", "🗑"),
    "search": ("5231012545799666522", "🔍"),
    "hourglass": ("5386367538735104399", "⏳"),
    "refresh": ("5375338737028841420", "🔄"),
    "star": ("5893494861612455015", "⭐"),
    "fire": ("5424972470023104089", "🔥"),
    "globe": ("5447410659077661506", "🌐"),
    "plus": ("5397916757333654639", "➕"),
    "music": ("5463107823946717464", "🎶"),
    "play": ("5264919878082509254", "▶"),
    "image": ("5409109841538994759", "🌈"),
    "crown": ("6310083389126876253", "👑"),
    "diamond": ("5427168083074628963", "💎"),
    "info": ("5334544901428229844", "ℹ"),
    "chat": ("5443038326535759644", "💬"),
    "bulb": ("5422439311196834318", "💡"),
    "wrench": ("5341715473882955310", "🔧"),
    "clock": ("5440621591387980068", "🕰"),
    "calendar": ("5413879192267805083", "📅"),
    "free": ("5406756500108501710", "🆓"),
    "new": ("5382357040008021292", "🆕"),
    "trophy": ("5893376775781617954", "🏆"),
    "robot": ("6309920764485180319", "🤖"),
    "book": ("5222444124698853913", "📚"),
    "mail": ("5253742260054409879", "📬"),
    "pc": ("5282843764451195532", "💻"),
    "money": ("5893473283696759404", "💰"),
    "pin": ("5397782960512444700", "📌"),
    "sparkles": ("5325547803936572038", "✨"),
    "back": ("4956304191279596468", "👈"),
    "next": ("5416117059207572332", "➡"),
    "red": ("5411225014148014586", "🔴"),
    "green": ("5416081784641168838", "🟢"),
    "heart": ("5337080053119336309", "❤"),
    "party": ("5461151367559141950", "🥳"),
    "eyes": ("5210956306952758910", "👀"),
    "check": ("5206607081334906820", "✔"),
    "up": ("5244837092042750681", "📈"),
    "down": ("5246762912428603768", "📉"),
    "pencil": ("5395444784611480792", "🖊"),
    "mic": ("5294339927318739359", "🎤"),
    "phone": ("5895652322469482989", "📱"),
    "siren": ("5395695537687123235", "🚨"),
    "clip": ("5305265301917549162", "🖇"),
    "map": ("5391032818111363540", "🗺"),
    "hundred": ("5341498088408234504", "💯"),
}

TG_EMOJI_RE = re.compile(r'<tg-emoji emoji-id="\d+">(.*?)</tg-emoji>', re.S)


class _Emoji:
    """`E.ok` → `<tg-emoji emoji-id="…">✅</tg-emoji>` (works inside HTML parse mode)."""

    def __getattr__(self, name: str) -> str:
        try:
            eid, fb = EMOJI[name]
        except KeyError:
            return ""
        return f'<tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'


E = _Emoji()

# message effects (private chats only)
EFFECT_PARTY = "5046509860389126442"
EFFECT_FIRE = "5104841245755180586"
EFFECT_LIKE = "5107584321108051014"

# ════════════════════════════════════════════════════════════════════
#  PLATFORMS
# ════════════════════════════════════════════════════════════════════
PLATFORMS: dict[str, dict[str, Any]] = {
    "youtube": {"name": "YouTube", "emoji": "youtube",
                "re": re.compile(r"(youtube\.com|youtu\.be|music\.youtube\.com)", re.I)},
    "tiktok": {"name": "TikTok", "emoji": "tiktok",
               "re": re.compile(r"(tiktok\.com|vm\.tiktok|vt\.tiktok)", re.I)},
    "instagram": {"name": "Instagram", "emoji": "instagram",
                  "re": re.compile(r"(instagram\.com|instagr\.am)", re.I)},
    "facebook": {"name": "Facebook", "emoji": "facebook",
                 "re": re.compile(r"(facebook\.com|fb\.watch|fb\.com|fb\.me)", re.I)},
    "other": {"name": "Universal", "emoji": "globe", "re": re.compile(r".")},
}
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
IMG_EXT = (".jpeg", ".jpg", ".png", ".webp", ".gif")
AUDIO_EXT = (".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav")


def detect_platform(url: str) -> str:
    for key, p in PLATFORMS.items():
        if key != "other" and p["re"].search(url):
            return key
    return "other"


# ════════════════════════════════════════════════════════════════════
#  SMALL HELPERS
# ════════════════════════════════════════════════════════════════════
def esc(s: Any) -> str:
    return html.escape(str(s if s is not None else ""), quote=False)


def now() -> int:
    return int(time.time())


def fmt_ts(ts: Optional[int]) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts, TZ).strftime("%d %b %Y, %I:%M %p")


def day_start(offset_days: int = 0) -> int:
    d = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((d - timedelta(days=offset_days)).timestamp())


def fmt_dur(sec: float) -> str:
    sec = int(sec)
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = [f"{d}d" if d else "", f"{h}h" if h else "", f"{m}m" if m else "", f"{s}s"]
    return " ".join(p for p in parts if p)


def fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def bar(pct: float, width: int = 10) -> str:
    filled = max(0, min(width, round(pct / 100 * width)))
    return "▰" * filled + "▱" * (width - filled)


def short_url(url: str, n: int = 46) -> str:
    return url if len(url) <= n else url[: n - 1] + "…"


def safe_filename(name: str, default: str) -> str:
    name = re.sub(r"[^\w.\- ]", "_", name or "").strip(" .")[:80]
    return name or default


def user_label(u: dict) -> str:
    if u.get("username"):
        return f"@{u['username']}"
    return esc(u.get("first_name") or str(u["id"]))


# ════════════════════════════════════════════════════════════════════
#  BUTTON HELPERS
#
#  IMPORTANT — Telegram Bot API reality check:
#  Inline/reply keyboard buttons are plain-text controls. The Bot API has
#  no "icon_custom_emoji_id" or "style/colour" field on InlineKeyboardButton
#  or KeyboardButton, and custom (premium) emoji can only be rendered as
#  message *text* via <tg-emoji> entities — never inside a button's label,
#  and buttons cannot be colour-styled. Telegram renders all inline buttons
#  in its own fixed grey style; that is a client-side constant, not
#  something a bot can override.
#
#  So "professional colour" here comes from clean icon+label conventions
#  (Unicode emoji prefixes, consistent grouping, danger/success wording)
#  rather than fictional API fields. Every *message* still uses real
#  premium emoji via <tg-emoji> (see the E object above).
# ════════════════════════════════════════════════════════════════════
def B(text: str, *, cb: str = None, url: str = None, icon: str = None,
      style: str = None) -> InlineKeyboardButton:
    """style is accepted for readability at call-sites but only affects
    which plain-emoji prefix is used (✅/⚠️/🚫) since Telegram buttons
    can't be colour-styled."""
    prefix = ""
    if icon and icon in EMOJI:
        prefix = EMOJI[icon][1] + " "
    elif style == "success":
        prefix = "✅ "
    elif style == "danger":
        prefix = "🚫 "
    kw: dict[str, Any] = {"text": f"{prefix}{text}"}
    if cb:
        kw["callback_data"] = cb
    if url:
        kw["url"] = url
    return InlineKeyboardButton(**kw)


def RB(text: str, *, icon: str = None, style: str = None) -> KeyboardButton:
    prefix = (EMOJI[icon][1] + " ") if icon and icon in EMOJI else ""
    return KeyboardButton(text=f"{prefix}{text}")


def KB(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


class EmojiFallbackMiddleware(BaseRequestMiddleware):
    """If Telegram ever rejects a <tg-emoji> entity in message text/caption
    (e.g. the bot doesn't have Telegram Premium so custom emoji sending is
    restricted, or an emoji ID is invalid/deleted), retry once with the
    plain Unicode fallback so the bot never hard-fails on this."""

    async def __call__(self, make_request, bot, method):
        try:
            return await make_request(bot, method)
        except TelegramBadRequest as exc:
            msg = str(exc).lower()
            if "not modified" in msg or "message to edit not found" in msg:
                raise
            changed = False
            for attr in ("text", "caption"):
                v = getattr(method, attr, None)
                if isinstance(v, str) and "<tg-emoji" in v:
                    setattr(method, attr, TG_EMOJI_RE.sub(r"\1", v))
                    changed = True
            if changed and "emoji" in msg:
                log.warning("Premium emoji rejected (%s) — retrying with plain emoji", exc)
                return await make_request(bot, method)
            raise


# ════════════════════════════════════════════════════════════════════
#  DATABASE
# ════════════════════════════════════════════════════════════════════
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    username TEXT, first_name TEXT,
    joined_at INTEGER, last_seen INTEGER,
    downloads INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0,
    vip INTEGER DEFAULT 0,
    blocked INTEGER DEFAULT 0,
    auto_send INTEGER DEFAULT 1,
    want_audio INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY, added_at INTEGER);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS channels(
    chat_id INTEGER PRIMARY KEY, title TEXT, link TEXT
);
CREATE TABLE IF NOT EXISTS downloads(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, platform TEXT, url TEXT,
    status TEXT, error TEXT, duration REAL, created_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_dl_user ON downloads(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_dl_time ON downloads(created_at);
"""

DEFAULT_SETTINGS = {
    "maintenance": "0",
    "force_join": "1",
    "daily_limit": "0",          # 0 = unlimited
    "auto_send": "1",
    "max_upload_mb": "49",
    "api_base": DEFAULT_API_BASE,
    "welcome_text": "",
    "notify_new": "1",
    "animations": "1",
    "p_youtube": "1", "p_tiktok": "1", "p_instagram": "1",
    "p_facebook": "1", "p_other": "1",
}


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: Optional[aiosqlite.Connection] = None
        self.settings: dict[str, str] = dict(DEFAULT_SETTINGS)

    async def connect(self) -> None:
        d = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(d, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()
        for r in await self.q("SELECT key, value FROM settings"):
            self.settings[r["key"]] = r["value"]
        if not await self.q1("SELECT 1 FROM channels LIMIT 1"):
            await self.x("INSERT OR IGNORE INTO channels(chat_id,title,link) VALUES(?,?,?)",
                         (DEFAULT_CHANNEL_ID, "Official Channel", DEFAULT_CHANNEL_LINK))

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    async def q(self, sql: str, params: tuple = ()) -> list[dict]:
        async with self.conn.execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def q1(self, sql: str, params: tuple = ()) -> Optional[dict]:
        rows = await self.q(sql, params)
        return rows[0] if rows else None

    async def scalar(self, sql: str, params: tuple = ()) -> int:
        row = await self.q1(sql, params)
        if not row:
            return 0
        v = next(iter(row.values()))
        return v or 0

    async def x(self, sql: str, params: tuple = ()) -> int:
        cur = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cur.rowcount

    # ── settings ──
    def get(self, key: str) -> str:
        return self.settings.get(key, DEFAULT_SETTINGS.get(key, ""))

    def flag(self, key: str) -> bool:
        return self.get(key) == "1"

    def num(self, key: str) -> int:
        try:
            return int(float(self.get(key)))
        except ValueError:
            return int(float(DEFAULT_SETTINGS.get(key, "0") or 0))

    async def set(self, key: str, value: Any) -> None:
        self.settings[key] = str(value)
        await self.x("INSERT INTO settings(key,value) VALUES(?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

    async def toggle(self, key: str) -> bool:
        new = "0" if self.flag(key) else "1"
        await self.set(key, new)
        return new == "1"

    # ── users ──
    async def touch_user(self, u) -> tuple[dict, bool]:
        row = await self.q1("SELECT * FROM users WHERE id=?", (u.id,))
        t = now()
        if row is None:
            await self.x("INSERT INTO users(id,username,first_name,joined_at,last_seen) VALUES(?,?,?,?,?)",
                         (u.id, u.username, u.first_name, t, t))
            return await self.q1("SELECT * FROM users WHERE id=?", (u.id,)), True
        await self.x("UPDATE users SET username=?, first_name=?, last_seen=?, blocked=0 WHERE id=?",
                     (u.username, u.first_name, t, u.id))
        row.update(username=u.username, first_name=u.first_name, last_seen=t, blocked=0)
        return row, False

    async def get_user(self, uid: int) -> Optional[dict]:
        return await self.q1("SELECT * FROM users WHERE id=?", (uid,))

    async def downloads_today(self, uid: int) -> int:
        return await self.scalar(
            "SELECT COUNT(*) FROM downloads WHERE user_id=? AND status='ok' AND created_at>=?",
            (uid, day_start()))

    async def log_download(self, uid: int, platform: str, url: str, status: str,
                           error: str = "", duration: float = 0) -> None:
        await self.x("INSERT INTO downloads(user_id,platform,url,status,error,duration,created_at) "
                     "VALUES(?,?,?,?,?,?,?)", (uid, platform, url, status, error[:300], duration, now()))
        if status == "ok":
            await self.x("UPDATE users SET downloads=downloads+1 WHERE id=?", (uid,))

    # ── admins ──
    async def admin_ids(self) -> set[int]:
        return {r["id"] for r in await self.q("SELECT id FROM admins")}

    # ── channels ──
    async def channels(self) -> list[dict]:
        return await self.q("SELECT * FROM channels")


db = Database(DB_PATH)
ADMINS: set[int] = set()
HTTP: Optional[aiohttp.ClientSession] = None
SEM = asyncio.Semaphore(MAX_CONCURRENT)


def is_admin(uid: int) -> bool:
    return uid == OWNER_ID or uid in ADMINS


def is_owner(uid: int) -> bool:
    return uid == OWNER_ID


# ════════════════════════════════════════════════════════════════════
#  SAFE TELEGRAM HELPERS
# ════════════════════════════════════════════════════════════════════
async def safe_edit(msg: Message, text: str, kb: InlineKeyboardMarkup = None) -> bool:
    try:
        if msg.photo or msg.video or msg.document:
            await msg.edit_caption(caption=text, reply_markup=kb)
        else:
            await msg.edit_text(text, reply_markup=kb)
        return True
    except TelegramRetryAfter as e:
        await asyncio.sleep(min(e.retry_after, 5))
    except TelegramBadRequest as e:
        if "not modified" not in str(e).lower():
            log.debug("edit failed: %s", e)
    except TelegramAPIError as e:
        log.debug("edit api error: %s", e)
    return False


async def show(event, text: str, kb: InlineKeyboardMarkup = None) -> None:
    """Edit in place for callbacks, send fresh for messages."""
    if isinstance(event, CallbackQuery):
        msg = event.message
        try:
            if msg.photo or msg.video or msg.document:
                await msg.edit_caption(caption=text, reply_markup=kb)
            else:
                await msg.edit_text(text, reply_markup=kb)
        except TelegramBadRequest as e:
            if "not modified" in str(e).lower():
                return
            with suppress(Exception):
                await msg.delete()
            await msg.answer(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


async def notify_owner(bot: Bot, text: str, kb: InlineKeyboardMarkup = None) -> None:
    with suppress(Exception):
        await bot.send_message(OWNER_ID, text, reply_markup=kb)


_last_alert: dict[str, float] = {}


async def alert_once(bot: Bot, key: str, text: str, every: int = 1800) -> None:
    if time.time() - _last_alert.get(key, 0) > every:
        _last_alert[key] = time.time()
        await notify_owner(bot, text)


# ════════════════════════════════════════════════════════════════════
#  FORCE JOIN
# ════════════════════════════════════════════════════════════════════
JOIN_CACHE: dict[int, float] = {}      # uid → time of last successful check
JOIN_TTL = 45                           # seconds — leavers are caught again quickly


async def missing_channels(bot: Bot, uid: int, use_cache: bool = True) -> list[dict]:
    if is_admin(uid) or not db.flag("force_join"):
        return []
    if use_cache and time.time() - JOIN_CACHE.get(uid, 0) < JOIN_TTL:
        return []
    missing: list[dict] = []
    for ch in await db.channels():
        try:
            m = await bot.get_chat_member(ch["chat_id"], uid)
            joined = m.status in (ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR,
                                  ChatMemberStatus.MEMBER) or (
                m.status == ChatMemberStatus.RESTRICTED and getattr(m, "is_member", False))
            if not joined:
                missing.append(ch)
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            log.warning("Cannot verify %s in %s: %s", uid, ch["chat_id"], e)
            await alert_once(
                bot, f"fj{ch['chat_id']}",
                f"{E.warn} <b>Force-join problem</b>\n\nI can't check members of "
                f"<code>{ch['chat_id']}</code>.\nMake sure the bot is an <b>admin</b> in that channel.\n"
                f"<i>Mode: {'users allowed through' if FAIL_OPEN else 'users blocked'}</i>")
            if not FAIL_OPEN:
                missing.append(ch)
        except TelegramRetryAfter as e:
            await asyncio.sleep(min(e.retry_after, 3))
    if not missing:
        JOIN_CACHE[uid] = time.time()
    else:
        JOIN_CACHE.pop(uid, None)
    return missing


def join_text(missing: list[dict]) -> str:
    return (
        f"{E.lock} <b>Access Required</b>\n\n"
        f"{E.megaphone} To use <b>{esc(BOT_BRAND)}</b>, please join our official "
        f"channel{'s' if len(missing) > 1 else ''} first.\n\n"
        f"{E.check} Tap <b>Join</b>, then press <b>Verify</b> below.\n"
        f"{E.warn} <i>Leaving the channel later will lock the bot again.</i>"
    )


def join_kb(missing: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for i, ch in enumerate(missing, 1):
        if ch.get("link"):
            label = "Join Channel" if len(missing) == 1 else f"Join Channel {i}"
            rows.append([B(label, url=ch["link"], icon="megaphone", style="primary")])
    rows.append([B("Verify — I've Joined", cb="fj:verify", icon="ok", style="success")])
    return KB(*rows)


# ════════════════════════════════════════════════════════════════════
#  MIDDLEWARE  (user tracking · ban · maintenance · throttle · force-join)
# ════════════════════════════════════════════════════════════════════
class GateMiddleware(BaseMiddleware):
    def __init__(self):
        self.last: dict[int, float] = {}

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user is None or user.is_bot:
            return await handler(event, data)

        is_cb = isinstance(event, CallbackQuery)
        chat = event.message.chat if is_cb and event.message else getattr(event, "chat", None)
        if chat is not None and chat.type != "private":
            return                                    # private chats only
        bot: Bot = data["bot"]

        # ── throttle ──
        t = time.monotonic()
        if t - self.last.get(user.id, 0) < 0.35 and not is_admin(user.id):
            if is_cb:
                with suppress(Exception):
                    await event.answer("Slow down a little…")
            return
        self.last[user.id] = t

        row, is_new = await db.touch_user(user)
        data["db_user"] = row
        if is_new and db.flag("notify_new"):
            asyncio.create_task(notify_owner(
                bot,
                f"{E.new} <b>New user</b>\n{E.user} {esc(user.full_name)} "
                f"{'(@' + esc(user.username) + ')' if user.username else ''}\n"
                f"{E.pin} <code>{user.id}</code>",
                KB([B("Open profile", cb=f"adm:uc:{user.id}", icon="user", style="primary")])))

        # ── banned ──
        if row["banned"] and not is_admin(user.id):
            text = (f"{E.ban} <b>Access Denied</b>\n\nYour account has been restricted from using this bot.\n"
                    f"{E.chat} Contact the owner if you think this is a mistake.")
            if is_cb:
                with suppress(Exception):
                    await event.answer("You are banned.", show_alert=True)
            else:
                await event.answer(text)
            return

        # ── maintenance ──
        if db.flag("maintenance") and not is_admin(user.id):
            text = (f"{E.wrench} <b>Under Maintenance</b>\n\nWe're upgrading things behind the scenes.\n"
                    f"{E.clock} Please try again in a little while.")
            if is_cb:
                with suppress(Exception):
                    await event.answer("Bot is under maintenance.", show_alert=True)
            else:
                await event.answer(text)
            return

        # ── force join ──
        if not (is_cb and event.data == "fj:verify"):
            missing = await missing_channels(bot, user.id)
            if missing:
                if is_cb:
                    with suppress(Exception):
                        await event.answer("Join the channel first.", show_alert=True)
                    await show(event, join_text(missing), join_kb(missing))
                else:
                    await event.answer(join_text(missing), reply_markup=join_kb(missing))
                return

        return await handler(event, data)


# ════════════════════════════════════════════════════════════════════
#  DOWNLOADER ENGINE  (talks to the same backend as the web app)
# ════════════════════════════════════════════════════════════════════
class DownloaderError(Exception):
    pass


class Cancelled(Exception):
    pass


def api_base() -> str:
    return db.get("api_base").rstrip("/")


def proxy_url(link: str, name: str) -> str:
    return f"{api_base()}/api/proxy_download?url={quote(link, safe='')}&name={quote(name or 'download', safe='')}"


async def _json(resp: aiohttp.ClientResponse) -> dict:
    try:
        data = await resp.json(content_type=None)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def api_server_status() -> tuple[bool, float]:
    t = time.monotonic()
    try:
        async with HTTP.get(f"{api_base()}/api/server_status",
                            timeout=aiohttp.ClientTimeout(total=15)) as r:
            d = await _json(r)
            return bool(d.get("online", r.status == 200)), (time.monotonic() - t) * 1000
    except Exception:
        return False, (time.monotonic() - t) * 1000


async def api_submit(url: str) -> str:
    try:
        async with HTTP.post(f"{api_base()}/api/add", json={"url": url},
                             timeout=aiohttp.ClientTimeout(total=45)) as r:
            d = await _json(r)
            if r.status >= 400:
                raise DownloaderError(d.get("error") or d.get("detail") or "The server rejected this link.")
            tid = d.get("task_id")
            if not tid:
                raise DownloaderError("Server returned no task ID.")
            return tid
    except asyncio.TimeoutError:
        raise DownloaderError("Server is waking up — please try again in a few seconds.")
    except aiohttp.ClientError:
        raise DownloaderError("Couldn't reach the download server. Try again shortly.")


PHASES = {
    "waking_up": (8, 24, "Waking up server nodes"),
    "pending": (22, 40, "Waiting in queue"),
    "processing": (40, 80, "Extracting HD stream"),
    "uploading": (80, 96, "Packaging your links"),
}


async def api_wait(task_id: str, on_tick, job: dict) -> dict:
    """Poll the backend with smart back-off. `on_tick(pct, label)` drives the animation."""
    start = time.monotonic()
    delay, pct, fails = 1.4, 6, 0
    while time.monotonic() - start < TASK_TIMEOUT:
        if job.get("cancel"):
            raise Cancelled()
        try:
            async with HTTP.get(f"{api_base()}/api/status/{task_id}",
                                timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status >= 500:
                    raise aiohttp.ClientError("status 5xx")
                d = await _json(r)
            fails = 0
            st = d.get("status", "processing")
            if st == "completed":
                await on_tick(100, "Done")
                return d
            if st == "failed":
                raise DownloaderError(d.get("error") or "Processing failed on the server.")
            lo, hi, label = PHASES.get(st, PHASES["processing"])
            if st == "pending" and (d.get("queue_position") or 0) > 1:
                label = f"Queue position #{d['queue_position']}"
            pct = min(max(pct, lo) + 2, hi)
            await on_tick(pct, label)
            delay = 2.0 if st in ("processing", "uploading") else min(delay * 1.25, 4.5)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            fails += 1
            if fails >= 8:
                raise DownloaderError("Lost connection to the download server.")
            delay = min(delay * 1.5, 5)
        await asyncio.sleep(delay)
    raise DownloaderError("Request timed out. Please try again in a few moments.")


@asynccontextmanager
async def fetch_to_disk(url: str, max_bytes: int):
    """Stream a remote file to a temp dir. Yields path or None (too big / failed)."""
    tmp = tempfile.mkdtemp(prefix="dl_")
    path = os.path.join(tmp, "file.bin")
    ok = False
    try:
        async with HTTP.get(url, timeout=aiohttp.ClientTimeout(total=300, sock_connect=25)) as r:
            if r.status == 200:
                cl = int(r.headers.get("Content-Length") or 0)
                if not cl or cl <= max_bytes:
                    size = 0
                    with open(path, "wb") as f:
                        async for chunk in r.content.iter_chunked(256 * 1024):
                            size += len(chunk)
                            if size > max_bytes:
                                break
                            f.write(chunk)
                        else:
                            ok = size > 0
        yield (path, tmp) if ok else None
    except Exception as e:
        log.info("fetch_to_disk failed: %s", e)
        yield None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ════════════════════════════════════════════════════════════════════
#  UI — TEXTS & KEYBOARDS
# ════════════════════════════════════════════════════════════════════
def platforms_line() -> str:
    return (f"{E.youtube} YouTube   {E.facebook} Facebook\n"
            f"{E.instagram} Instagram   {E.tiktok} TikTok")


def welcome_text(name: str) -> str:
    custom = db.get("welcome_text").strip()
    if custom:
        return custom.replace("{name}", esc(name))
    return (
        f"{E.rocket} <b>{esc(BOT_BRAND)}</b>\n\n"
        f"{E.sparkles} Welcome, <b>{esc(name)}</b>!\n"
        f"Paste any video link and get your media in seconds.\n\n"
        f"{platforms_line()}\n\n"
        f"{E.ok} HD quality   {E.ok} No watermark\n"
        f"{E.ok} MP3 audio    {E.ok} Photo slideshows\n"
        f"{E.free} Free — no login required\n\n"
        f"{E.link} <b>Send a link to begin.</b>"
    )


def main_menu(uid: int) -> InlineKeyboardMarkup:
    rows = [
        [B("Download", cb="menu:download", icon="download", style="primary")],
        [B("Platforms", cb="menu:platforms", icon="globe"),
         B("My Profile", cb="menu:profile", icon="user")],
        [B("History", cb="menu:history", icon="clock"),
         B("Settings", cb="menu:settings", icon="gear")],
        [B("FAQ", cb="menu:faq", icon="bulb"),
         B("About", cb="menu:about", icon="info")],
    ]
    link = next((c["link"] for c in JOIN_LINKS if c.get("link")), None)
    if link:
        rows.append([B("Official Channel", url=link, icon="megaphone", style="success")])
    if is_admin(uid):
        rows.append([B("Admin Panel", cb="adm:home", icon="shield", style="danger")])
    return KB(*rows)


JOIN_LINKS: list[dict] = []          # cached channel list for the menu button


def reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [RB("Download", icon="download", style="primary"), RB("Profile", icon="user")],
            [RB("Platforms", icon="globe"), RB("Help", icon="bulb", style="success")],
        ],
        resize_keyboard=True, is_persistent=True,
        input_field_placeholder="Paste a video link…",
    )


def back_kb(to: str = "menu:home") -> InlineKeyboardMarkup:
    return KB([B("Back", cb=to, icon="back")])


FAQ_ITEMS = [
    ("Is it completely free?",
     "Yes! This bot is 100% free. No registration, no subscription and no hidden fees — just paste your link and download."),
    ("Will the video have a watermark?",
     "No watermarks at all. The original clean HD video is downloaded directly."),
    ("Why is my download failing?",
     "Make sure the account is public (not private), the link is complete, and try copying it again."),
    ("Can I download private videos?",
     "No. Only videos from public accounts can be downloaded. Private videos are protected."),
    ("Is there a daily limit?",
     "__LIMIT__"),
    ("What formats are supported?",
     "MP4 (HD video), MP3 (audio only) and JPG (for photo slideshows). All files are high quality."),
]


def faq_limit_text() -> str:
    n = db.num("daily_limit")
    return ("No limits — download as many as you like, completely free."
            if n <= 0 else f"Free users can download up to {n} items per day. VIP members are unlimited.")


# ════════════════════════════════════════════════════════════════════
#  ROUTERS & STATES
# ════════════════════════════════════════════════════════════════════
user_router = Router(name="user")
admin_router = Router(name="admin")
ACTIVE: dict[int, dict] = {}          # uid → job info (one download at a time per user)


async def play_welcome(bot: Bot, chat_id: int, user) -> None:
    """Animated /start: loading frames → welcome card (with confetti effect)."""
    name = user.first_name or "friend"
    msg = await bot.send_message(
        chat_id, f"{E.sparkles} <b>Initializing…</b>\n\n{bar(0)} 0%", reply_markup=reply_keyboard())
    if db.flag("animations"):
        frames = [
            (25, E.bolt, "Connecting to servers"),
            (55, E.shield, "Securing your session"),
            (80, E.globe, "Loading platforms"),
            (100, E.rocket, "Ready to go"),
        ]
        for pct, ico, label in frames:
            await asyncio.sleep(0.45)
            await safe_edit(msg, f"{ico} <b>{label}…</b>\n\n{bar(pct)} {pct}%")
        await asyncio.sleep(0.4)
    with suppress(Exception):
        await msg.delete()
    kb = main_menu(user.id)
    try:
        await bot.send_message(chat_id, welcome_text(name), reply_markup=kb,
                               message_effect_id=EFFECT_PARTY)
    except TelegramAPIError:
        await bot.send_message(chat_id, welcome_text(name), reply_markup=kb)


# ════════════════════════════════════════════════════════════════════
#  USER HANDLERS
# ════════════════════════════════════════════════════════════════════
@user_router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    await refresh_join_links()
    await play_welcome(bot, message.chat.id, message.from_user)


@user_router.callback_query(F.data == "fj:verify")
async def cb_verify(cb: CallbackQuery, bot: Bot):
    JOIN_CACHE.pop(cb.from_user.id, None)
    missing = await missing_channels(bot, cb.from_user.id, use_cache=False)
    if missing:
        await cb.answer("❌ You haven't joined yet. Join the channel, then press Verify.", show_alert=True)
        return
    await cb.answer("✅ Verified — welcome!")
    with suppress(Exception):
        await cb.message.delete()
    await refresh_join_links()
    await play_welcome(bot, cb.message.chat.id, cb.from_user)


@user_router.callback_query(F.data == "menu:home")
async def cb_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await show(cb, welcome_text(cb.from_user.first_name or "friend"), main_menu(cb.from_user.id))


@user_router.message(Command("help"))
@user_router.message(F.text == "Help")
async def msg_help(message: Message):
    await message.answer(help_text(), reply_markup=back_kb())


@user_router.message(F.text == "Download")
@user_router.callback_query(F.data == "menu:download")
async def ev_download(event):
    if isinstance(event, CallbackQuery):
        await event.answer()
    await show(event,
               f"{E.download} <b>Send me a link</b>\n\n"
               f"{E.link} Paste a video or post URL from:\n{platforms_line()}\n\n"
               f"{E.bolt} I'll fetch HD video, MP3 audio or images for you.",
               back_kb())


def help_text() -> str:
    return (
        f"{E.bulb} <b>How it works</b>\n\n"
        f"{E.check} <b>1.</b> Copy a video link\n"
        f"{E.check} <b>2.</b> Paste it here\n"
        f"{E.check} <b>3.</b> Pick HD video, MP3 or images\n\n"
        f"{platforms_line()}\n\n"
        f"{E.warn} Only public content can be downloaded.\n"
        f"{E.book} Commands: /start · /profile · /help"
    )


@user_router.message(F.text == "Platforms")
@user_router.callback_query(F.data == "menu:platforms")
async def ev_platforms(event):
    if isinstance(event, CallbackQuery):
        await event.answer()
    rows = []
    for key, p in PLATFORMS.items():
        if key == "other":
            continue
        on = db.flag(f"p_{key}")
        rows.append(f"{E[p['emoji']] if False else getattr(E, p['emoji'])} <b>{p['name']}</b> — "
                    f"{E.green if on else E.red} {'LIVE' if on else 'OFF'}")
    text = (
        f"{E.globe} <b>Supported Platforms</b>\n\n" + "\n".join(rows) +
        f"\n\n{E.download} <b>Download types</b>\n"
        f"{E.play} HD Video (MP4) — no watermark\n"
        f"{E.music} Audio only (MP3) — high quality\n"
        f"{E.image} Photo slideshow — all images\n"
        f"{E.diamond} Original quality — no compression"
    )
    await show(event, text, back_kb())


@user_router.message(Command("profile"))
@user_router.message(F.text == "Profile")
@user_router.callback_query(F.data == "menu:profile")
async def ev_profile(event, db_user: dict):
    if isinstance(event, CallbackQuery):
        await event.answer()
    u = await db.get_user(event.from_user.id) or db_user
    today = await db.downloads_today(u["id"])
    limit = db.num("daily_limit")
    rank = await db.scalar("SELECT COUNT(*)+1 FROM users WHERE downloads>?", (u["downloads"],))
    tier = f"{E.crown} VIP" if u["vip"] else f"{E.user} Free"
    if is_admin(u["id"]):
        tier = f"{E.shield} Admin"
    usage = "Unlimited" if (limit <= 0 or u["vip"] or is_admin(u["id"])) else f"{today}/{limit}"
    text = (
        f"{E.user} <b>My Profile</b>\n\n"
        f"{E.pin} ID: <code>{u['id']}</code>\n"
        f"{E.star} Plan: {tier}\n"
        f"{E.download} Total downloads: <b>{u['downloads']}</b>\n"
        f"{E.bolt} Today: <b>{usage}</b>\n"
        f"{E.trophy} Rank: <b>#{rank}</b>\n"
        f"{E.calendar} Joined: {fmt_ts(u['joined_at'])}"
    )
    await show(event, text, back_kb())


@user_router.callback_query(F.data == "menu:history")
async def cb_history(cb: CallbackQuery):
    await cb.answer()
    rows = await db.q("SELECT * FROM downloads WHERE user_id=? ORDER BY id DESC LIMIT 10", (cb.from_user.id,))
    if not rows:
        body = f"{E.eyes} Nothing here yet — send a link to get started."
    else:
        lines = []
        for r in rows:
            p = PLATFORMS.get(r["platform"], PLATFORMS["other"])
            lines.append(f"{getattr(E, p['emoji'])} <b>{p['name']}</b> · "
                         f"{E.ok if r['status'] == 'ok' else E.no} · "
                         f"<i>{fmt_ts(r['created_at'])}</i>")
        body = "\n".join(lines)
    await show(cb, f"{E.clock} <b>Recent Downloads</b>\n\n{body}", back_kb())


def settings_kb(u: dict) -> InlineKeyboardMarkup:
    return KB(
        [B(f"Auto-send file: {'ON' if u['auto_send'] else 'OFF'}", cb="set:auto_send",
           icon="ok" if u["auto_send"] else "no", style="success" if u["auto_send"] else "danger")],
        [B(f"Also send MP3: {'ON' if u['want_audio'] else 'OFF'}", cb="set:want_audio",
           icon="music", style="success" if u["want_audio"] else None)],
        [B("Back", cb="menu:home", icon="back")],
    )


SETTINGS_TEXT = (
    f"{E.gear} <b>Settings</b>\n\n"
    f"{E.download} <b>Auto-send file</b> — the bot uploads the video straight into this chat "
    f"(files under the size limit).\n"
    f"{E.music} <b>Also send MP3</b> — when audio is available, receive it as well."
)


@user_router.callback_query(F.data == "menu:settings")
async def cb_settings(cb: CallbackQuery):
    await cb.answer()
    u = await db.get_user(cb.from_user.id)
    await show(cb, SETTINGS_TEXT, settings_kb(u))


@user_router.callback_query(F.data.in_({"set:auto_send", "set:want_audio"}))
async def cb_setting_toggle(cb: CallbackQuery):
    col = cb.data.split(":")[1]
    u = await db.get_user(cb.from_user.id)
    new = 0 if u[col] else 1
    await db.x(f"UPDATE users SET {col}=? WHERE id=?", (new, u["id"]))
    u[col] = new
    await cb.answer("Saved ✓")
    await show(cb, SETTINGS_TEXT, settings_kb(u))


@user_router.callback_query(F.data == "menu:faq")
async def cb_faq(cb: CallbackQuery):
    await cb.answer()
    rows = [[B(q, cb=f"faq:{i}", icon="bulb")] for i, (q, _) in enumerate(FAQ_ITEMS)]
    rows.append([B("Back", cb="menu:home", icon="back")])
    await show(cb, f"{E.bulb} <b>Frequently Asked Questions</b>\n\nTap a question:", KB(*rows))


@user_router.callback_query(F.data.startswith("faq:"))
async def cb_faq_item(cb: CallbackQuery):
    await cb.answer()
    q, a = FAQ_ITEMS[int(cb.data.split(":")[1])]
    a = faq_limit_text() if a == "__LIMIT__" else a
    await show(cb, f"{E.bulb} <b>{esc(q)}</b>\n\n{E.check} {esc(a)}", back_kb("menu:faq"))


@user_router.callback_query(F.data == "menu:about")
async def cb_about(cb: CallbackQuery, bot: Bot):
    await cb.answer()
    me = await bot.me()
    await show(cb,
               f"{E.info} <b>About</b>\n\n"
               f"{E.robot} <b>{esc(BOT_BRAND)}</b> (@{esc(me.username)})\n"
               f"{E.shield} Secure · {E.bolt} Fast · {E.free} Free\n\n"
               f"{E.warn} <i>For personal use only. Respect creators' rights.</i>",
               back_kb())


@user_router.callback_query(F.data.startswith("dl:cancel"))
async def cb_cancel(cb: CallbackQuery):
    job = ACTIVE.get(cb.from_user.id)
    if job:
        job["cancel"] = True
    await cb.answer("Cancelling…")


async def refresh_join_links():
    global JOIN_LINKS
    JOIN_LINKS = await db.channels()


# ════════════════════════════════════════════════════════════════════
#  CORE DOWNLOAD FLOW
# ════════════════════════════════════════════════════════════════════
LOADER_FRAMES = [
    (6, "bolt", "Connecting to pipeline"),
    (18, "shield", "Dispatching request"),
]


async def animate_loader(bot: Bot, chat_id: int, msg_id: int, job: dict, platform_key: str) -> None:
    """Background task: keeps the progress message moving smoothly."""
    p = PLATFORMS[platform_key]
    icon = getattr(E, p["emoji"])
    spinner = ["◐", "◓", "◑", "◒"]
    i = 0
    while not job.get("stop"):
        pct = job.get("pct", 6)
        label = job.get("label", "Working")
        text = (
            f"{icon} <b>{p['name']}</b> · {spinner[i % 4]} <i>{esc(label)}…</i>\n\n"
            f"{bar(pct)}  <b>{pct}%</b>\n"
            f"{E.hourglass} <i>Please wait, this won't take long.</i>"
        )
        with suppress(Exception):
            await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id,
                                        reply_markup=KB([B("Cancel", cb="dl:cancel", icon="no", style="danger")]))
        i += 1
        await asyncio.sleep(1.1)


async def deliver_files(bot: Bot, chat_id: int, user_row: dict, data: dict, platform_key: str,
                        status_msg: Message) -> int:
    """Send proxied media back to the user. Returns number of items delivered."""
    files = data.get("files") or []
    direct_link = data.get("direct_link")
    thumb = data.get("thumbnail") or data.get("poster")
    max_bytes = db.num("max_upload_mb") * 1024 * 1024
    delivered = 0

    image_files = [f for f in files if (f.get("name") or "").lower().endswith(IMG_EXT)]
    media_files = [f for f in files if not (f.get("name") or "").lower().endswith(IMG_EXT)]
    want_audio = bool(user_row.get("want_audio"))
    auto_send = bool(user_row.get("auto_send"))

    entries: list[tuple[str, str, bool]] = []     # (link, name, is_audio)
    if direct_link:
        entries.append((direct_link, "video.mp4", False))
    for f in media_files:
        name = f.get("name") or "media"
        is_audio = name.lower().endswith(AUDIO_EXT)
        if is_audio and not want_audio and direct_link:
            continue
        entries.append((f["link"], name, is_audio))

    p = PLATFORMS[platform_key]
    icon = getattr(E, p["emoji"])

    for link, name, is_audio in entries:
        fname = safe_filename(name, "audio.mp3" if is_audio else "video.mp4")
        caption = (f"{E.music if is_audio else E.play} <b>{'Audio' if is_audio else 'HD Video'}</b> · "
                   f"{icon} {p['name']}\n{E.robot} via {esc(BOT_BRAND)}")
        purl = proxy_url(link, fname)
        if auto_send:
            async with fetch_to_disk(purl, max_bytes) as got:
                if got:
                    path, _ = got
                    try:
                        file = FSInputFile(path, filename=fname)
                        if is_audio:
                            await bot.send_audio(chat_id, file, caption=caption, title=fname)
                        else:
                            await bot.send_video(chat_id, file, caption=caption, supports_streaming=True)
                        delivered += 1
                        continue
                    except TelegramAPIError as e:
                        log.info("upload failed, falling back to link: %s", e)
        # fallback: send as a tappable link
        await bot.send_message(
            chat_id,
            f"{E.download} <b>{esc(fname)}</b>\n{E.link} Tap below to download:",
            reply_markup=KB([B("Download", url=purl, icon="download", style="primary")]))
        delivered += 1

    if image_files:
        media_group = []
        extra_links = []
        for f in image_files[:10]:
            iurl = f.get("link")
            if iurl:
                media_group.append(InputMediaPhoto(media=iurl))
            extra_links.append((iurl, f.get("name") or "image.jpg"))
        if media_group:
            with suppress(TelegramAPIError):
                await bot.send_media_group(chat_id, media_group)
                delivered += len(media_group)
        if len(image_files) > 10:
            rows = [[B(f"Image {i+1}", url=proxy_url(u, n), icon="image")]
                    for i, (u, n) in enumerate(extra_links[10:20])]
            await bot.send_message(chat_id, f"{E.image} <b>More images</b>", reply_markup=KB(*rows))

    if not delivered and thumb:
        with suppress(TelegramAPIError):
            await bot.send_photo(chat_id, thumb, caption=f"{icon} Preview")
            delivered += 1

    return delivered


@user_router.message(F.text.func(lambda t: t and URL_RE.search(t)))
async def msg_link(message: Message, bot: Bot, db_user: dict):
    uid = message.from_user.id
    url_m = URL_RE.search(message.text)
    url = url_m.group(0)
    platform_key = detect_platform(url)
    p = PLATFORMS[platform_key]

    if not db.flag(f"p_{platform_key}") and platform_key != "other":
        await message.answer(
            f"{E.warn} <b>{p['name']} is temporarily disabled</b>\nPlease try another platform or check back later.",
            reply_markup=back_kb())
        return

    if uid in ACTIVE:
        await message.answer(f"{E.hourglass} You already have a download in progress — please wait for it to finish.")
        return

    limit = db.num("daily_limit")
    if limit > 0 and not db_user.get("vip") and not is_admin(uid):
        used = await db.downloads_today(uid)
        if used >= limit:
            await message.answer(
                f"{E.warn} <b>Daily limit reached</b>\n\nYou've used {used}/{limit} downloads today.\n"
                f"{E.crown} Ask the owner about VIP access for unlimited downloads.",
                reply_markup=back_kb())
            return

    online, ping = await api_server_status()
    if not online:
        await message.answer(
            f"{E.no} <b>Server unavailable</b>\n\n{E.hourglass} The download engine is waking up or offline.\n"
            f"Please try again in about a minute.")
        await db.log_download(uid, platform_key, url, "fail", "server_offline")
        return

    icon = getattr(E, p["emoji"])
    status = await message.answer(
        f"{icon} <b>{p['name']} detected</b>\n\n{bar(5)}  <b>5%</b>\n{E.bolt} <i>Starting pipeline…</i>",
        reply_markup=KB([B("Cancel", cb="dl:cancel", icon="no", style="danger")]))

    job = {"pct": 6, "label": "Starting", "cancel": False, "stop": False}
    ACTIVE[uid] = job
    anim_task = asyncio.create_task(animate_loader(bot, message.chat.id, status.message_id, job, platform_key))
    t0 = time.monotonic()

    async def on_tick(pct, label):
        job["pct"], job["label"] = pct, label

    try:
        async with SEM:
            task_id = await api_submit(url)
            data = await api_wait(task_id, on_tick, job)

        job["stop"] = True
        await anim_task

        files = data.get("files") or []
        has_media = bool(files or data.get("direct_link"))
        if not has_media:
            await safe_edit(status, f"{E.no} <b>No downloadable media found</b>\n\n"
                                    f"{E.warn} The server processed the link but didn't find anything to download.")
            await db.log_download(uid, platform_key, url, "fail", "empty")
            return

        await safe_edit(status, f"{E.ok} <b>{p['name']} · Ready!</b>\n\n{bar(100)}  <b>100%</b>\n"
                                f"{E.rocket} <i>Delivering your media…</i>")

        u_row = await db.get_user(uid)
        delivered = await deliver_files(bot, message.chat.id, u_row, data, platform_key, status)

        if delivered:
            await bot.send_message(
                message.chat.id,
                f"{E.party} <b>Done!</b> {delivered} item{'s' if delivered != 1 else ''} delivered.\n"
                f"{E.heart} Thanks for using {esc(BOT_BRAND)}!",
                reply_markup=back_kb(), message_effect_id=EFFECT_LIKE if delivered else None)
            await db.log_download(uid, platform_key, url, "ok", duration=time.monotonic() - t0)
        else:
            await safe_edit(status, f"{E.no} Couldn't deliver the media. Please try again.")
            await db.log_download(uid, platform_key, url, "fail", "deliver_failed")

    except Cancelled:
        job["stop"] = True
        await anim_task
        await safe_edit(status, f"{E.no} <b>Cancelled</b>\n\nYou stopped this download.")
        await db.log_download(uid, platform_key, url, "cancelled")
    except DownloaderError as e:
        job["stop"] = True
        await anim_task
        await safe_edit(status, f"{E.no} <b>Download failed</b>\n\n{E.warn} {esc(str(e))}")
        await db.log_download(uid, platform_key, url, "fail", str(e))
    except Exception as e:
        job["stop"] = True
        with suppress(Exception):
            await anim_task
        log.exception("download crash")
        await safe_edit(status, f"{E.no} <b>Unexpected error</b>\n\n{E.warn} Please try again shortly.")
        await db.log_download(uid, platform_key, url, "fail", f"crash:{e}")
    finally:
        ACTIVE.pop(uid, None)


@user_router.message(F.text & ~F.text.startswith("/"))
async def msg_fallback(message: Message):
    await message.answer(
        f"{E.link} That doesn't look like a link.\n\n"
        f"{E.bulb} Paste a <b>YouTube</b>, <b>TikTok</b>, <b>Instagram</b> or <b>Facebook</b> URL and I'll fetch it for you.",
        reply_markup=back_kb())


# ════════════════════════════════════════════════════════════════════
#  ADMIN PANEL — FSM STATES
# ════════════════════════════════════════════════════════════════════
class Adm(StatesGroup):
    broadcast = State()
    broadcast_confirm = State()
    find_user = State()
    ban_user = State()
    unban_user = State()
    vip_add = State()
    vip_remove = State()
    add_admin = State()
    remove_admin = State()
    add_channel = State()
    remove_channel = State()
    set_welcome = State()
    set_limit = State()
    set_api = State()
    set_upload = State()
    dm_user = State()


def admin_home_kb() -> InlineKeyboardMarkup:
    return KB(
        [B("Statistics", cb="adm:stats", icon="stats", style="primary"),
         B("Broadcast", cb="adm:bc", icon="megaphone", style="primary")],
        [B("Users", cb="adm:users", icon="user"),
         B("VIP", cb="adm:vip", icon="crown")],
        [B("Channels", cb="adm:ch", icon="globe"),
         B("Admins", cb="adm:admins", icon="shield")],
        [B("Platforms", cb="adm:plat", icon="bolt"),
         B("Bot Settings", cb="adm:cfg", icon="gear")],
        [B("Server Status", cb="adm:srv", icon="pc"),
         B("Export Data", cb="adm:export", icon="book")],
        [B("Close", cb="adm:close", icon="no", style="danger")],
    )


@user_router.message(Command("admin"))
@user_router.callback_query(F.data == "adm:home")
async def adm_home(event, state: FSMContext):
    if not is_admin(event.from_user.id):
        if isinstance(event, Message):
            await event.answer(f"{E.ban} Admins only.")
        else:
            await event.answer("Admins only.", show_alert=True)
        return
    await state.clear()
    if isinstance(event, CallbackQuery):
        await event.answer()
    text = (
        f"{E.shield} <b>Admin Control Panel</b>\n\n"
        f"{E.robot} {esc(BOT_BRAND)}\n"
        f"{E.user} Admin: {esc(event.from_user.full_name)}\n"
        f"{E.clock} Uptime: {fmt_dur(time.time() - START_TIME)}\n\n"
        f"{E.gear} Choose a section below:"
    )
    await show(event, text, admin_home_kb())


@admin_router.callback_query(F.data == "adm:close")
async def adm_close(cb: CallbackQuery):
    await cb.answer()
    with suppress(Exception):
        await cb.message.delete()


# ── STATISTICS ──
@admin_router.callback_query(F.data == "adm:stats")
async def adm_stats(cb: CallbackQuery):
    await cb.answer()
    total = await db.scalar("SELECT COUNT(*) FROM users")
    banned = await db.scalar("SELECT COUNT(*) FROM users WHERE banned=1")
    vip = await db.scalar("SELECT COUNT(*) FROM users WHERE vip=1")
    today_u = await db.scalar("SELECT COUNT(*) FROM users WHERE joined_at>=?", (day_start(),))
    week_u = await db.scalar("SELECT COUNT(*) FROM users WHERE joined_at>=?", (day_start(7),))
    dl_total = await db.scalar("SELECT COUNT(*) FROM downloads WHERE status='ok'")
    dl_today = await db.scalar("SELECT COUNT(*) FROM downloads WHERE status='ok' AND created_at>=?", (day_start(),))
    dl_fail = await db.scalar("SELECT COUNT(*) FROM downloads WHERE status='fail' AND created_at>=?", (day_start(),))
    active_now = len(ACTIVE)
    by_platform = await db.q(
        "SELECT platform, COUNT(*) c FROM downloads WHERE status='ok' GROUP BY platform ORDER BY c DESC")
    plat_lines = "\n".join(
        f"  {getattr(E, PLATFORMS.get(r['platform'], PLATFORMS['other'])['emoji'])} "
        f"{PLATFORMS.get(r['platform'], PLATFORMS['other'])['name']}: <b>{r['c']}</b>"
        for r in by_platform) or "  —"
    text = (
        f"{E.stats} <b>Statistics</b>\n\n"
        f"{E.user} <b>Users</b>\n"
        f"  Total: <b>{total}</b>   Today: <b>+{today_u}</b>   7d: <b>+{week_u}</b>\n"
        f"  {E.crown} VIP: <b>{vip}</b>   {E.ban} Banned: <b>{banned}</b>\n\n"
        f"{E.download} <b>Downloads</b>\n"
        f"  All-time: <b>{dl_total}</b>   Today: <b>{dl_today}</b>   Failed today: <b>{dl_fail}</b>\n"
        f"  {E.bolt} Active right now: <b>{active_now}</b>\n\n"
        f"{E.globe} <b>By platform (all-time)</b>\n{plat_lines}"
    )
    await show(cb, text, KB([B("Refresh", cb="adm:stats", icon="refresh"),
                            B("Back", cb="adm:home", icon="back")]))


# ── SERVER STATUS ──
@admin_router.callback_query(F.data == "adm:srv")
async def adm_srv(cb: CallbackQuery):
    await cb.answer()
    online, ping = await api_server_status()
    text = (
        f"{E.pc} <b>Server Status</b>\n\n"
        f"{E.link} Backend: <code>{esc(api_base())}</code>\n"
        f"{E.green if online else E.red} Status: <b>{'ONLINE' if online else 'OFFLINE'}</b>\n"
        f"{E.bolt} Ping: <b>{ping:.0f} ms</b>\n\n"
        f"{E.robot} Python {pyplatform.python_version()} · aiogram\n"
        f"{E.clock} Bot uptime: {fmt_dur(time.time() - START_TIME)}\n"
        f"{E.hourglass} Active downloads: {len(ACTIVE)}/{MAX_CONCURRENT}"
    )
    await show(cb, text, KB([B("Refresh", cb="adm:srv", icon="refresh"),
                            B("Change API URL", cb="adm:setapi", icon="wrench"),
                            B("Back", cb="adm:home", icon="back")]))


@admin_router.callback_query(F.data == "adm:setapi")
async def adm_setapi(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(Adm.set_api)
    await show(cb, f"{E.wrench} Send the new API base URL (e.g. <code>https://your-app.onrender.com</code>).",
               back_kb("adm:srv"))


@admin_router.message(Adm.set_api)
async def adm_setapi_recv(message: Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith("http"):
        await message.answer(f"{E.no} Must start with http:// or https://")
        return
    await db.set("api_base", url.rstrip("/"))
    await state.clear()
    await message.answer(f"{E.ok} API base updated to <code>{esc(url)}</code>", reply_markup=back_kb("adm:srv"))


# ── USERS ──
def users_home_kb() -> InlineKeyboardMarkup:
    return KB(
        [B("Find user", cb="adm:finduser", icon="search"),
         B("Ban", cb="adm:ban", icon="ban", style="danger")],
        [B("Unban", cb="adm:unban", icon="ok", style="success"),
         B("Message user", cb="adm:dm", icon="chat")],
        [B("Recent users", cb="adm:recent", icon="clock")],
        [B("Back", cb="adm:home", icon="back")],
    )


@admin_router.callback_query(F.data == "adm:users")
async def adm_users(cb: CallbackQuery):
    await cb.answer()
    total = await db.scalar("SELECT COUNT(*) FROM users")
    await show(cb, f"{E.user} <b>User Management</b>\n\n{E.stats} Total users: <b>{total}</b>", users_home_kb())


@admin_router.callback_query(F.data == "adm:recent")
async def adm_recent(cb: CallbackQuery):
    await cb.answer()
    rows = await db.q("SELECT * FROM users ORDER BY joined_at DESC LIMIT 12")
    lines = [f"{E.user} {user_label(r)} · <code>{r['id']}</code> · {fmt_ts(r['joined_at'])}" for r in rows]
    await show(cb, f"{E.clock} <b>Recently Joined</b>\n\n" + "\n".join(lines), back_kb("adm:users"))


async def ask_uid(cb: CallbackQuery, state: FSMContext, target_state: State, prompt: str, back_to="adm:users"):
    await cb.answer()
    await state.set_state(target_state)
    await show(cb, prompt, back_kb(back_to))


@admin_router.callback_query(F.data == "adm:finduser")
async def adm_finduser(cb: CallbackQuery, state: FSMContext):
    await ask_uid(cb, state, Adm.find_user, f"{E.search} Send a user ID or @username to look up.")


def user_card_kb(uid: int, banned: int, vip: int) -> InlineKeyboardMarkup:
    return KB(
        [B("Unban" if banned else "Ban", cb=f"adm:toggleban:{uid}",
           icon="ok" if banned else "ban", style="success" if banned else "danger"),
         B("Remove VIP" if vip else "Make VIP", cb=f"adm:togglevip:{uid}",
           icon="no" if vip else "crown", style=None if vip else "success")],
        [B("Message", cb=f"adm:dmid:{uid}", icon="chat")],
        [B("Back", cb="adm:users", icon="back")],
    )


async def render_user_card(uid: int) -> tuple[str, InlineKeyboardMarkup] | tuple[None, None]:
    u = await db.get_user(uid)
    if not u:
        return None, None
    today = await db.downloads_today(uid)
    tier = f"{E.crown} VIP" if u["vip"] else (f"{E.shield} Admin" if is_admin(uid) else f"{E.user} Free")
    text = (
        f"{E.user} <b>User Card</b>\n\n"
        f"{E.pin} ID: <code>{u['id']}</code>\n"
        f"{E.chat} Username: {('@' + esc(u['username'])) if u['username'] else '—'}\n"
        f"{E.star} Plan: {tier}\n"
        f"{E.ban if u['banned'] else E.ok} Status: {'Banned' if u['banned'] else 'Active'}\n"
        f"{E.download} Downloads: <b>{u['downloads']}</b> (today: {today})\n"
        f"{E.calendar} Joined: {fmt_ts(u['joined_at'])}\n"
        f"{E.clock} Last seen: {fmt_ts(u['last_seen'])}"
    )
    return text, user_card_kb(uid, u["banned"], u["vip"])


@admin_router.message(Adm.find_user)
async def adm_finduser_recv(message: Message, state: FSMContext):
    q = message.text.strip().lstrip("@")
    row = None
    if q.isdigit():
        row = await db.q1("SELECT id FROM users WHERE id=?", (int(q),))
    if not row:
        row = await db.q1("SELECT id FROM users WHERE username=?", (q,))
    await state.clear()
    if not row:
        await message.answer(f"{E.no} No user found.", reply_markup=back_kb("adm:users"))
        return
    text, kb = await render_user_card(row["id"])
    await message.answer(text, reply_markup=kb)


@admin_router.callback_query(F.data.startswith("adm:uc:"))
async def adm_user_card(cb: CallbackQuery):
    await cb.answer()
    uid = int(cb.data.split(":")[2])
    text, kb = await render_user_card(uid)
    if text is None:
        await show(cb, f"{E.no} User not found.", back_kb("adm:users"))
        return
    await show(cb, text, kb)


@admin_router.callback_query(F.data.startswith("adm:toggleban:"))
async def adm_toggleban(cb: CallbackQuery, bot: Bot):
    uid = int(cb.data.split(":")[2])
    u = await db.get_user(uid)
    new = 0 if u["banned"] else 1
    await db.x("UPDATE users SET banned=? WHERE id=?", (new, uid))
    await cb.answer("Updated ✓")
    with suppress(Exception):
        await bot.send_message(uid, f"{E.ban if new else E.ok} Your access has been "
                                    f"{'restricted' if new else 'restored'} by an administrator.")
    text, kb = await render_user_card(uid)
    await show(cb, text, kb)


@admin_router.callback_query(F.data.startswith("adm:togglevip:"))
async def adm_togglevip(cb: CallbackQuery, bot: Bot):
    uid = int(cb.data.split(":")[2])
    u = await db.get_user(uid)
    new = 0 if u["vip"] else 1
    await db.x("UPDATE users SET vip=? WHERE id=?", (new, uid))
    await cb.answer("Updated ✓")
    with suppress(Exception):
        await bot.send_message(uid, f"{E.crown} You've been {'granted' if new else 'removed from'} "
                                    f"VIP status{' — unlimited downloads unlocked!' if new else '.'}")
    text, kb = await render_user_card(uid)
    await show(cb, text, kb)


@admin_router.callback_query(F.data == "adm:ban")
async def adm_ban(cb: CallbackQuery, state: FSMContext):
    await ask_uid(cb, state, Adm.ban_user, f"{E.ban} Send the user ID to ban.")


@admin_router.message(Adm.ban_user)
async def adm_ban_recv(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    if not message.text.strip().isdigit():
        await message.answer(f"{E.no} Send a numeric user ID.")
        return
    uid = int(message.text.strip())
    if uid == OWNER_ID:
        await message.answer(f"{E.no} Cannot ban the owner.")
        return
    await db.x("UPDATE users SET banned=1 WHERE id=?", (uid,))
    await message.answer(f"{E.ban} User <code>{uid}</code> banned.", reply_markup=back_kb("adm:users"))
    with suppress(Exception):
        await bot.send_message(uid, f"{E.ban} Your access has been restricted by an administrator.")


@admin_router.callback_query(F.data == "adm:unban")
async def adm_unban(cb: CallbackQuery, state: FSMContext):
    await ask_uid(cb, state, Adm.unban_user, f"{E.ok} Send the user ID to unban.")


@admin_router.message(Adm.unban_user)
async def adm_unban_recv(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    if not message.text.strip().isdigit():
        await message.answer(f"{E.no} Send a numeric user ID.")
        return
    uid = int(message.text.strip())
    await db.x("UPDATE users SET banned=0 WHERE id=?", (uid,))
    await message.answer(f"{E.ok} User <code>{uid}</code> unbanned.", reply_markup=back_kb("adm:users"))
    with suppress(Exception):
        await bot.send_message(uid, f"{E.ok} Your access has been restored.")


@admin_router.callback_query(F.data == "adm:dm")
async def adm_dm(cb: CallbackQuery, state: FSMContext):
    await ask_uid(cb, state, Adm.find_user, f"{E.chat} Send the user ID to message (step 1/2).")
    await state.update_data(mode="dm")


@admin_router.callback_query(F.data.startswith("adm:dmid:"))
async def adm_dmid(cb: CallbackQuery, state: FSMContext):
    uid = int(cb.data.split(":")[2])
    await cb.answer()
    await state.set_state(Adm.dm_user)
    await state.update_data(target=uid)
    await show(cb, f"{E.chat} Send the message to deliver to <code>{uid}</code>.", back_kb("adm:users"))


@admin_router.message(Adm.find_user, F.text)
async def adm_find_router(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("mode") != "dm":
        return await adm_finduser_recv(message, state)
    q = message.text.strip().lstrip("@")
    row = await db.q1("SELECT id FROM users WHERE id=?", (int(q),)) if q.isdigit() else \
        await db.q1("SELECT id FROM users WHERE username=?", (q,))
    if not row:
        await message.answer(f"{E.no} No user found.")
        await state.clear()
        return
    await state.set_state(Adm.dm_user)
    await state.update_data(target=row["id"])
    await message.answer(f"{E.chat} Send the message to deliver to <code>{row['id']}</code>.")


@admin_router.message(Adm.dm_user)
async def adm_dm_recv(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target = data.get("target")
    await state.clear()
    try:
        await bot.send_message(target, f"{E.mail} <b>Message from admin</b>\n\n{esc(message.text)}")
        await message.answer(f"{E.ok} Delivered.", reply_markup=back_kb("adm:users"))
    except TelegramAPIError as e:
        await message.answer(f"{E.no} Couldn't deliver: {esc(e)}", reply_markup=back_kb("adm:users"))


# ── VIP ──
@admin_router.callback_query(F.data == "adm:vip")
async def adm_vip(cb: CallbackQuery):
    await cb.answer()
    rows = await db.q("SELECT id, username, first_name FROM users WHERE vip=1 ORDER BY id DESC LIMIT 20")
    count = await db.scalar("SELECT COUNT(*) FROM users WHERE vip=1")
    lines = [f"{E.crown} {user_label(r)} · <code>{r['id']}</code>" for r in rows] or [f"{E.eyes} No VIP members yet."]
    text = f"{E.crown} <b>VIP Members</b> ({count})\n\n" + "\n".join(lines)
    await show(cb, text, KB(
        [B("Add VIP", cb="adm:vipadd", icon="plus", style="success"),
         B("Remove VIP", cb="adm:vipdel", icon="no", style="danger")],
        [B("Back", cb="adm:home", icon="back")]))


@admin_router.callback_query(F.data == "adm:vipadd")
async def adm_vipadd(cb: CallbackQuery, state: FSMContext):
    await ask_uid(cb, state, Adm.vip_add, f"{E.crown} Send the user ID to grant VIP.", "adm:vip")


@admin_router.message(Adm.vip_add)
async def adm_vipadd_recv(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    if not message.text.strip().isdigit():
        await message.answer(f"{E.no} Send a numeric user ID.")
        return
    uid = int(message.text.strip())
    if not await db.get_user(uid):
        await message.answer(f"{E.no} That user hasn't started the bot yet.")
        return
    await db.x("UPDATE users SET vip=1 WHERE id=?", (uid,))
    await message.answer(f"{E.ok} <code>{uid}</code> is now VIP.", reply_markup=back_kb("adm:vip"))
    with suppress(Exception):
        await bot.send_message(uid, f"{E.crown} Congratulations — you've been granted VIP status! Unlimited downloads unlocked.")


@admin_router.callback_query(F.data == "adm:vipdel")
async def adm_vipdel(cb: CallbackQuery, state: FSMContext):
    await ask_uid(cb, state, Adm.vip_remove, f"{E.no} Send the user ID to remove VIP from.", "adm:vip")


@admin_router.message(Adm.vip_remove)
async def adm_vipdel_recv(message: Message, state: FSMContext):
    await state.clear()
    if not message.text.strip().isdigit():
        await message.answer(f"{E.no} Send a numeric user ID.")
        return
    uid = int(message.text.strip())
    await db.x("UPDATE users SET vip=0 WHERE id=?", (uid,))
    await message.answer(f"{E.ok} VIP removed from <code>{uid}</code>.", reply_markup=back_kb("adm:vip"))


# ── CHANNELS (force-join) ──
@admin_router.callback_query(F.data == "adm:ch")
async def adm_ch(cb: CallbackQuery):
    await cb.answer()
    chans = await db.channels()
    lines = [f"{E.megaphone} <b>{esc(c['title'] or c['chat_id'])}</b>\n   <code>{c['chat_id']}</code>"
            f"{(' · ' + c['link']) if c.get('link') else ''}" for c in chans] or [f"{E.eyes} No channels configured."]
    fj = db.flag("force_join")
    text = (f"{E.globe} <b>Force-Join Channels</b>\n\n" + "\n".join(lines) +
           f"\n\n{E.bolt} Force-join is currently: {E.green + ' ON' if fj else E.red + ' OFF'}")
    await show(cb, text, KB(
        [B("Add channel", cb="adm:chadd", icon="plus", style="success"),
         B("Remove channel", cb="adm:chdel", icon="trash", style="danger")],
        [B(f"Turn {'OFF' if fj else 'ON'}", cb="adm:chtoggle", icon="refresh")],
        [B("Back", cb="adm:home", icon="back")]))


@admin_router.callback_query(F.data == "adm:chtoggle")
async def adm_chtoggle(cb: CallbackQuery):
    new = await db.toggle("force_join")
    await cb.answer(f"Force-join is now {'ON' if new else 'OFF'}")
    await adm_ch(cb)


@admin_router.callback_query(F.data == "adm:chadd")
async def adm_chadd(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(Adm.add_channel)
    await show(cb,
               f"{E.plus} Send channel info as:\n<code>chat_id | title | invite_link</code>\n\n"
               f"{E.warn} The bot must be an <b>admin</b> in that channel.\n"
               f"Example:\n<code>-1001234567890 | My Channel | https://t.me/+abc123</code>",
               back_kb("adm:ch"))


@admin_router.message(Adm.add_channel)
async def adm_chadd_recv(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    parts = [p.strip() for p in message.text.split("|")]
    if not parts or not parts[0].lstrip("-").isdigit():
        await message.answer(f"{E.no} Format: <code>chat_id | title | invite_link</code>", reply_markup=back_kb("adm:ch"))
        return
    chat_id = int(parts[0])
    title = parts[1] if len(parts) > 1 else str(chat_id)
    link = parts[2] if len(parts) > 2 else ""
    try:
        chat = await bot.get_chat(chat_id)
        title = chat.title or title
        me = await bot.get_chat_member(chat_id, (await bot.me()).id)
        if me.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            await message.answer(f"{E.warn} Added, but I'm not an admin there yet — verification will fail until I am.")
    except TelegramAPIError as e:
        await message.answer(f"{E.warn} Couldn't verify the channel ({esc(e)}), saving anyway.")
    await db.x("INSERT INTO channels(chat_id,title,link) VALUES(?,?,?) "
              "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, link=excluded.link",
              (chat_id, title, link))
    await refresh_join_links()
    await message.answer(f"{E.ok} Channel saved.", reply_markup=back_kb("adm:ch"))


@admin_router.callback_query(F.data == "adm:chdel")
async def adm_chdel(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    chans = await db.channels()
    if not chans:
        await show(cb, f"{E.eyes} No channels to remove.", back_kb("adm:ch"))
        return
    rows = [[B(f"{c['title'] or c['chat_id']}", cb=f"adm:chdo:{c['chat_id']}", icon="trash")] for c in chans]
    rows.append([B("Back", cb="adm:ch", icon="back")])
    await show(cb, f"{E.trash} Tap a channel to remove it:", KB(*rows))


@admin_router.callback_query(F.data.startswith("adm:chdo:"))
async def adm_chdo(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    await db.x("DELETE FROM channels WHERE chat_id=?", (chat_id,))
    await refresh_join_links()
    await cb.answer("Removed ✓")
    await adm_ch(cb)


# ── ADMINS ──
@admin_router.callback_query(F.data == "adm:admins")
async def adm_admins(cb: CallbackQuery):
    await cb.answer()
    if not is_owner(cb.from_user.id):
        await show(cb, f"{E.ban} Only the owner can manage admins.", back_kb("adm:home"))
        return
    ids = await db.admin_ids()
    lines = [f"{E.shield} <code>{i}</code>" for i in ids] or [f"{E.eyes} No extra admins yet."]
    text = f"{E.shield} <b>Bot Admins</b>\n\n{E.crown} Owner: <code>{OWNER_ID}</code>\n\n" + "\n".join(lines)
    await show(cb, text, KB(
        [B("Add admin", cb="adm:addadmin", icon="plus", style="success"),
         B("Remove admin", cb="adm:deladmin", icon="trash", style="danger")],
        [B("Back", cb="adm:home", icon="back")]))


@admin_router.callback_query(F.data == "adm:addadmin")
async def adm_addadmin(cb: CallbackQuery, state: FSMContext):
    if not is_owner(cb.from_user.id):
        await cb.answer("Owner only.", show_alert=True)
        return
    await ask_uid(cb, state, Adm.add_admin, f"{E.plus} Send the user ID to make an admin.", "adm:admins")


@admin_router.message(Adm.add_admin)
async def adm_addadmin_recv(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    if not message.text.strip().isdigit():
        await message.answer(f"{E.no} Send a numeric user ID.")
        return
    uid = int(message.text.strip())
    await db.x("INSERT OR IGNORE INTO admins(id, added_at) VALUES(?,?)", (uid, now()))
    ADMINS.add(uid)
    await message.answer(f"{E.ok} <code>{uid}</code> is now an admin.", reply_markup=back_kb("adm:admins"))
    with suppress(Exception):
        await bot.send_message(uid, f"{E.shield} You've been made an admin of {esc(BOT_BRAND)}. Use /admin to open the panel.")


@admin_router.callback_query(F.data == "adm:deladmin")
async def adm_deladmin(cb: CallbackQuery, state: FSMContext):
    if not is_owner(cb.from_user.id):
        await cb.answer("Owner only.", show_alert=True)
        return
    await ask_uid(cb, state, Adm.remove_admin, f"{E.trash} Send the user ID to remove from admins.", "adm:admins")


@admin_router.message(Adm.remove_admin)
async def adm_deladmin_recv(message: Message, state: FSMContext):
    await state.clear()
    if not message.text.strip().isdigit():
        await message.answer(f"{E.no} Send a numeric user ID.")
        return
    uid = int(message.text.strip())
    await db.x("DELETE FROM admins WHERE id=?", (uid,))
    ADMINS.discard(uid)
    await message.answer(f"{E.ok} <code>{uid}</code> removed from admins.", reply_markup=back_kb("adm:admins"))


# ── PLATFORMS TOGGLE ──
@admin_router.callback_query(F.data == "adm:plat")
async def adm_plat(cb: CallbackQuery):
    await cb.answer()
    rows = []
    for key, p in PLATFORMS.items():
        if key == "other":
            continue
        on = db.flag(f"p_{key}")
        rows.append([B(f"{p['name']}: {'ON' if on else 'OFF'}", cb=f"adm:ptoggle:{key}",
                      icon=p["emoji"], style="success" if on else "danger")])
    rows.append([B("Back", cb="adm:home", icon="back")])
    await show(cb, f"{E.bolt} <b>Platform Toggles</b>\n\nTap to enable/disable a platform instantly.", KB(*rows))


@admin_router.callback_query(F.data.startswith("adm:ptoggle:"))
async def adm_ptoggle(cb: CallbackQuery):
    key = cb.data.split(":")[2]
    new = await db.toggle(f"p_{key}")
    await cb.answer(f"{PLATFORMS[key]['name']} is now {'ON' if new else 'OFF'}")
    await adm_plat(cb)


# ── BOT SETTINGS ──
def cfg_kb() -> InlineKeyboardMarkup:
    m = db.flag("maintenance")
    au = db.flag("auto_send")
    an = db.flag("animations")
    nn = db.flag("notify_new")
    return KB(
        [B(f"Maintenance: {'ON' if m else 'OFF'}", cb="adm:cfgtoggle:maintenance",
           icon="wrench", style="danger" if m else "success")],
        [B(f"Default auto-send: {'ON' if au else 'OFF'}", cb="adm:cfgtoggle:auto_send",
           icon="download", style="success" if au else None)],
        [B(f"Animations: {'ON' if an else 'OFF'}", cb="adm:cfgtoggle:animations",
           icon="sparkles", style="success" if an else None)],
        [B(f"New-user alerts: {'ON' if nn else 'OFF'}", cb="adm:cfgtoggle:notify_new",
           icon="bell", style="success" if nn else None)],
        [B("Daily limit", cb="adm:setlimit", icon="hourglass"),
         B("Upload size cap", cb="adm:setupload", icon="pc")],
        [B("Welcome text", cb="adm:setwelcome", icon="pencil")],
        [B("Back", cb="adm:home", icon="back")],
    )


@admin_router.callback_query(F.data == "adm:cfg")
async def adm_cfg(cb: CallbackQuery):
    await cb.answer()
    limit = db.num("daily_limit")
    text = (
        f"{E.gear} <b>Bot Settings</b>\n\n"
        f"{E.hourglass} Daily limit: <b>{'Unlimited' if limit <= 0 else limit}</b>\n"
        f"{E.pc} Upload cap: <b>{db.num('max_upload_mb')} MB</b>\n"
        f"{E.link} API base: <code>{esc(api_base())}</code>"
    )
    await show(cb, text, cfg_kb())


@admin_router.callback_query(F.data.startswith("adm:cfgtoggle:"))
async def adm_cfgtoggle(cb: CallbackQuery):
    key = cb.data.split(":")[2]
    new = await db.toggle(key)
    await cb.answer(f"{key} is now {'ON' if new else 'OFF'}")
    await adm_cfg(cb)


@admin_router.callback_query(F.data == "adm:setlimit")
async def adm_setlimit(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(Adm.set_limit)
    await show(cb, f"{E.hourglass} Send the daily download limit per user (0 = unlimited).", back_kb("adm:cfg"))


@admin_router.message(Adm.set_limit)
async def adm_setlimit_recv(message: Message, state: FSMContext):
    await state.clear()
    if not message.text.strip().lstrip("-").isdigit():
        await message.answer(f"{E.no} Send a whole number.")
        return
    await db.set("daily_limit", max(0, int(message.text.strip())))
    await message.answer(f"{E.ok} Daily limit updated.", reply_markup=back_kb("adm:cfg"))


@admin_router.callback_query(F.data == "adm:setupload")
async def adm_setupload(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(Adm.set_upload)
    await show(cb, f"{E.pc} Send the max auto-upload size in MB (Telegram bot limit ≈ 50MB).", back_kb("adm:cfg"))


@admin_router.message(Adm.set_upload)
async def adm_setupload_recv(message: Message, state: FSMContext):
    await state.clear()
    if not message.text.strip().isdigit():
        await message.answer(f"{E.no} Send a whole number.")
        return
    mb = max(1, min(2000, int(message.text.strip())))
    await db.set("max_upload_mb", mb)
    await message.answer(f"{E.ok} Upload cap set to {mb} MB.", reply_markup=back_kb("adm:cfg"))


@admin_router.callback_query(F.data == "adm:setwelcome")
async def adm_setwelcome(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(Adm.set_welcome)
    await show(cb,
               f"{E.pencil} Send the new welcome message (HTML allowed). Use <code>{{name}}</code> for the user's name.\n"
               f"Send <code>reset</code> to restore the default.",
               back_kb("adm:cfg"))


@admin_router.message(Adm.set_welcome)
async def adm_setwelcome_recv(message: Message, state: FSMContext):
    await state.clear()
    txt = message.text.strip()
    await db.set("welcome_text", "" if txt.lower() == "reset" else message.html_text)
    await message.answer(f"{E.ok} Welcome message updated.", reply_markup=back_kb("adm:cfg"))


# ── BROADCAST ──
@admin_router.callback_query(F.data == "adm:bc")
async def adm_bc(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(Adm.broadcast)
    await show(cb,
               f"{E.megaphone} <b>Broadcast</b>\n\nSend the message to deliver to all users "
               f"(text, photo, or video — with caption).",
               back_kb("adm:home"))


@admin_router.message(Adm.broadcast)
async def adm_bc_recv(message: Message, state: FSMContext):
    await state.update_data(bc_chat=message.chat.id, bc_msg=message.message_id)
    await state.set_state(Adm.broadcast_confirm)
    total = await db.scalar("SELECT COUNT(*) FROM users WHERE banned=0")
    await message.answer(
        f"{E.warn} This will be sent to <b>{total}</b> users. Confirm?",
        reply_markup=KB([B("Send now", cb="adm:bcsend", icon="rocket", style="success"),
                        B("Cancel", cb="adm:home", icon="no", style="danger")]))


@admin_router.callback_query(F.data == "adm:bcsend", Adm.broadcast_confirm)
async def adm_bcsend(cb: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    await cb.answer("Broadcasting…")
    src_chat, src_msg = data["bc_chat"], data["bc_msg"]
    ids = [r["id"] for r in await db.q("SELECT id FROM users WHERE banned=0")]
    status = await cb.message.answer(f"{E.rocket} <b>Broadcasting…</b>\n\n{bar(0)} 0/{len(ids)}")
    ok = fail = blocked = 0
    for i, uid in enumerate(ids, 1):
        try:
            await bot.copy_message(uid, src_chat, src_msg)
            ok += 1
        except TelegramForbiddenError:
            blocked += 1
            await db.x("UPDATE users SET blocked=1 WHERE id=?", (uid,))
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            with suppress(Exception):
                await bot.copy_message(uid, src_chat, src_msg)
                ok += 1
        except TelegramAPIError:
            fail += 1
        if i % 20 == 0 or i == len(ids):
            pct = round(i / max(len(ids), 1) * 100)
            await safe_edit(status, f"{E.rocket} <b>Broadcasting…</b>\n\n{bar(pct)} {i}/{len(ids)}")
        await asyncio.sleep(0.04)
    await safe_edit(status,
                    f"{E.party} <b>Broadcast complete</b>\n\n"
                    f"{E.ok} Delivered: <b>{ok}</b>\n{E.ban} Blocked bot: <b>{blocked}</b>\n"
                    f"{E.no} Failed: <b>{fail}</b>")


# ── EXPORT ──
@admin_router.callback_query(F.data == "adm:export")
async def adm_export(cb: CallbackQuery, bot: Bot):
    await cb.answer("Preparing export…")
    rows = await db.q("SELECT id, username, first_name, joined_at, downloads, vip, banned FROM users ORDER BY id")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "username", "first_name", "joined_at", "downloads", "vip", "banned"])
    for r in rows:
        w.writerow([r["id"], r["username"] or "", r["first_name"] or "",
                   fmt_ts(r["joined_at"]), r["downloads"], r["vip"], r["banned"]])
    data = buf.getvalue().encode("utf-8")
    file = BufferedInputFile(data, filename=f"users_{datetime.now(TZ):%Y%m%d_%H%M}.csv")
    await bot.send_document(cb.from_user.id, file,
                            caption=f"{E.book} <b>User export</b> — {len(rows)} records")


# ── FALLBACK — stray text while inside an admin FSM state that drifted off ──
@admin_router.message(StateFilter(Adm))
async def adm_fsm_catch(message: Message, state: FSMContext):
    await message.answer(f"{E.warn} Unexpected input — please follow the prompt, or press Back to cancel.")


# ════════════════════════════════════════════════════════════════════
#  HEALTH / KEEP-ALIVE WEB SERVER   (required by Render)
# ════════════════════════════════════════════════════════════════════
async def health_handler(request: web.Request) -> web.Response:
    online, ping = await api_server_status()
    return web.json_response({
        "status": "ok",
        "bot": BOT_BRAND,
        "uptime_seconds": round(time.time() - START_TIME),
        "uptime": fmt_dur(time.time() - START_TIME),
        "backend_online": online,
        "backend_ping_ms": round(ping),
        "active_downloads": len(ACTIVE),
        "users": await db.scalar("SELECT COUNT(*) FROM users"),
        "downloads_today": await db.scalar(
            "SELECT COUNT(*) FROM downloads WHERE status='ok' AND created_at>=?", (day_start(),)),
        "time": datetime.now(TZ).isoformat(),
    })


async def root_handler(request: web.Request) -> web.Response:
    return web.Response(
        text=f"{BOT_BRAND} is running.\nHealth check: /health",
        content_type="text/plain")


async def ping_handler(request: web.Request) -> web.Response:
    return web.Response(text="pong")


async def start_web_app(bot: Bot) -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", root_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/healthz", health_handler)
    app.router.add_get("/ping", ping_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info("Health server listening on :%s", PORT)
    return runner


async def self_ping_loop() -> None:
    """Keeps a Render free-tier web service awake."""
    if not SELF_URL:
        return
    await asyncio.sleep(60)
    while True:
        with suppress(Exception):
            async with HTTP.get(f"{SELF_URL}/ping", timeout=aiohttp.ClientTimeout(total=20)) as r:
                log.debug("self-ping %s", r.status)
        await asyncio.sleep(600)


async def backend_watch_loop(bot: Bot) -> None:
    """Periodic backend health poke + owner alert if it goes down for a while."""
    down_since: Optional[float] = None
    while True:
        await asyncio.sleep(120)
        online, _ = await api_server_status()
        if not online:
            if down_since is None:
                down_since = time.time()
            elif time.time() - down_since > 900:
                await alert_once(bot, "backend_down",
                                 f"{E.warn} <b>Backend has been offline for 15+ minutes</b>\n"
                                 f"{E.link} <code>{esc(api_base())}</code>", every=1800)
        else:
            down_since = None


# ════════════════════════════════════════════════════════════════════
#  BOT COMMANDS MENU
# ════════════════════════════════════════════════════════════════════
async def setup_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [BotCommand(command="start", description="Restart the bot"),
         BotCommand(command="profile", description="View your profile"),
         BotCommand(command="help", description="How to use this bot")],
        scope=BotCommandScopeDefault())
    for uid in {OWNER_ID, *ADMINS}:
        with suppress(Exception):
            await bot.set_my_commands(
                [BotCommand(command="start", description="Restart the bot"),
                 BotCommand(command="profile", description="View your profile"),
                 BotCommand(command="help", description="How to use this bot"),
                 BotCommand(command="admin", description="Open admin panel")],
                scope=BotCommandScopeChat(chat_id=uid))


# ════════════════════════════════════════════════════════════════════
#  LIFECYCLE
# ════════════════════════════════════════════════════════════════════
async def on_startup(bot: Bot) -> None:
    me = await bot.me()
    log.info("Logged in as @%s (%s)", me.username, me.id)
    with suppress(Exception):
        await bot.send_message(
            OWNER_ID,
            f"{E.rocket} <b>{esc(BOT_BRAND)} is online</b>\n\n"
            f"{E.robot} @{esc(me.username)}\n{E.clock} {datetime.now(TZ):%d %b %Y, %I:%M %p}\n"
            f"{E.shield} Admins loaded: {len(ADMINS) + 1}")


async def on_shutdown(bot: Bot) -> None:
    with suppress(Exception):
        await bot.send_message(OWNER_ID, f"{E.warn} <b>{esc(BOT_BRAND)} is shutting down.</b>")
    await db.close()
    if HTTP:
        await HTTP.close()


async def main() -> None:
    global HTTP, ADMINS
    if not BOT_TOKEN:
        log.error("BOT_TOKEN is not set. Set it in your environment (Render → Environment).")
        sys.exit(1)

    await db.connect()
    ADMINS = await db.admin_ids()
    await refresh_join_links()

    HTTP = aiohttp.ClientSession()

    session = AiohttpSession()
    session.middleware(EmojiFallbackMiddleware())
    bot = Bot(token=BOT_TOKEN, session=session,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True))

    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(GateMiddleware())
    dp.include_router(admin_router)
    dp.include_router(user_router)

    runner = await start_web_app(bot)
    await setup_commands(bot)

    watchdog = asyncio.create_task(backend_watch_loop(bot))
    pinger = asyncio.create_task(self_ping_loop())

    try:
        await on_startup(bot)
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        watchdog.cancel()
        pinger.cancel()
        await runner.cleanup()
        await on_shutdown(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass

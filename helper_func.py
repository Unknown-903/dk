import base64
import re
import asyncio
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant, FloodWait

from config import ADMINS, OWNER_ID
from database.database import present_admin, is_banned, get_fsub_channels, has_join_request


# ── Subscription check ─────────────────────────────────────────────────────────
async def is_subscribed(filter, client, update):
    user_id = update.from_user.id

    if await is_banned(user_id):
        return False

    if user_id == OWNER_ID or user_id in ADMINS:
        return True
    if await present_admin(user_id):
        return True

    channels = await get_fsub_channels()
    if not channels:
        return True

    member_ok = (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER)

    for ch in channels:
        ch_id   = ch['id']
        ch_type = ch.get('type', 'public')

        # Request channels — DB mein check karo ki user ne request bheji hai ya nahi
        if ch_type == 'request':
            if not await has_join_request(user_id, ch_id):
                return False
            continue

        # Public / Private channels — membership check karo
        try:
            member = await client.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status not in member_ok:
                return False
        except UserNotParticipant:
            return False
        except Exception:
            continue

    return True

subscribed = filters.create(is_subscribed)


# ── Encode / decode base64 ─────────────────────────────────────────────────────
async def encode(string: str) -> str:
    b = base64.urlsafe_b64encode(string.encode("ascii"))
    return b.decode("ascii").strip("=")

async def decode(b64: str) -> str:
    b64 = b64.strip("=")
    b64 += "=" * (-len(b64) % 4)
    return base64.urlsafe_b64decode(b64.encode("ascii")).decode("ascii")


# ── Fetch messages from DB channel ────────────────────────────────────────────
async def get_messages(client, message_ids):
    messages = []
    done = 0
    while done < len(message_ids):
        batch = message_ids[done:done + 200]
        try:
            msgs = await client.get_messages(chat_id=client.db_channel.id, message_ids=batch)
        except FloodWait as e:
            await asyncio.sleep(e.x)
            msgs = await client.get_messages(chat_id=client.db_channel.id, message_ids=batch)
        done += len(batch)
        messages.extend(msgs)
    return messages


# ── Extract message ID from a forwarded/linked message ────────────────────────
async def get_message_id(client, message) -> int:
    if message.forward_from_chat:
        if message.forward_from_chat.id == client.db_channel.id:
            return message.forward_from_message_id
        return 0
    if message.forward_sender_name:
        return 0
    if message.text:
        pattern = r"https://t\.me/(?:c/)?(.+?)/(\d+)"
        m = re.match(pattern, message.text)
        if not m:
            return 0
        ch, msg_id = m.group(1), int(m.group(2))
        if ch.isdigit():
            return msg_id if f"-100{ch}" == str(client.db_channel.id) else 0
        return msg_id if ch == client.db_channel.username else 0
    return 0


# ── Human-readable time ───────────────────────────────────────────────────────
def readable_time(seconds: int) -> str:
    periods = [
        ("year",  60 * 60 * 24 * 365),
        ("month", 60 * 60 * 24 * 30),
        ("day",   60 * 60 * 24),
        ("hour",  60 * 60),
        ("min",   60),
        ("sec",   1),
    ]
    parts = []
    for name, div in periods:
        if seconds >= div:
            n, seconds = divmod(seconds, div)
            parts.append(f"{n} {name}{'s' if n > 1 else ''}")
    return ", ".join(parts) if parts else "0 secs"

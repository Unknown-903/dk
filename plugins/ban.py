from pyrogram import filters
from pyrogram.types import Message

from bot import Bot
from config import OWNER_ID, ADMINS
from database.database import is_banned, ban_user, unban_user


def _is_owner_or_admin(uid: int) -> bool:
    return uid == OWNER_ID or uid in ADMINS


# ─────────────────────────────────────────────────────────────────────────────
# /ban
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("ban") & filters.private)
async def ban_cmd(client: Bot, message: Message):
    if not _is_owner_or_admin(message.from_user.id):
        await message.reply_text("❌ Only admins can ban users.")
        return

    if len(message.command) < 2:
        await message.reply_text("<b>Usage:</b> <code>/ban user_id</code>")
        return

    try:
        target_id = int(message.command[1])
    except ValueError:
        await message.reply_text("❌ Invalid user ID.")
        return

    if target_id == OWNER_ID:
        await message.reply_text("🛡 Cannot ban the owner.")
        return

    if await is_banned(target_id):
        await message.reply_text(f"⚠️ <code>{target_id}</code> is already banned.")
        return

    await ban_user(target_id)
    try:
        u = await client.get_users(target_id)
        name = u.first_name
    except Exception:
        name = str(target_id)

    await message.reply_text(f"🚫 <b>{name}</b> (<code>{target_id}</code>) has been banned.")


# ─────────────────────────────────────────────────────────────────────────────
# /unban
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("unban") & filters.private)
async def unban_cmd(client: Bot, message: Message):
    if not _is_owner_or_admin(message.from_user.id):
        await message.reply_text("❌ Only admins can unban users.")
        return

    if len(message.command) < 2:
        await message.reply_text("<b>Usage:</b> <code>/unban user_id</code>")
        return

    try:
        target_id = int(message.command[1])
    except ValueError:
        await message.reply_text("❌ Invalid user ID.")
        return

    if not await is_banned(target_id):
        await message.reply_text(f"⚠️ <code>{target_id}</code> is not banned.")
        return

    await unban_user(target_id)
    try:
        u = await client.get_users(target_id)
        name = u.first_name
    except Exception:
        name = str(target_id)

    await message.reply_text(f"✅ <b>{name}</b> (<code>{target_id}</code>) has been unbanned.")

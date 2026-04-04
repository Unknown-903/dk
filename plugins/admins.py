from pyrogram import filters
from pyrogram.types import Message

from bot import Bot
from config import OWNER_ID, ADMINS
from database.database import present_admin, add_admin, del_admin, full_adminbase


def _is_owner_or_admin(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in ADMINS


# ─────────────────────────────────────────────────────────────────────────────
# /add  – add admin  (owner or existing admin)
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("add") & filters.private)
async def add_admin_cmd(client: Bot, message: Message):
    uid = message.from_user.id

    if not _is_owner_or_admin(uid):
        await message.reply_text("❌ Only admins can add other admins.")
        return

    if len(message.command) < 2:
        await message.reply_text("<b>Usage:</b> <code>/add user_id</code>")
        return

    try:
        target_id = int(message.command[1])
    except ValueError:
        await message.reply_text("❌ Invalid user ID.")
        return

    if target_id == OWNER_ID:
        await message.reply_text("ℹ️ Owner is already the top admin.")
        return

    try:
        user = await client.get_users(target_id)
        name = user.first_name
    except Exception:
        await message.reply_text("❌ User not found.")
        return

    already = await add_admin(target_id)
    if already:
        await message.reply_text(f"⚠️ <b>{name}</b> (<code>{target_id}</code>) is already an admin.")
        return

    # Update in-memory list
    if target_id not in ADMINS:
        ADMINS.append(target_id)

    await message.reply_text(f"✅ <b>{name}</b> (<code>{target_id}</code>) is now an admin.")


# ─────────────────────────────────────────────────────────────────────────────
# /rm  – remove admin  (owner or existing admin; cannot remove owner)
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("rm") & filters.private)
async def rm_admin_cmd(client: Bot, message: Message):
    uid = message.from_user.id

    if not _is_owner_or_admin(uid):
        await message.reply_text("❌ Only admins can remove other admins.")
        return

    if len(message.command) < 2:
        await message.reply_text("<b>Usage:</b> <code>/rm user_id</code>")
        return

    try:
        target_id = int(message.command[1])
    except ValueError:
        await message.reply_text("❌ Invalid user ID.")
        return

    # Protect owner
    if target_id == OWNER_ID:
        await message.reply_text("🛡 The owner cannot be removed.")
        return

    try:
        user = await client.get_users(target_id)
        name = user.first_name
    except Exception:
        name = str(target_id)

    not_found = await del_admin(target_id)
    if not_found:
        await message.reply_text(f"⚠️ <b>{name}</b> (<code>{target_id}</code>) is not an admin.")
        return

    # Update in-memory list
    if target_id in ADMINS:
        ADMINS.remove(target_id)

    await message.reply_text(f"✅ <b>{name}</b> (<code>{target_id}</code>) removed from admins.")


# ─────────────────────────────────────────────────────────────────────────────
# /admins  – list all admins
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("admins") & filters.private)
async def list_admins_cmd(client: Bot, message: Message):
    uid = message.from_user.id
    if not _is_owner_or_admin(uid):
        await message.reply_text("❌ Only admins can view the admin list.")
        return

    db_admins = await full_adminbase()
    lines = []

    # Always show owner first
    try:
        owner = await client.get_users(OWNER_ID)
        lines.append(f"👑 <b>{owner.first_name}</b> — <code>{OWNER_ID}</code> (Owner)")
    except Exception:
        lines.append(f"👑 <code>{OWNER_ID}</code> (Owner)")

    for aid in db_admins:
        if aid == OWNER_ID:
            continue
        try:
            u = await client.get_users(aid)
            lines.append(f"🔑 <b>{u.first_name}</b> — <code>{aid}</code>")
        except Exception:
            lines.append(f"🔑 <code>{aid}</code>")

    text = "<b>👮 Admin List</b>\n\n" + "\n".join(lines) if lines else "<b>No admins yet.</b>"
    await message.reply_text(text)

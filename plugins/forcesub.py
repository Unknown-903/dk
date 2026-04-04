from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from bot import Bot
from config import OWNER_ID
from database.database import get_fsub_channels, add_fsub_channel, remove_fsub_channel


async def _is_bot_admin(client, channel_id: int) -> bool:
    """Check if bot is admin in the given channel."""
    try:
        me = await client.get_me()
        member = await client.get_chat_member(channel_id, me.id)
        from pyrogram.enums import ChatMemberStatus
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# /fsub  – add a new fsub channel
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("fsub") & filters.private & filters.user(OWNER_ID))
async def fsub_add(client: Bot, message: Message):
    if len(message.command) < 2:
        await message.reply_text(
            "<b>Usage:</b> <code>/fsub -100xxxxxxxxxx</code>\n\nAdd a channel to force-subscribe list."
        )
        return

    try:
        ch_id = int(message.command[1])
    except ValueError:
        await message.reply_text("❌ Invalid channel ID. It must be a number like <code>-1002864509771</code>")
        return

    # Validate bot is admin there
    if not await _is_bot_admin(client, ch_id):
        await message.reply_text(
            "❌ <b>Channel not found or bot is not admin there.</b>\n\n"
            "Make sure:\n• Bot is added as admin\n• The channel ID is correct"
        )
        return

    added = await add_fsub_channel(ch_id)
    if not added:
        await message.reply_text(f"⚠️ Channel <code>{ch_id}</code> is already in the FSub list.")
        return

    # Cache invite link
    try:
        chat = await client.get_chat(ch_id)
        link = chat.invite_link or await client.export_chat_invite_link(ch_id)
        client.fsub_invite_links[ch_id] = link
        name = chat.title
    except Exception:
        name = str(ch_id)

    await message.reply_text(f"✅ <b>{name}</b> (<code>{ch_id}</code>) added to FSub list.")


# ─────────────────────────────────────────────────────────────────────────────
# /sf  – show all fsub channels (with toggle remove buttons)
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("sf") & filters.private & filters.user(OWNER_ID))
async def show_fsub(client: Bot, message: Message):
    channels = await get_fsub_channels()
    if not channels:
        await message.reply_text("📭 No FSub channels set yet.\nUse /fsub <channel_id> to add one.")
        return

    lines   = []
    buttons = []
    for ch_id in channels:
        try:
            chat = await client.get_chat(ch_id)
            name = chat.title
        except Exception:
            name = "Unknown"
        lines.append(f"• <b>{name}</b> — <code>{ch_id}</code>")
        buttons.append([InlineKeyboardButton(f"🗑 Remove {name}", callback_data=f"rm_fsub:{ch_id}")])

    text = "<b>📢 Current FSub Channels:</b>\n\n" + "\n".join(lines)
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ─────────────────────────────────────────────────────────────────────────────
# /chnge  – alias: open the same remove-toggle panel
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("chnge") & filters.private & filters.user(OWNER_ID))
async def chnge_cmd(client: Bot, message: Message):
    await show_fsub(client, message)


# ─────────────────────────────────────────────────────────────────────────────
# Callback – remove fsub channel button
# ─────────────────────────────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex(r"^rm_fsub:(-?\d+)$"))
async def rm_fsub_cb(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("Only the owner can do this.", show_alert=True)
        return

    ch_id = int(query.matches[0].group(1))
    removed = await remove_fsub_channel(ch_id)
    client.fsub_invite_links.pop(ch_id, None)

    if removed:
        await query.answer(f"✅ Channel {ch_id} removed.", show_alert=True)
    else:
        await query.answer("⚠️ Channel not found in list.", show_alert=True)

    # Refresh the message
    channels = await get_fsub_channels()
    if not channels:
        await query.message.edit_text("📭 No FSub channels set. Use /fsub <id> to add one.")
        return

    lines   = []
    buttons = []
    for cid in channels:
        try:
            chat = await client.get_chat(cid)
            name = chat.title
        except Exception:
            name = "Unknown"
        lines.append(f"• <b>{name}</b> — <code>{cid}</code>")
        buttons.append([InlineKeyboardButton(f"🗑 Remove {name}", callback_data=f"rm_fsub:{cid}")])

    await query.message.edit_text(
        "<b>📢 Current FSub Channels:</b>\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
    )

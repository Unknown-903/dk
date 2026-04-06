import asyncio
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ChatMemberStatus

from bot import Bot
from config import OWNER_ID
from database.database import (
    get_fsub_channels, add_fsub_channel, add_fsub_folder,
    update_fsub_channel, remove_fsub_entry
)


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _bot_is_admin(client, channel_id: int) -> bool:
    try:
        me = await client.get_me()
        member = await client.get_chat_member(channel_id, me.id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False

async def _listen(client, chat_id, timeout=90):
    """Listen for next message, raise TimeoutError on timeout."""
    return await client.listen(chat_id, timeout=timeout)

def _display_name(ch: dict, fallback: str = "") -> str:
    return ch.get('custom_name') or fallback or str(ch.get('id', ''))


# ── /mfsub panel ─────────────────────────────────────────────────────────────
async def _mfsub_panel(client) -> tuple:
    entries = await get_fsub_channels()
    if not entries:
        return (
            "<b>Koi FSub entry set nahi hai.</b>\n/fsub se add karo.",
            InlineKeyboardMarkup([[InlineKeyboardButton("Close", callback_data="mfsub_close")]])
        )

    lines   = ["<b>FSub List:</b>\n"]
    buttons = []
    for entry in entries:
        etype = entry.get('type', 'public')
        eid   = entry.get('id')

        if etype == 'folder':
            fallback = "Folder"
            name     = _display_name(entry, fallback)
            lines.append(f"<b>{name}</b> — Folder")
            buttons.append([
                InlineKeyboardButton(f"{name} — Edit",   callback_data=f"mfsub_edit_folder:{eid}"),
                InlineKeyboardButton("Remove", callback_data=f"mfsub_rm:{eid}"),
            ])
        else:
            try:
                tg_name = (await client.get_chat(eid)).title or str(eid)
            except Exception:
                tg_name = str(eid)
            name = _display_name(entry, tg_name)
            lines.append(f"<b>{name}</b> — {etype} (<code>{eid}</code>)")
            buttons.append([
                InlineKeyboardButton(f"{name} — Edit",   callback_data=f"mfsub_edit:{eid}"),
                InlineKeyboardButton("Remove", callback_data=f"mfsub_rm:{eid}"),
            ])

    buttons.append([InlineKeyboardButton("Close", callback_data="mfsub_close")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


# ── /fsub — Step 1: choose type ───────────────────────────────────────────────
@Bot.on_message(filters.command("fsub") & filters.private & filters.user(OWNER_ID))
async def fsub_start(client: Bot, message: Message):
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Public",  callback_data="fsub_type:public"),
            InlineKeyboardButton("Private", callback_data="fsub_type:private"),
        ],
        [
            InlineKeyboardButton("Request", callback_data="fsub_type:request"),
            InlineKeyboardButton("Folder",  callback_data="fsub_type:folder"),
        ],
        [InlineKeyboardButton("Cancel", callback_data="fsub_cancel")],
    ])
    await message.reply_text(
        "<b>New FSub Entry</b>\n\n"
        "<b>Public</b> — Public channel, bot admin hona chahiye\n"
        "<b>Private</b> — Private channel, bot admin + invite link\n"
        "<b>Request</b> — Join request collect karta hai\n"
        "<b>Folder</b> — Telegram folder link (bot admin ki zarurat nahi)",
        reply_markup=markup,
    )


# ── Folder flow ───────────────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex(r"^fsub_type:folder$"))
async def fsub_folder(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("Sirf owner.", show_alert=True)
        return

    await query.message.edit_text(
        "<b>Folder FSub</b>\n\n"
        "Telegram folder link bhejo\n"
        "(e.g. <code>https://t.me/addlist/xxxxxxxxxx</code>)\n\n"
        "/cancel to abort."
    )
    await query.answer()

    try:
        reply = await _listen(client, query.message.chat.id)
    except asyncio.TimeoutError:
        await query.message.edit_text("Timeout. /fsub se dobara try karo.")
        return

    if reply.text and reply.text.strip() == "/cancel":
        await reply.reply_text("Cancelled.")
        return

    folder_link = reply.text.strip() if reply.text else ""
    if not folder_link.startswith("https://t.me/"):
        await reply.reply_text("Invalid link. https://t.me/ se start hona chahiye.")
        return

    # Ask custom name
    await reply.reply_text(
        "Custom naam set karna chahte ho?\n\n"
        "Naam bhejo (emoji + text dono allowed) ya <code>skip</code>.\n"
        "/cancel to abort."
    )
    try:
        name_reply = await _listen(client, reply.chat.id)
    except asyncio.TimeoutError:
        await reply.reply_text("Timeout.")
        return

    if name_reply.text and name_reply.text.strip() == "/cancel":
        await name_reply.reply_text("Cancelled.")
        return

    custom_name = None
    if name_reply.text and name_reply.text.strip().lower() != "skip":
        custom_name = name_reply.text.strip()

    added = await add_fsub_folder(folder_link, custom_name)
    if not added:
        await name_reply.reply_text("Yeh folder already added hai.")
        return

    display = custom_name or "Folder"
    await name_reply.reply_text(f"<b>{display}</b> folder added!\nLink: {folder_link}")


# ── Channel flow ──────────────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex(r"^fsub_type:(public|private|request)$"))
async def fsub_channel(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("Sirf owner.", show_alert=True)
        return

    ch_type = query.matches[0].group(1)
    labels  = {"public": "Public", "private": "Private", "request": "Request"}

    await query.message.edit_text(
        f"<b>{labels[ch_type]} FSub</b>\n\n"
        "Channel ID bhejo (e.g. <code>-1002864509771</code>)\n\n"
        "/cancel to abort."
    )
    await query.answer()

    # Get channel ID
    try:
        reply = await _listen(client, query.message.chat.id)
    except asyncio.TimeoutError:
        await query.message.edit_text("Timeout. /fsub se dobara try karo.")
        return

    if reply.text and reply.text.strip() == "/cancel":
        await reply.reply_text("Cancelled.")
        return

    try:
        ch_id = int(reply.text.strip())
    except (ValueError, AttributeError):
        await reply.reply_text("Invalid ID. /fsub se dobara try karo.")
        return

    if not await _bot_is_admin(client, ch_id):
        await reply.reply_text(
            "<b>Channel nahi mila ya bot admin nahi hai.</b>\n"
            "Bot ko admin banao phir dobara try karo."
        )
        return

    # Get custom name
    await reply.reply_text(
        "Custom naam set karna chahte ho?\n\n"
        "Naam bhejo (emoji + text dono allowed) ya <code>skip</code>.\n"
        "/cancel to abort."
    )
    try:
        name_reply = await _listen(client, reply.chat.id)
    except asyncio.TimeoutError:
        await reply.reply_text("Timeout.")
        return

    if name_reply.text and name_reply.text.strip() == "/cancel":
        await name_reply.reply_text("Cancelled.")
        return

    custom_name = None
    if name_reply.text and name_reply.text.strip().lower() != "skip":
        custom_name = name_reply.text.strip()

    # Request needs a join link
    if ch_type == "request":
        await name_reply.reply_text(
            "Join Request link bhejo\n"
            "(e.g. <code>https://t.me/+xxxxxxxxxx</code>)\n\n"
            "/cancel to abort."
        )
        try:
            link_reply = await _listen(client, name_reply.chat.id)
        except asyncio.TimeoutError:
            await name_reply.reply_text("Timeout.")
            return

        if link_reply.text and link_reply.text.strip() == "/cancel":
            await link_reply.reply_text("Cancelled.")
            return

        custom_link = link_reply.text.strip() if link_reply.text else ""
        if not custom_link.startswith("https://t.me/"):
            await link_reply.reply_text("Invalid link. /fsub se dobara try karo.")
            return

        added = await add_fsub_channel(ch_id, "request", custom_link, custom_name)
        if not added:
            await link_reply.reply_text(f"Channel <code>{ch_id}</code> already added hai.")
            return

        try:
            tg_name = (await client.get_chat(ch_id)).title or str(ch_id)
        except Exception:
            tg_name = str(ch_id)

        display = custom_name or tg_name
        await link_reply.reply_text(
            f"<b>{display}</b> (<code>{ch_id}</code>) added!\n"
            f"Type: Request\nLink: {custom_link}"
        )
    else:
        added = await add_fsub_channel(ch_id, ch_type, None, custom_name)
        if not added:
            await name_reply.reply_text(f"Channel <code>{ch_id}</code> already added hai.")
            return

        try:
            chat    = await client.get_chat(ch_id)
            tg_name = chat.title or str(ch_id)
            link    = chat.invite_link or await client.export_chat_invite_link(ch_id)
            client.fsub_invite_links[ch_id] = link
        except Exception:
            tg_name = str(ch_id)

        display = custom_name or tg_name
        await name_reply.reply_text(
            f"<b>{display}</b> (<code>{ch_id}</code>) added!\n"
            f"Type: {ch_type.capitalize()}"
        )


@Bot.on_callback_query(filters.regex(r"^fsub_cancel$"))
async def fsub_cancel(client: Bot, query: CallbackQuery):
    await query.message.edit_text("Cancelled.")


# ── /mfsub ────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("mfsub") & filters.private & filters.user(OWNER_ID))
async def mfsub_cmd(client: Bot, message: Message):
    text, markup = await _mfsub_panel(client)
    await message.reply_text(text, reply_markup=markup)


# Remove any entry (channel or folder)
@Bot.on_callback_query(filters.regex(r"^mfsub_rm:(.+)$"))
async def mfsub_remove(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("Sirf owner.", show_alert=True)
        return

    raw = query.matches[0].group(1)
    # Try int first (channel), else str (folder link)
    try:
        entry_id = int(raw)
        client.fsub_invite_links.pop(entry_id, None)
    except ValueError:
        entry_id = raw

    removed = await remove_fsub_entry(entry_id)
    await query.answer("Removed." if removed else "Not found.", show_alert=True)
    text, markup = await _mfsub_panel(client)
    await query.message.edit_text(text, reply_markup=markup)


# ── Edit channel ──────────────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex(r"^mfsub_edit:(-?\d+)$"))
async def mfsub_edit_channel(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("Sirf owner.", show_alert=True)
        return

    ch_id    = int(query.matches[0].group(1))
    entries  = await get_fsub_channels()
    entry    = next((e for e in entries if e.get('id') == ch_id), None)
    if not entry:
        await query.answer("Entry nahi mili.", show_alert=True)
        return

    try:
        tg_name = (await client.get_chat(ch_id)).title or str(ch_id)
    except Exception:
        tg_name = str(ch_id)

    name    = _display_name(entry, tg_name)
    ch_type = entry.get('type', 'public')

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Public",  callback_data=f"mfsub_chtype:{ch_id}:public"),
            InlineKeyboardButton("Private", callback_data=f"mfsub_chtype:{ch_id}:private"),
        ],
        [
            InlineKeyboardButton("Request", callback_data=f"mfsub_chtype:{ch_id}:request"),
        ],
        [InlineKeyboardButton("Link update karo",  callback_data=f"mfsub_chlink:{ch_id}")],
        [InlineKeyboardButton("Custom naam badlo", callback_data=f"mfsub_chname:{ch_id}")],
        [InlineKeyboardButton("Back",              callback_data="mfsub_back")],
    ])
    await query.message.edit_text(
        f"<b>Edit: {name}</b>\n"
        f"ID: <code>{ch_id}</code>\n"
        f"Type: <b>{ch_type}</b>\n"
        f"Custom naam: <b>{entry.get('custom_name') or 'None'}</b>\n"
        f"Link: <b>{entry.get('link') or 'None'}</b>",
        reply_markup=markup,
    )
    await query.answer()


# ── Edit folder ───────────────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex(r"^mfsub_edit_folder:(.+)$"))
async def mfsub_edit_folder(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("Sirf owner.", show_alert=True)
        return

    folder_link = query.matches[0].group(1)
    entries     = await get_fsub_channels()
    entry       = next((e for e in entries if e.get('id') == folder_link), None)
    if not entry:
        await query.answer("Entry nahi mili.", show_alert=True)
        return

    name = _display_name(entry, "Folder")
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Custom naam badlo", callback_data=f"mfsub_folder_name:{folder_link}")],
        [InlineKeyboardButton("Link badlo",        callback_data=f"mfsub_folder_link:{folder_link}")],
        [InlineKeyboardButton("Back",              callback_data="mfsub_back")],
    ])
    await query.message.edit_text(
        f"<b>Edit Folder: {name}</b>\n"
        f"Link: <code>{folder_link}</code>\n"
        f"Custom naam: <b>{entry.get('custom_name') or 'None'}</b>",
        reply_markup=markup,
    )
    await query.answer()


# ── Folder: change naam ───────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex(r"^mfsub_folder_name:(.+)$"))
async def mfsub_folder_name(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("Sirf owner.", show_alert=True)
        return

    folder_link = query.matches[0].group(1)
    await query.message.edit_text(
        "Naya custom naam bhejo (emoji + text dono allowed).\n"
        "<code>none</code> bhejo naam hatane ke liye.\n\n"
        "/cancel to abort."
    )
    await query.answer()

    try:
        reply = await _listen(client, query.message.chat.id)
    except asyncio.TimeoutError:
        await query.message.edit_text("Timeout.")
        return

    if reply.text and reply.text.strip() == "/cancel":
        await reply.reply_text("Cancelled.")
        return

    val         = reply.text.strip() if reply.text else ""
    custom_name = None if val.lower() == "none" else val

    await update_fsub_channel(folder_link, custom_name=custom_name, update_name=True)
    msg = f"Custom naam set: <b>{custom_name}</b>" if custom_name else "Custom naam hata diya."
    await reply.reply_text(msg)

    text, markup = await _mfsub_panel(client)
    await reply.reply_text(text, reply_markup=markup)


# ── Folder: change link ───────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex(r"^mfsub_folder_link:(.+)$"))
async def mfsub_folder_link_change(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("Sirf owner.", show_alert=True)
        return

    old_link = query.matches[0].group(1)
    await query.message.edit_text(
        "Naya folder link bhejo (https://t.me/addlist/...)\n\n/cancel to abort."
    )
    await query.answer()

    try:
        reply = await _listen(client, query.message.chat.id)
    except asyncio.TimeoutError:
        await query.message.edit_text("Timeout.")
        return

    if reply.text and reply.text.strip() == "/cancel":
        await reply.reply_text("Cancelled.")
        return

    new_link = reply.text.strip() if reply.text else ""
    if not new_link.startswith("https://t.me/"):
        await reply.reply_text("Invalid link.")
        return

    # Update link (stored as both id and link field)
    await update_fsub_channel(old_link, link=new_link)
    # Also update id field by re-saving
    entries = await get_fsub_channels()
    for e in entries:
        if e.get('id') == old_link:
            e['id']   = new_link
            e['link'] = new_link
            break
    from database.database import _save_fsub
    await _save_fsub(entries)

    await reply.reply_text(f"Folder link updated.")
    text, markup = await _mfsub_panel(client)
    await reply.reply_text(text, reply_markup=markup)


# ── Channel: change type ──────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex(r"^mfsub_chtype:(-?\d+):(public|private|request)$"))
async def mfsub_change_type(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("Sirf owner.", show_alert=True)
        return

    ch_id   = int(query.matches[0].group(1))
    ch_type = query.matches[0].group(2)

    if ch_type == "request":
        await query.message.edit_text(
            "Join Request link bhejo (https://t.me/+...)\n\n/cancel to abort."
        )
        await query.answer()
        try:
            reply = await _listen(client, query.message.chat.id)
        except asyncio.TimeoutError:
            await query.message.edit_text("Timeout.")
            return

        if reply.text and reply.text.strip() == "/cancel":
            await reply.reply_text("Cancelled.")
            return

        link = reply.text.strip() if reply.text else ""
        if not link.startswith("https://t.me/"):
            await reply.reply_text("Invalid link.")
            return

        await update_fsub_channel(ch_id, ch_type="request", link=link)
        await reply.reply_text("Type → Request")
    else:
        await update_fsub_channel(ch_id, ch_type=ch_type, link=None)
        try:
            inv = (await client.get_chat(ch_id)).invite_link or await client.export_chat_invite_link(ch_id)
            client.fsub_invite_links[ch_id] = inv
        except Exception:
            pass
        await query.message.edit_text(f"Type → {ch_type.capitalize()}")
        await query.answer()

    text, markup = await _mfsub_panel(client)
    await query.message.reply_text(text, reply_markup=markup)


# ── Channel: change link ──────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex(r"^mfsub_chlink:(-?\d+)$"))
async def mfsub_change_link(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("Sirf owner.", show_alert=True)
        return

    ch_id = int(query.matches[0].group(1))
    await query.message.edit_text("Naya link bhejo (https://t.me/...)\n\n/cancel to abort.")
    await query.answer()

    try:
        reply = await _listen(client, query.message.chat.id)
    except asyncio.TimeoutError:
        await query.message.edit_text("Timeout.")
        return

    if reply.text and reply.text.strip() == "/cancel":
        await reply.reply_text("Cancelled.")
        return

    link = reply.text.strip() if reply.text else ""
    if not link.startswith("https://t.me/"):
        await reply.reply_text("Invalid link.")
        return

    await update_fsub_channel(ch_id, link=link)
    await reply.reply_text("Link updated.")

    text, markup = await _mfsub_panel(client)
    await reply.reply_text(text, reply_markup=markup)


# ── Channel: change naam ──────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex(r"^mfsub_chname:(-?\d+)$"))
async def mfsub_change_name(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("Sirf owner.", show_alert=True)
        return

    ch_id = int(query.matches[0].group(1))
    await query.message.edit_text(
        "Naya custom naam bhejo (emoji + text dono allowed).\n"
        "<code>none</code> bhejo naam hatane ke liye.\n\n"
        "/cancel to abort."
    )
    await query.answer()

    try:
        reply = await _listen(client, query.message.chat.id)
    except asyncio.TimeoutError:
        await query.message.edit_text("Timeout.")
        return

    if reply.text and reply.text.strip() == "/cancel":
        await reply.reply_text("Cancelled.")
        return

    val         = reply.text.strip() if reply.text else ""
    custom_name = None if val.lower() == "none" else val

    await update_fsub_channel(ch_id, custom_name=custom_name, update_name=True)
    msg = f"Custom naam set: <b>{custom_name}</b>" if custom_name else "Custom naam hata diya."
    await reply.reply_text(msg)

    text, markup = await _mfsub_panel(client)
    await reply.reply_text(text, reply_markup=markup)


# ── Back / Close ──────────────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex(r"^mfsub_back$"))
async def mfsub_back(client: Bot, query: CallbackQuery):
    if query.from_user.id != OWNER_ID:
        await query.answer("Sirf owner.", show_alert=True)
        return
    text, markup = await _mfsub_panel(client)
    await query.message.edit_text(text, reply_markup=markup)
    await query.answer()

@Bot.on_callback_query(filters.regex(r"^mfsub_close$"))
async def mfsub_close(client: Bot, query: CallbackQuery):
    await query.message.delete()

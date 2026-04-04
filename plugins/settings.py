from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from bot import Bot
from config import OWNER_ID, ADMINS, START_MSG
from database.database import get_settings, update_setting
from helper_func import readable_time


def _is_owner_or_admin(uid: int) -> bool:
    return uid == OWNER_ID or uid in ADMINS


async def _settings_markup(settings: dict) -> InlineKeyboardMarkup:
    auto_del    = settings.get("auto_del", True)
    del_timer   = settings.get("del_timer", 120)
    dump_ch     = settings.get("dump_channel")
    custom_start = settings.get("custom_start_msg")

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🗑 Auto Delete: {'✅ ON' if auto_del else '❌ OFF'}",
            callback_data="toggle:auto_del"
        )],
        [InlineKeyboardButton(
            f"⏱ Delete Timer: {readable_time(del_timer)}",
            callback_data="set:del_timer"
        )],
        [InlineKeyboardButton(
            f"📦 Dump Channel: {'✅ ' + str(dump_ch) if dump_ch else '❌ None'}",
            callback_data="set:dump_channel"
        )],
        [InlineKeyboardButton(
            f"💬 Start Message: {'✅ Custom' if custom_start else '⚙️ Default'}",
            callback_data="set:custom_start_msg"
        )],
        [InlineKeyboardButton("❌ Close", callback_data="close_modify")],
    ])


def _settings_text(settings: dict) -> str:
    custom_start = settings.get("custom_start_msg")
    preview = (custom_start[:40] + "…") if custom_start and len(custom_start) > 40 else (custom_start or "Default")
    return (
        "<b>⚙️ Bot Settings</b>\n\n"
        f"🗑 Auto Delete: <b>{'ON' if settings.get('auto_del', True) else 'OFF'}</b>\n"
        f"⏱ Delete Timer: <b>{readable_time(settings.get('del_timer', 120))}</b>\n"
        f"📦 Dump Channel: <b>{settings.get('dump_channel') or 'None'}</b>\n"
        f"💬 Start Message: <b>{preview}</b>\n\n"
        "Tap a button to change a setting."
    )


# ── /modify ────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.command("modify") & filters.private)
async def modify_cmd(client: Bot, message: Message):
    if not _is_owner_or_admin(message.from_user.id):
        await message.reply_text("❌ Only admins can modify settings.")
        return
    settings = await get_settings()
    await message.reply_text(
        _settings_text(settings),
        reply_markup=await _settings_markup(settings),
    )


# ── Toggle auto_del ───────────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex(r"^toggle:auto_del$"))
async def toggle_auto_del(client: Bot, query: CallbackQuery):
    if not _is_owner_or_admin(query.from_user.id):
        await query.answer("❌ No permission.", show_alert=True)
        return
    settings = await get_settings()
    new_val  = not settings.get("auto_del", True)
    await update_setting("auto_del", new_val)
    settings["auto_del"] = new_val
    await query.message.edit_text(
        _settings_text(settings),
        reply_markup=await _settings_markup(settings),
    )
    await query.answer(f"Auto Delete {'enabled' if new_val else 'disabled'}.")


# ── Set fields ────────────────────────────────────────────────────────────────
@Bot.on_callback_query(filters.regex(r"^set:(del_timer|dump_channel|custom_start_msg)$"))
async def set_field(client: Bot, query: CallbackQuery):
    if not _is_owner_or_admin(query.from_user.id):
        await query.answer("❌ No permission.", show_alert=True)
        return

    field = query.matches[0].group(1)

    prompts = {
        "del_timer":
            "⏱ Send new delete timer in <b>seconds</b> (e.g. <code>300</code>):",
        "dump_channel":
            "📦 Send the dump channel ID (e.g. <code>-1002864509771</code>).\n"
            "Send <code>none</code> to remove.",
        "custom_start_msg":
            "💬 Send your custom <b>Start Message</b>.\n\n"
            "You can use these variables:\n"
            "<code>{first}</code> – first name\n"
            "<code>{last}</code> – last name\n"
            "<code>{username}</code> – @username\n"
            "<code>{mention}</code> – mention\n"
            "<code>{id}</code> – user ID\n\n"
            "Send <code>none</code> to reset to default.",
    }

    await query.message.edit_text(prompts[field] + "\n\nSend /cancel to abort.")
    await query.answer()

    try:
        reply = await client.listen(query.message.chat.id, timeout=120)
    except Exception:
        await query.message.edit_text("⏰ Timed out. Use /modify again.")
        return

    if reply.text and reply.text.strip().lower() == "/cancel":
        await reply.reply_text("❌ Cancelled.")
        return

    val_text = reply.text.strip() if reply.text else ""

    if field == "del_timer":
        try:
            val = int(val_text)
            if val < 10:
                await reply.reply_text("❌ Minimum timer is 10 seconds.")
                return
        except ValueError:
            await reply.reply_text("❌ Please send a valid number.")
            return
        await update_setting("del_timer", val)
        await reply.reply_text(f"✅ Delete timer set to {readable_time(val)}.")

    elif field == "dump_channel":
        if val_text.lower() == "none":
            await update_setting("dump_channel", None)
            await reply.reply_text("✅ Dump channel removed.")
        else:
            try:
                ch_id = int(val_text)
            except ValueError:
                await reply.reply_text("❌ Invalid channel ID.")
                return
            try:
                await client.get_chat(ch_id)
            except Exception:
                await reply.reply_text(
                    "❌ <b>Channel not found or bot is not admin there.</b>\n"
                    "Make the bot admin in that channel first."
                )
                return
            await update_setting("dump_channel", ch_id)
            await reply.reply_text(f"✅ Dump channel set to <code>{ch_id}</code>.")

    elif field == "custom_start_msg":
        if val_text.lower() == "none":
            await update_setting("custom_start_msg", None)
            await reply.reply_text("✅ Start message reset to default.")
        else:
            # Quick validation — try formatting with dummy values
            try:
                val_text.format(first="Test", last="User", username="@test", mention="Test", id=123)
            except KeyError as e:
                await reply.reply_text(f"❌ Invalid variable: {e}\nCheck your message and try again.")
                return
            await update_setting("custom_start_msg", val_text)
            await reply.reply_text(
                f"✅ Start message saved!\n\n<b>Preview:</b>\n"
                + val_text.format(
                    first="John", last="Doe", username="@johndoe",
                    mention="John", id=123456789
                )
            )

    settings = await get_settings()
    await reply.reply_text(
        _settings_text(settings),
        reply_markup=await _settings_markup(settings),
    )


@Bot.on_callback_query(filters.regex(r"^close_modify$"))
async def close_modify(client: Bot, query: CallbackQuery):
    await query.message.delete()

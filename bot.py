import pyrogram.utils
pyrogram.utils.MIN_CHANNEL_ID = -1009999999999

from aiohttp import web
from plugins import web_server

import pyromod.listen
from pyrogram import Client
from pyrogram.enums import ParseMode
from datetime import datetime

from config import API_HASH, APP_ID, LOGGER, TG_BOT_TOKEN, TG_BOT_WORKERS, CHANNEL_ID, PORT, OWNER_ID, ADMINS
from database.database import full_adminbase, get_fsub_channels


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="Bot",
            api_hash=API_HASH,
            api_id=APP_ID,
            plugins={"root": "plugins"},
            workers=TG_BOT_WORKERS,
            bot_token=TG_BOT_TOKEN,
        )
        self.LOGGER = LOGGER

    async def start(self):
        await super().start()
        me = await self.get_me()
        self.username = me.username
        self.uptime   = datetime.now()

        # ── Load admins from DB into memory ───────────────────────────────────
        db_admins = await full_adminbase()
        for aid in db_admins:
            if aid not in ADMINS:
                ADMINS.append(aid)
        if OWNER_ID not in ADMINS:
            ADMINS.append(OWNER_ID)

        # ── Validate DB channel ───────────────────────────────────────────────
        try:
            db_channel = await self.get_chat(CHANNEL_ID)
            self.db_channel = db_channel
            test = await self.send_message(chat_id=db_channel.id, text="✅ Bot started.")
            await test.delete()
        except Exception as e:
            self.LOGGER(__name__).error(f"DB Channel error: {e}")
            raise SystemExit(f"Cannot access DB channel {CHANNEL_ID}. Make bot admin there.")

        # ── Validate fsub channels (warn, don't crash) ─────────────────────
        channels = await get_fsub_channels()
        self.fsub_invite_links = {}
        for ch_id in channels:
            try:
                chat = await self.get_chat(ch_id)
                link = chat.invite_link or await self.export_chat_invite_link(ch_id)
                self.fsub_invite_links[ch_id] = link
            except Exception as e:
                self.LOGGER(__name__).warning(f"FSub channel {ch_id} inaccessible: {e}")

        self.set_parse_mode(ParseMode.HTML)
        self.LOGGER(__name__).info(f"Bot @{self.username} started successfully.")

        # ── Web server ────────────────────────────────────────────────────────
        runner = web.AppRunner(await web_server())
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", PORT).start()

    async def stop(self, *args):
        await super().stop()
        self.LOGGER(__name__).info("Bot stopped.")

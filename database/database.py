import asyncio
import pymongo
from config import DB_URI, DB_NAME

dbclient = pymongo.MongoClient(DB_URI)
database = dbclient[DB_NAME]

user_data      = database['users']
admin_data     = database['admins']
banned_data    = database['banned']
fsub_data      = database['fsub_channels']
settings_data  = database['bot_settings']
upload_stats   = database['upload_stats']


# ── Users ──────────────────────────────────────────────────────────────────────
async def present_user(user_id: int) -> bool:
    loop = asyncio.get_running_loop()
    found = await loop.run_in_executor(None, user_data.find_one, {'_id': user_id})
    return bool(found)

async def add_user(user_id: int):
    if not await present_user(user_id):
        user_data.insert_one({'_id': user_id})

async def del_user(user_id: int):
    user_data.delete_one({'_id': user_id})

async def full_userbase() -> list:
    return [doc['_id'] for doc in user_data.find()]


# ── Admins ─────────────────────────────────────────────────────────────────────
async def present_admin(admin_id: int) -> bool:
    loop = asyncio.get_running_loop()
    found = await loop.run_in_executor(None, admin_data.find_one, {'_id': admin_id})
    return bool(found)

async def add_admin(admin_id: int) -> bool:
    """Returns True if already existed."""
    if await present_admin(admin_id):
        return True
    admin_data.insert_one({'_id': admin_id})
    return False

async def del_admin(admin_id: int) -> bool:
    """Returns True if not found (nothing removed)."""
    if not await present_admin(admin_id):
        return True
    admin_data.delete_one({'_id': admin_id})
    return False

async def full_adminbase() -> list:
    return [doc['_id'] for doc in admin_data.find()]


# ── Banned users ───────────────────────────────────────────────────────────────
async def is_banned(user_id: int) -> bool:
    loop = asyncio.get_running_loop()
    found = await loop.run_in_executor(None, banned_data.find_one, {'_id': user_id})
    return bool(found)

async def ban_user(user_id: int):
    if not await is_banned(user_id):
        banned_data.insert_one({'_id': user_id})

async def unban_user(user_id: int):
    banned_data.delete_one({'_id': user_id})


# ── FSub channels (stored as list in one document) ─────────────────────────────
def _get_fsub_doc() -> dict:
    doc = fsub_data.find_one({'_id': 'fsub'})
    return doc or {'_id': 'fsub', 'channels': []}

async def get_fsub_channels() -> list:
    loop = asyncio.get_running_loop()
    doc = await loop.run_in_executor(None, _get_fsub_doc)
    return doc.get('channels', [])

async def add_fsub_channel(channel_id: int) -> bool:
    """Returns False if already exists, True on success."""
    channels = await get_fsub_channels()
    if channel_id in channels:
        return False
    channels.append(channel_id)
    fsub_data.update_one({'_id': 'fsub'}, {'$set': {'channels': channels}}, upsert=True)
    return True

async def remove_fsub_channel(channel_id: int) -> bool:
    """Returns False if not found."""
    channels = await get_fsub_channels()
    if channel_id not in channels:
        return False
    channels.remove(channel_id)
    fsub_data.update_one({'_id': 'fsub'}, {'$set': {'channels': channels}}, upsert=True)
    return True


# ── Bot settings (auto-delete, custom message, dump channel) ───────────────────
def _default_settings() -> dict:
    return {
        '_id': 'settings',
        'auto_del': True,
        'del_timer': 120,
        'custom_caption': None,
        'dump_channel': None,
    }

async def get_settings() -> dict:
    loop = asyncio.get_running_loop()
    doc = await loop.run_in_executor(None, settings_data.find_one, {'_id': 'settings'})
    if not doc:
        defaults = _default_settings()
        settings_data.insert_one(defaults)
        return defaults
    return doc

async def update_setting(key: str, value):
    settings_data.update_one({'_id': 'settings'}, {'$set': {key: value}}, upsert=True)


# ── Upload / rank stats ────────────────────────────────────────────────────────
async def record_upload(user_id: int, count: int = 1):
    upload_stats.update_one({'_id': user_id}, {'$inc': {'uploads': count}}, upsert=True)

async def get_upload_stats(user_id: int) -> int:
    doc = upload_stats.find_one({'_id': user_id})
    return doc['uploads'] if doc else 0

async def get_leaderboard(limit: int = 10) -> list:
    """Returns list of (user_id, uploads) sorted desc."""
    docs = upload_stats.find().sort('uploads', pymongo.DESCENDING).limit(limit)
    return [(doc['_id'], doc['uploads']) for doc in docs]

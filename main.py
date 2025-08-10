import os
import re
import aiohttp
import asyncio
from pathlib import Path
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image
from hachoir.parser import createParser
from hachoir.metadata import extractMetadata
import subprocess
import traceback

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

TMP = Path("tmp")
TMP.mkdir(parents=True, exist_ok=True)

USER_THUMBS = {}
TASKS = {}
ADMIN_ID = 6473423613  # আপনার Telegram ID
MAX_SIZE = 2 * 1024 * 1024 * 1024  # 2GB max size

app = Client("mybot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


def is_drive_url(url: str) -> bool:
    return "drive.google.com" in url


def extract_drive_id(url: str) -> str:
    patterns = [r"/d/([a-zA-Z0-9_-]+)", r"id=([a-zA-Z0-9_-]+)"]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def get_video_duration(file_path: Path) -> int:
    try:
        parser = createParser(str(file_path))
        if not parser:
            return 0
        with parser:
            metadata = extractMetadata(parser)
        if metadata and metadata.has("duration"):
            return int(metadata.get("duration").total_seconds())
    except Exception:
        return 0
    return 0


def progress_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Cancel ❌", callback_data="cancel_task")]]
    )


async def progress_callback(current, total, message: Message, start_time, task="Progress"):
    try:
        now = datetime.now()
        diff = (now - start_time).total_seconds()
        if diff == 0:
            diff = 1
        percentage = (current * 100 / total) if total else 0
        speed = (current / diff / 1024 / 1024) if diff else 0
        elapsed = int(diff)
        eta = int((total - current) / (current / diff)) if current and diff else 0

        done_blocks = int(percentage // 5)
        done_blocks = min(max(done_blocks, 0), 20)
        progress_bar = ("█" * done_blocks).ljust(20, "░")
        text = (
            f"{task}...\n"
            f"[{progress_bar}] {percentage:.2f}%\n"
            f"{current / 1024 / 1024:.2f}MB of {total / 1024 / 1024 if total else 0:.2f}MB\n"
            f"Speed: {speed:.2f} MB/s\n"
            f"Elapsed: {elapsed}s | ETA: {eta}s\n\n"
            "আপলোড/ডাউনলোড বাতিল করতে নিচের বাটনে চাপুন।"
        )
        try:
            await message.edit_text(text, reply_markup=progress_keyboard())
        except Exception:
            pass
    except Exception:
        pass


async def download_stream(resp, out_path: Path, message: Message = None, start_time=None, task="Downloading", cancel_event: asyncio.Event = None):
    total = 0
    try:
        size = int(resp.headers.get("Content-Length", 0))
    except:
        size = 0
    chunk_size = 256 * 1024
    try:
        with out_path.open("wb") as f:
            async for chunk in resp.content.iter_chunked(chunk_size):
                if cancel_event and cancel_event.is_set():
                    return False, "অপারেশন ব্যবহারকারী দ্বারা বাতিল করা হয়েছে।"
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_SIZE:
                    return False, "ফাইলের সাইজ 2GB এর বেশি হতে পারে না।"
                f.write(chunk)
                if message and start_time:
                    await progress_callback(total, size, message, start_time, task=task)
    except Exception as e:
        return False, str(e)
    return True, None


async def download_url_generic(url: str, out_path: Path, message: Message = None, cancel_event: asyncio.Event = None):
    try:
        timeout = aiohttp.ClientTimeout(total=3600)
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
            async with sess.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return False, f"HTTP {resp.status}"
                return await download_stream(resp, out_path, message, datetime.now(), task="Downloading", cancel_event=cancel_event)
    except Exception as e:
        return False, str(e)


async def download_drive_file(file_id: str, out_path: Path, message: Message = None, cancel_event: asyncio.Event = None):
    base = f"https://drive.google.com/uc?export=download&id={file_id}"
    try:
        timeout = aiohttp.ClientTimeout(total=3600)
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
            async with sess.get(base, allow_redirects=True) as resp:
                text = await resp.text(errors="ignore")
                if "content-disposition" in (k.lower() for k in resp.headers.keys()):
                    async with sess.get(base) as r2:
                        return await download_stream(r2, out_path, message, datetime.now(), task="Downloading", cancel_event=cancel_event)
                m = re.search(r"confirm=([0-9A-Za-z_-]+)", text)
                if m:
                    token = m.group(1)
                    download_url = f"https://drive.google.com/uc?export=download&confirm={token}&id={file_id}"
                    async with sess.get(download_url, allow_redirects=True) as resp2:
                        if resp2.status != 200:
                            return False, f"HTTP {resp2.status}"
                        return await download_stream(resp2, out_path, message, datetime.now(), task="Downloading", cancel_event=cancel_event)
                return False, "ডাউনলোডের জন্য Google Drive থেকে অনুমতি প্রয়োজন বা লিংক পাবলিক নয়।"
    except Exception as e:
        return False, str(e)


async def generate_video_thumbnail(video_path: Path, thumb_path: Path):
    try:
        duration = get_video_duration(video_path)
        timestamp = 1 if duration > 1 else 0
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-ss", str(timestamp),
            "-vframes", "1",
            "-vf", "scale=320:-1",
            str(thumb_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return thumb_path.exists() and thumb_path.stat().st_size > 0
    except Exception as e:
        print(f"Thumbnail generate error: {e}")
        return False


async def upload_progress(current, total, message: Message, start_time):
    await progress_callback(current, total, message, start_time, task="Uploading")


async def process_file_and_upload(c: Client, m: Message, in_path: Path, original_name: str = None):
    uid = m.from_user.id
    try:
        final_name = original_name or in_path.name
        thumb_path = USER_THUMBS.get(uid)
        if thumb_path and not Path(thumb_path).exists():
            thumb_path = None

        is_video = in_path.suffix.lower() in {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"}

        if is_video and not thumb_path:
            thumb_path_tmp = TMP / f"thumb_{uid}_{int(datetime.now().timestamp())}.jpg"
            ok = await generate_video_thumbnail(in_path, thumb_path_tmp)
            if ok:
                thumb_path = str(thumb_path_tmp)

        status_msg = await m.reply_text("আপলোড শুরু হচ্ছে...", reply_markup=progress_keyboard())
        cancel_event = asyncio.Event()
        TASKS[uid] = cancel_event
        start_time = datetime.now()

        duration_sec = get_video_duration(in_path) if in_path.exists() else 0

        try:
            if is_video:
                await c.send_video(
                    chat_id=m.chat.id,
                    video=str(in_path),
                    caption=final_name,
                    thumb=thumb_path,
                    duration=duration_sec,
                    progress=upload_progress,
                    progress_args=(status_msg, start_time)
                )
            else:
                await c.send_document(
                    chat_id=m.chat.id,
                    document=str(in_path),
                    file_name=final_name,
                    caption=final_name,
                    progress=upload_progress,
                    progress_args=(status_msg, start_time)
                )
            await status_msg.edit("আপলোড সম্পন্ন।", reply_markup=None)
        except Exception as e:
            await status_msg.edit(f"আপলোড ব্যর্থ: {e}", reply_markup=None)
        finally:
            TASKS.pop(uid, None)
    except Exception as e:
        TASKS.pop(uid, None)
        await m.reply_text(f"আপলোডে ত্রুটি: {e}")


# ========================== নতুন ফিচারগুলো এখানে ==========================

# ১. অটো থাম্বনেইল সেভ (image দিলে)
@app.on_message(filters.photo & filters.private & filters.user(ADMIN_ID))
async def auto_save_thumbnail(c: Client, m: Message):
    uid = m.from_user.id
    out = TMP / f"thumb_{uid}.jpg"
    try:
        await m.download(file_name=str(out))
        img = Image.open(out)
        img.thumbnail((320, 320))
        img = img.convert("RGB")
        img.save(out, "JPEG")
        USER_THUMBS[uid] = str(out)
        await m.reply_text("আপনার থাম্বনেইল স্বয়ংক্রিয়ভাবে সেভ হয়েছে।")
    except Exception as e:
        await m.reply_text(f"থাম্বনেইল সেভ করতে সমস্যা: {e}")


# ২. অটো URL আপলোড (কমান্ড ছাড়া)
@app.on_message(filters.private & filters.regex(r"https?://") & filters.user(ADMIN_ID))
async def auto_url_upload(c: Client, m: Message):
    url_match = re.search(r"https?://[^\s]+", m.text)
    if url_match:
        url = url_match.group(0)
        await m.reply_text(f"URL পাওয়া গেছে, ডাউনলোড ও আপলোড শুরু হচ্ছে...")
        await handle_url_download_and_upload(c, m, url)


# ৩. ভিডিও ফরওয়ার্ড করলে অটো রিনেম ও আপলোড (কমান্ড ছাড়া)
@app.on_message(filters.private & filters.video & filters.user(ADMIN_ID))
async def auto_rename_forward_video(c: Client, m: Message):
    uid = m.from_user.id
    tmp_path = TMP / f"forward_{uid}_{int(datetime.now().timestamp())}.mp4"
    try:
        await m.download(file_name=str(tmp_path))
        new_name = "new_video.mp4"
        await process_file_and_upload(c, m, tmp_path, original_name=new_name)
    except Exception as e:
        await m.reply_text(f"ফরওয়ার্ড ভিডিও প্রসেসে সমস্যা: {e}")


# ================ আগের কিছু কোড যেমন start, rename, cancel_task ইত্যাদি থাকবে নিচে ===================

# আপনার আগের যেসব হ্যান্ডলার দরকার যেমন /start, /rename, /cancel_task ইত্যাদি এখানে রাখতে পারেন


if __name__ == "__main__":
    print("Bot চালু হচ্ছে...")
    app.run()

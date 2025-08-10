import os
import re
import aiohttp
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
import sys

API_ID = int(os.getenv("API_ID", "0"))  # আপনার API_ID দিন environment variables এ
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # আপনার টেলিগ্রাম আইডি

TMP = Path("./tmp")
TMP.mkdir(exist_ok=True, parents=True)

app = Client("auto_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def generate_thumbnail(video_path: Path, thumb_path: Path) -> bool:
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-ss", "00:00:01",
            "-vframes", "1",
            "-vf", "scale=320:-1",
            str(thumb_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return thumb_path.exists() and thumb_path.stat().st_size > 0
    except Exception as e:
        print(f"Thumbnail error: {e}", file=sys.stderr)
        return False

async def download_file(url: str, dest: Path, progress_msg: Message = None):
    try:
        timeout = aiohttp.ClientTimeout(total=3600)
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 256 * 1024
                with dest.open("wb") as f:
                    async for chunk in resp.content.iter_chunked(chunk_size):
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_msg and total:
                            percent = downloaded * 100 / total
                            await progress_msg.edit(f"Downloading... {percent:.2f}%")
        return True, None
    except Exception as e:
        return False, str(e)

def is_video_file(filename: str) -> bool:
    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"}
    return any(filename.lower().endswith(ext) for ext in video_exts)

@app.on_message(filters.private & filters.regex(r"https?://"))
async def url_auto_upload(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    urls = re.findall(r"(https?://[^\s]+)", message.text)
    if not urls:
        return
    url = urls[0]

    filename = url.split("/")[-1].split("?")[0]
    if not filename:
        filename = f"file_{int(datetime.now().timestamp())}"

    if not is_video_file(filename):
        filename += ".mp4"

    tmp_file = TMP / filename

    status_msg = await message.reply_text("ডাউনলোড শুরু হচ্ছে...")
    ok, err = await download_file(url, tmp_file, status_msg)
    if not ok:
        await status_msg.edit(f"ডাউনলোড ব্যর্থ: {err}")
        if tmp_file.exists():
            tmp_file.unlink()
        return

    await status_msg.edit("ডাউনলোড শেষ, আপলোড শুরু হচ্ছে...")

    thumb_path = None
    if is_video_file(str(tmp_file)):
        thumb_path_candidate = TMP / f"thumb_{int(datetime.now().timestamp())}.jpg"
        if generate_thumbnail(tmp_file, thumb_path_candidate):
            thumb_path = str(thumb_path_candidate)

    try:
        if is_video_file(str(tmp_file)):
            await client.send_video(
                chat_id=message.chat.id,
                video=str(tmp_file),
                thumb=thumb_path,
                caption=filename
            )
        else:
            await client.send_document(
                chat_id=message.chat.id,
                document=str(tmp_file),
                caption=filename
            )
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit(f"আপলোডে সমস্যা: {e}")
    finally:
        if tmp_file.exists():
            tmp_file.unlink()
        if thumb_path and Path(thumb_path).exists():
            Path(thumb_path).unlink()

@app.on_message(filters.private & filters.video)
async def video_auto_rename(client: Client, message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    status_msg = await message.reply_text("ভিডিও প্রসেসিং হচ্ছে...")
    tmp_file = TMP / f"video_{int(datetime.now().timestamp())}.mp4"

    try:
        await message.download(file_name=str(tmp_file))
        thumb_path_candidate = TMP / f"thumb_{int(datetime.now().timestamp())}.jpg"
        thumb_path = None
        if generate_thumbnail(tmp_file, thumb_path_candidate):
            thumb_path = str(thumb_path_candidate)
        # Rename filename example: original filename + timestamp
        new_name = f"renamed_{int(datetime.now().timestamp())}.mp4"
        await client.send_video(
            chat_id=message.chat.id,
            video=str(tmp_file),
            thumb=thumb_path,
            caption=new_name
        )
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit(f"ত্রুটি: {e}")
    finally:
        if tmp_file.exists():
            tmp_file.unlink()
        if thumb_path and Path(thumb_path).exists():
            Path(thumb_path).unlink()

if __name__ == "__main__":
    print("Bot Starting...")
    app.run()

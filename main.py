import re
import aiohttp
import asyncio
from pathlib import Path
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
import subprocess
import os
import sys

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", ""))

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
        print(f"Thumbnail generation error: {e}", file=sys.stderr)
        return False


async def download_url(url: str, dest: Path, progress_message: Message = None):
    try:
        timeout = aiohttp.ClientTimeout(total=3600)
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP error: {resp.status}")
                total_size = int(resp.headers.get("Content-Length", 0))
                chunk_size = 256 * 1024
                downloaded = 0
                with dest.open("wb") as f:
                    async for chunk in resp.content.iter_chunked(chunk_size):
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_message and total_size > 0:
                            percent = downloaded * 100 / total_size
                            await progress_message.edit(f"ডাউনলোড হচ্ছে: {percent:.2f}%")
        return True, None
    except Exception as e:
        return False, str(e)


@app.on_message(filters.private & filters.user(ADMIN_ID) & filters.regex(r"https?://"))
async def auto_url_upload(client: Client, message: Message):
    url_match = re.search(r"https?://[^\s]+", message.text)
    if not url_match:
        return
    url = url_match.group(0)

    fname = url.split("/")[-1].split("?")[0]
    if not fname or len(fname) < 3:
        fname = f"file_{int(datetime.now().timestamp())}"
    dest_path = TMP / fname

    status_msg = await message.reply_text(f"URL পাওয়া গেছে:\n{url}\nডাউনলোড শুরু হচ্ছে...")
    ok, err = await download_url(url, dest_path, progress_message=status_msg)

    if not ok:
        await status_msg.edit(f"ডাউনলোড ব্যর্থ: {err}")
        if dest_path.exists():
            dest_path.unlink(missing_ok=True)
        return

    # Generate thumbnail if video
    thumb_path = None
    if dest_path.suffix.lower() in {".mp4", ".mkv", ".avi", ".mov"}:
        thumb_tmp = TMP / f"thumb_{message.from_user.id}_{int(datetime.now().timestamp())}.jpg"
        if generate_thumbnail(dest_path, thumb_tmp):
            thumb_path = str(thumb_tmp)

    try:
        if dest_path.suffix.lower() in {".mp4", ".mkv", ".avi", ".mov"}:
            await client.send_video(
                chat_id=message.chat.id,
                video=str(dest_path),
                caption=f"অটোমেটিক আপলোড: {fname}",
                thumb=thumb_path
            )
        else:
            await client.send_document(
                chat_id=message.chat.id,
                document=str(dest_path),
                caption=f"অটোমেটিক আপলোড: {fname}"
            )
        await status_msg.edit("আপলোড সম্পন্ন।")
    except Exception as e:
        await status_msg.edit(f"আপলোড ব্যর্থ: {e}")

    # Clean up temp files
    if dest_path.exists():
        dest_path.unlink(missing_ok=True)
    if thumb_path and Path(thumb_path).exists():
        Path(thumb_path).unlink(missing_ok=True)


@app.on_message(filters.private & filters.user(ADMIN_ID) & (filters.video | filters.document))
async def auto_file_rename_upload(client: Client, message: Message):
    uid = message.from_user.id
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Determine extension and new filename
    ext = ""
    if message.video:
        ext = (message.video.file_name or "mp4").split(".")[-1]
    elif message.document:
        ext = (message.document.file_name or "bin").split(".")[-1]
    new_name = f"auto_{uid}_{now_str}.{ext}"

    dest_path = TMP / new_name

    status_msg = await message.reply_text("ফাইল ডাউনলোড হচ্ছে...")
    try:
        await message.download(file_name=str(dest_path))
        await status_msg.edit("ডাউনলোড সম্পন্ন, আপলোড শুরু হচ্ছে...")
    except Exception as e:
        await status_msg.edit(f"ডাউনলোড ব্যর্থ: {e}")
        if dest_path.exists():
            dest_path.unlink(missing_ok=True)
        return

    thumb_path = None
    if ext.lower() in {"mp4", "mkv", "avi", "mov"}:
        thumb_tmp = TMP / f"thumb_{uid}_{int(datetime.now().timestamp())}.jpg"
        if generate_thumbnail(dest_path, thumb_tmp):
            thumb_path = str(thumb_tmp)

    try:
        if message.video:
            await client.send_video(
                chat_id=message.chat.id,
                video=str(dest_path),
                caption=new_name,
                thumb=thumb_path
            )
        else:
            await client.send_document(
                chat_id=message.chat.id,
                document=str(dest_path),
                caption=new_name
            )
        await status_msg.edit("অটোমেটিক আপলোড সম্পন্ন।")
    except Exception as e:
        await status_msg.edit(f"আপলোড ব্যর্থ: {e}")

    # Clean up temp files
    if dest_path.exists():
        dest_path.unlink(missing_ok=True)
    if thumb_path and Path(thumb_path).exists():
        Path(thumb_path).unlink(missing_ok=True)


if __name__ == "__main__":
    print("Auto Telegram Bot is running...")
    app.run()

import re
import asyncio
from pathlib import Path
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from PIL import Image
import subprocess

API_ID = 1234567
API_HASH = "your_api_hash"
BOT_TOKEN = "your_bot_token"
ADMIN_ID = 6473423613

TMP = Path("./tmp")
TMP.mkdir(exist_ok=True)

app = Client("autobot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return thumb_path.exists() and thumb_path.stat().st_size > 0
    except Exception:
        return False

async def download_and_upload_url(c: Client, m: Message, url: str):
    # Generate safe filename from URL
    fname = url.split("/")[-1].split("?")[0]
    if not fname:
        fname = f"file_{int(datetime.now().timestamp())}"
    out_path = TMP / fname

    # Download file with aiohttp or any method you want
    # For simplicity, skipping here — you can reuse your previous download code

    await m.reply_text(f"URL পাওয়া গেছে: {url}\nডাউনলোড শুরু হচ্ছে...")

    # TODO: Implement actual download logic here, then upload

    # After download, check if video, generate thumb
    thumb_path = None
    if out_path.suffix.lower() in {".mp4", ".mkv", ".avi", ".mov"}:
        thumb_path_tmp = TMP / f"thumb_{m.from_user.id}_{int(datetime.now().timestamp())}.jpg"
        if generate_thumbnail(out_path, thumb_path_tmp):
            thumb_path = str(thumb_path_tmp)

    # Upload video or document with or without thumb
    try:
        if out_path.suffix.lower() in {".mp4", ".mkv", ".avi", ".mov"}:
            await c.send_video(
                chat_id=m.chat.id,
                video=str(out_path),
                caption=f"অটোমেটিক আপলোড: {fname}",
                thumb=thumb_path
            )
        else:
            await c.send_document(
                chat_id=m.chat.id,
                document=str(out_path),
                caption=f"অটোমেটিক আপলোড: {fname}"
            )
        await m.reply_text("আপলোড সম্পন্ন।")
    except Exception as e:
        await m.reply_text(f"আপলোডে ত্রুটি: {e}")

@app.on_message(filters.private & filters.regex(r"https?://") & filters.user(ADMIN_ID))
async def auto_url_upload(c: Client, m: Message):
    url_match = re.search(r"https?://[^\s]+", m.text)
    if url_match:
        url = url_match.group(0)
        await download_and_upload_url(c, m, url)

@app.on_message(filters.private & (filters.video | filters.document) & filters.user(ADMIN_ID))
async def auto_forward_rename_upload(c: Client, m: Message):
    # Auto rename based on user and timestamp
    uid = m.from_user.id
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = ""
    if m.video:
        ext = m.video.file_name.split(".")[-1] if m.video.file_name else "mp4"
    elif m.document:
        ext = m.document.file_name.split(".")[-1] if m.document.file_name else "bin"
    new_name = f"auto_{uid}_{now}.{ext}"

    # Download file to tmp
    out_path = TMP / new_name
    await m.download(file_name=str(out_path))

    # Generate thumbnail if video
    thumb_path = None
    if ext.lower() in {"mp4", "mkv", "avi", "mov"}:
        thumb_path_tmp = TMP / f"thumb_{uid}_{int(datetime.now().timestamp())}.jpg"
        if generate_thumbnail(out_path, thumb_path_tmp):
            thumb_path = str(thumb_path_tmp)

    # Upload file with new name and thumb
    try:
        if m.video:
            await c.send_video(
                chat_id=m.chat.id,
                video=str(out_path),
                caption=new_name,
                thumb=thumb_path
            )
        else:
            await c.send_document(
                chat_id=m.chat.id,
                document=str(out_path),
                caption=new_name
            )
        await m.reply_text("অটোমেটিক ভিডিও আপলোড সম্পন্ন।")
    except Exception as e:
        await m.reply_text(f"আপলোডে ত্রুটি: {e}")

if __name__ == "__main__":
    print("অটোমেটিক বট শুরু হচ্ছে...")
    app.run()

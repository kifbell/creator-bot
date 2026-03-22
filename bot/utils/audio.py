import os
import shutil
import uuid
from pathlib import Path

from telegram import Bot


async def download_telegram_audio(bot: Bot, file_id: str, user_id: int) -> str:
    """Download a Telegram audio/voice file and save it to a temp path.

    Returns the local file path. Caller is responsible for deleting the file.
    """
    tg_file = await bot.get_file(file_id)
    suffix = os.path.splitext(tg_file.file_path or "audio.ogg")[1] or ".ogg"
    local_path = f"/tmp/{user_id}_{uuid.uuid4().hex}{suffix}"
    await tg_file.download_to_drive(local_path)
    return local_path


def persist_voice_sample(temp_path: str, user_id: int) -> str:
    """Copy temp audio file to data/voices/{user_id}/. Returns persistent path."""
    dest_dir = Path(f"data/voices/{user_id}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / os.path.basename(temp_path)
    shutil.copy2(temp_path, dest_path)
    return str(dest_path)


def delete_temp_file(path: str) -> None:
    """Delete a temp file, ignoring errors if it doesn't exist."""
    try:
        os.remove(path)
    except OSError:
        pass

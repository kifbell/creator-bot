import asyncio
import time

import httpx

from bot.providers.music.base_music import MusicProvider, MusicResult

_GENERATE_URL = "https://api.tempolor.com/open-apis/v1/song/generate"
_QUERY_URL = "https://api.tempolor.com/open-apis/v1/song/query"
_POLL_INTERVAL = 5      # seconds between status checks
_POLL_TIMEOUT = 300     # give up after 5 minutes
_SUCCESS_STATUS = "main_succeeded"


class TempolorMusicProvider(MusicProvider):
    def __init__(self, api_key: str, model: str = "TemPolor v4.0") -> None:
        self._api_key = api_key
        self.model = model

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": self._api_key,
            "Content-Type": "application/json; charset=utf-8",
        }

    async def generate(self, prompt: str) -> MusicResult:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _GENERATE_URL,
                headers=self._headers,
                json={
                    "prompt": prompt,
                    "model": self.model,
                    "callback_url": "https://example.com/callback",
                },
            )
            resp.raise_for_status()
            body = resp.json()

            if not body.get("success"):
                raise RuntimeError(f"Tempolor error: {body.get('message')}")

            item_id = body["data"]["item_ids"][0]

            audio_url = await self._poll(client, item_id)

            audio_resp = await client.get(audio_url, timeout=60.0)
            audio_resp.raise_for_status()

        return MusicResult(audio_bytes=audio_resp.content)

    async def _poll(self, client: httpx.AsyncClient, item_id: str) -> str:
        deadline = time.monotonic() + _POLL_TIMEOUT
        while time.monotonic() < deadline:
            await asyncio.sleep(_POLL_INTERVAL)
            resp = await client.post(
                _QUERY_URL,
                headers=self._headers,
                json={"item_ids": [item_id]},
            )
            resp.raise_for_status()
            songs = resp.json().get("data", {}).get("songs", [])
            if songs:
                song = songs[0]
                if song.get("status") == _SUCCESS_STATUS:
                    audio_url = song.get("audio_url")
                    if audio_url:
                        return audio_url
                err = song.get("err_msg")
                if err:
                    raise RuntimeError(f"Tempolor generation failed: {err}")
        raise TimeoutError(f"Tempolor timed out after {_POLL_TIMEOUT}s")

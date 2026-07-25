import base64
import re
from typing import Any, Dict

import httpx

from .cache import prediction_cache, token_cache
from .config import settings


class RedClError(Exception):
    pass


class TokenExtractionError(RedClError):
    pass


_JWT_REGEX = re.compile(r"\$jwt\s*=\s*'(.*?)'", re.DOTALL)


async def _fetch_token() -> str:
    headers = {"User-Agent": settings.user_agent}
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response = await client.get(settings.token_url, headers=headers)
        response.raise_for_status()
        html = response.text

    match = _JWT_REGEX.search(html)
    if not match:
        raise TokenExtractionError("Could not extract $jwt token from red.cl")

    encoded = match.group(1)
    try:
        return base64.b64decode(encoded).decode("utf-8")
    except Exception as exc:
        raise TokenExtractionError(f"Failed to decode JWT token: {exc}") from exc


async def get_token() -> str:
    async def factory() -> str:
        return await _fetch_token()

    return await token_cache.get_or_set("redcl_jwt", factory)


async def get_prediction(stop_id: str) -> Dict[str, Any]:
    stop_id = stop_id.strip().upper()

    async def factory() -> Dict[str, Any]:
        token = await get_token()
        params = {
            "t": token,
            "codsimt": stop_id,
            "codser": "",
        }
        headers = {"User-Agent": settings.user_agent}
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.get(
                settings.prediction_url,
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    return await prediction_cache.get_or_set(stop_id, factory)

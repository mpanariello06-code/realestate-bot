"""
Social media posting service for Facebook, Instagram, and TikTok.

Uses the Meta Graph API for Facebook/Instagram and a stub for TikTok
(TikTok's Content Posting API requires business-level approval).
"""

import json
import logging
import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_GRAPH_API_BASE = "https://graph.facebook.com/v19.0"
_REQUEST_TIMEOUT = 30.0  # seconds


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _token(agent_token: Optional[str], env_key: str) -> str:
    """Return agent-specific token, falling back to the environment-level token."""
    return agent_token or os.getenv(env_key, "")


async def _upload_photo_facebook(
    client: httpx.AsyncClient,
    page_id: str,
    access_token: str,
    photo_url: str,
    published: bool = False,
) -> Optional[str]:
    """Upload a single photo to Facebook and return its media object ID."""
    try:
        resp = await client.post(
            f"{_GRAPH_API_BASE}/{page_id}/photos",
            params={"access_token": access_token},
            data={"url": photo_url, "published": str(published).lower()},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to upload photo to Facebook: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Facebook
# ---------------------------------------------------------------------------


async def post_to_facebook(
    listing,
    agent_token: Optional[str] = None,
    page_id: Optional[str] = None,
) -> Optional[str]:
    """
    Post a listing to a Facebook Page using the Graph API.

    Supports multi-photo posts (uses the /{page_id}/feed endpoint for single
    photos, and the batch photo-attach approach for multiple).

    Args:
        listing: ORM Listing object.
        agent_token: Agent-specific Facebook page access token.
        page_id: Facebook Page ID.

    Returns:
        Facebook post ID string on success, None on failure.
    """
    token = _token(agent_token, "FACEBOOK_ACCESS_TOKEN")
    pid = page_id or os.getenv("FACEBOOK_PAGE_ID", "")

    if not token or not pid:
        logger.warning("Facebook credentials not configured – skipping post")
        return None

    import json as _json  # local import to keep module lightweight when unused

    photos: list[str] = []
    try:
        photos = _json.loads(listing.photos or "[]")
    except Exception:
        pass

    caption = (
        f"{listing.title}\n\n"
        f"{listing.description or ''}\n\n"
        f"📍 {listing.location or 'N/A'}  💰 {listing.price or 'N/A'}\n"
        f"🛏 {listing.bedrooms or '?'} beds  🚿 {listing.bathrooms or '?'} baths"
    )

    async with httpx.AsyncClient() as client:
        try:
            if len(photos) > 1:
                # Upload photos as unpublished, then attach to a feed post
                media_ids = []
                for photo_url in photos:
                    mid = await _upload_photo_facebook(client, pid, token, photo_url, published=False)
                    if mid:
                        media_ids.append({"media_fbid": mid})

                payload: dict = {
                    "message": caption,
                    "access_token": token,
                }
                if media_ids:
                    payload["attached_media"] = json.dumps(media_ids)

                resp = await client.post(
                    f"{_GRAPH_API_BASE}/{pid}/feed",
                    params={"access_token": token},
                    data=payload,
                    timeout=_REQUEST_TIMEOUT,
                )
            elif len(photos) == 1:
                resp = await client.post(
                    f"{_GRAPH_API_BASE}/{pid}/photos",
                    params={"access_token": token},
                    data={"url": photos[0], "message": caption},
                    timeout=_REQUEST_TIMEOUT,
                )
            else:
                # Text-only post
                resp = await client.post(
                    f"{_GRAPH_API_BASE}/{pid}/feed",
                    params={"access_token": token},
                    data={"message": caption},
                    timeout=_REQUEST_TIMEOUT,
                )

            resp.raise_for_status()
            post_id = resp.json().get("id") or resp.json().get("post_id")
            logger.info("Posted listing %s to Facebook: %s", listing.id, post_id)
            return post_id
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Facebook API error for listing %s: %s – %s",
                listing.id,
                exc.response.status_code,
                exc.response.text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error posting to Facebook: %s", exc)

    return None


# ---------------------------------------------------------------------------
# Instagram
# ---------------------------------------------------------------------------


async def post_to_instagram(
    listing,
    agent_token: Optional[str] = None,
    ig_account_id: Optional[str] = None,
) -> Optional[str]:
    """
    Post a listing to Instagram via the Meta Graph API (Instagram Graph API).

    Only the first photo is used for single-image posts. Multi-image carousel
    is supported when multiple photo URLs are provided.

    Args:
        listing: ORM Listing object.
        agent_token: Instagram-connected Facebook access token.
        ig_account_id: Instagram Business Account ID.

    Returns:
        Instagram media ID on success, None on failure.
    """
    token = _token(agent_token, "FACEBOOK_ACCESS_TOKEN")  # IG uses FB token
    ig_id = ig_account_id or os.getenv("INSTAGRAM_ACCOUNT_ID", "")

    if not token or not ig_id:
        logger.warning("Instagram credentials not configured – skipping post")
        return None

    import json as _json

    photos: list[str] = []
    try:
        photos = _json.loads(listing.photos or "[]")
    except Exception:
        pass

    caption = (
        f"{listing.title}\n\n"
        f"{listing.description or ''}\n\n"
        f"📍 {listing.location or 'N/A'}  💰 {listing.price or 'N/A'}\n"
        f"🛏 {listing.bedrooms or '?'} beds  🚿 {listing.bathrooms or '?'} baths\n\n"
        f"#realestate #property #forsale #home"
    )

    async with httpx.AsyncClient() as client:
        try:
            if len(photos) > 1:
                # Carousel post
                child_ids = []
                for photo_url in photos[:10]:  # IG carousel max 10
                    c_resp = await client.post(
                        f"{_GRAPH_API_BASE}/{ig_id}/media",
                        params={"access_token": token},
                        data={"image_url": photo_url, "is_carousel_item": "true"},
                        timeout=_REQUEST_TIMEOUT,
                    )
                    c_resp.raise_for_status()
                    child_ids.append(c_resp.json()["id"])

                container_resp = await client.post(
                    f"{_GRAPH_API_BASE}/{ig_id}/media",
                    params={"access_token": token},
                    data={
                        "media_type": "CAROUSEL",
                        "children": ",".join(child_ids),
                        "caption": caption,
                    },
                    timeout=_REQUEST_TIMEOUT,
                )
                container_resp.raise_for_status()
                container_id = container_resp.json()["id"]
            elif len(photos) == 1:
                container_resp = await client.post(
                    f"{_GRAPH_API_BASE}/{ig_id}/media",
                    params={"access_token": token},
                    data={"image_url": photos[0], "caption": caption},
                    timeout=_REQUEST_TIMEOUT,
                )
                container_resp.raise_for_status()
                container_id = container_resp.json()["id"]
            else:
                logger.warning("No photos for Instagram post – skipping")
                return None

            # Publish the container
            pub_resp = await client.post(
                f"{_GRAPH_API_BASE}/{ig_id}/media_publish",
                params={"access_token": token},
                data={"creation_id": container_id},
                timeout=_REQUEST_TIMEOUT,
            )
            pub_resp.raise_for_status()
            media_id = pub_resp.json().get("id")
            logger.info("Posted listing %s to Instagram: %s", listing.id, media_id)
            return media_id
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Instagram API error for listing %s: %s – %s",
                listing.id,
                exc.response.status_code,
                exc.response.text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error posting to Instagram: %s", exc)

    return None


# ---------------------------------------------------------------------------
# TikTok
# ---------------------------------------------------------------------------


async def post_to_tiktok(
    listing,
    agent_token: Optional[str] = None,
) -> Optional[str]:
    """
    Post a listing to TikTok.

    NOTE: TikTok's Content Posting API (v2) requires business-level approval
    and OAuth scopes that must be granted by TikTok support.  This implementation
    calls the direct-post video endpoint if a token is available, and logs a
    warning stub otherwise.

    Args:
        listing: ORM Listing object.
        agent_token: TikTok access token.

    Returns:
        TikTok publish_id on success, None on failure/stub.
    """
    token = _token(agent_token, "TIKTOK_ACCESS_TOKEN")

    if not token:
        # Stub: TikTok API requires special business approval
        logger.warning(
            "TikTok access token not configured. "
            "To enable TikTok posting, obtain a Content Posting API token from "
            "https://developers.tiktok.com/ and set TIKTOK_ACCESS_TOKEN in .env"
        )
        return None

    if not listing.video_file_id:
        logger.info("No video available for TikTok post of listing %s", listing.id)
        return None

    caption = (
        f"{listing.title} | {listing.location or ''} | {listing.price or ''} "
        f"#realestate #property #forsale #home"
    )

    # TikTok Content Posting API v2 – direct post (video URL required)
    # The video_file_id here is assumed to be a publicly accessible URL when
    # passed through the TikTok integration; Telegram file_ids need to be
    # downloaded and re-uploaded separately.
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                "https://open.tiktokapis.com/v2/post/publish/video/init/",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
                content=json.dumps(
                    {
                        "post_info": {
                            "title": caption[:150],
                            "privacy_level": "PUBLIC_TO_EVERYONE",
                            "disable_duet": False,
                            "disable_comment": False,
                            "disable_stitch": False,
                        },
                        "source_info": {
                            "source": "PULL_FROM_URL",
                            "video_url": listing.video_file_id,
                        },
                    }
                ),
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            publish_id = resp.json().get("data", {}).get("publish_id")
            logger.info("Posted listing %s to TikTok: %s", listing.id, publish_id)
            return publish_id
        except httpx.HTTPStatusError as exc:
            logger.error(
                "TikTok API error for listing %s: %s – %s",
                listing.id,
                exc.response.status_code,
                exc.response.text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error posting to TikTok: %s", exc)

    return None

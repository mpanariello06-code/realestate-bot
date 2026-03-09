"""
Social Media Poster
Posts property listings (photos/videos + caption) via Zapier, Go High Level's
Social Planner API, or the direct Facebook/Instagram Graph API (in that order
of preference).
"""
from __future__ import annotations

import logging
from pathlib import Path

import requests

import config
from services import ghl as ghl_service
from services import zapier as zapier_service

logger = logging.getLogger(__name__)

FACEBOOK_GRAPH_URL = "https://graph.facebook.com/v22.0"
LINKEDIN_API_URL = "https://api.linkedin.com/rest"


# ── Facebook ──────────────────────────────────────────────────────────────────

def post_to_facebook(caption: str, image_path: str | None = None) -> dict:
    """
    Post a photo with caption to the configured Facebook Page.

    Returns a dict with 'success' bool and 'post_id' or 'error'.
    """
    if not config.FACEBOOK_PAGE_ACCESS_TOKEN or not config.FACEBOOK_PAGE_ID:
        return {"success": False, "error": "Facebook credentials not configured"}

    try:
        if image_path and Path(image_path).exists():
            url = f"{FACEBOOK_GRAPH_URL}/{config.FACEBOOK_PAGE_ID}/photos"
            with open(image_path, "rb") as img:
                resp = requests.post(
                    url,
                    data={"caption": caption, "access_token": config.FACEBOOK_PAGE_ACCESS_TOKEN},
                    files={"source": img},
                    timeout=30,
                )
        else:
            url = f"{FACEBOOK_GRAPH_URL}/{config.FACEBOOK_PAGE_ID}/feed"
            resp = requests.post(
                url,
                json={"message": caption, "access_token": config.FACEBOOK_PAGE_ACCESS_TOKEN},
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
        post_id = data.get("post_id") or data.get("id", "")
        logger.info("Facebook post created: %s", post_id)
        return {"success": True, "post_id": post_id}
    except requests.RequestException as exc:
        logger.error("Facebook post failed: %s", exc)
        return {"success": False, "error": str(exc)}


# ── Instagram ─────────────────────────────────────────────────────────────────

def post_to_instagram(caption: str, image_url: str) -> dict:
    """
    Publish a photo to the configured Instagram Business Account.

    Instagram requires a publicly accessible *image_url* (not a local file).
    Use a CDN or temporary storage for uploaded images.
    """
    if not config.FACEBOOK_PAGE_ACCESS_TOKEN or not config.INSTAGRAM_ACCOUNT_ID:
        return {"success": False, "error": "Instagram credentials not configured"}

    try:
        # Step 1 – create media container
        container_url = (
            f"{FACEBOOK_GRAPH_URL}/{config.INSTAGRAM_ACCOUNT_ID}/media"
        )
        container_resp = requests.post(
            container_url,
            json={
                "image_url": image_url,
                "caption": caption,
                "access_token": config.FACEBOOK_PAGE_ACCESS_TOKEN,
            },
            timeout=30,
        )
        container_resp.raise_for_status()
        container_id = container_resp.json().get("id")

        # Step 2 – publish the container
        publish_url = (
            f"{FACEBOOK_GRAPH_URL}/{config.INSTAGRAM_ACCOUNT_ID}/media_publish"
        )
        publish_resp = requests.post(
            publish_url,
            json={
                "creation_id": container_id,
                "access_token": config.FACEBOOK_PAGE_ACCESS_TOKEN,
            },
            timeout=30,
        )
        publish_resp.raise_for_status()
        post_id = publish_resp.json().get("id", "")
        logger.info("Instagram post created: %s", post_id)
        return {"success": True, "post_id": post_id}
    except requests.RequestException as exc:
        logger.error("Instagram post failed: %s", exc)
        return {"success": False, "error": str(exc)}


# ── TikTok ────────────────────────────────────────────────────────────────────

def post_to_tiktok(caption: str, video_path: str) -> dict:
    """
    Upload a video to TikTok using the TikTok Content Posting API.

    Requires a valid ACCESS_TOKEN and OPEN_ID for the creator account.
    """
    if not config.TIKTOK_ACCESS_TOKEN or not config.TIKTOK_OPEN_ID:
        return {"success": False, "error": "TikTok credentials not configured"}

    if not Path(video_path).exists():
        return {"success": False, "error": f"Video file not found: {video_path}"}

    try:
        # Step 1 – initialise upload
        init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
        file_size = Path(video_path).stat().st_size
        init_resp = requests.post(
            init_url,
            headers={"Authorization": f"Bearer {config.TIKTOK_ACCESS_TOKEN}"},
            json={
                "post_info": {
                    "title": caption[:150],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": file_size,
                    "chunk_size": file_size,
                    "total_chunk_count": 1,
                },
            },
            timeout=30,
        )
        init_resp.raise_for_status()
        upload_url = init_resp.json()["data"]["upload_url"]
        publish_id = init_resp.json()["data"]["publish_id"]

        # Step 2 – upload binary
        with open(video_path, "rb") as vid:
            upload_resp = requests.put(
                upload_url,
                headers={
                    "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
                    "Content-Type": "video/mp4",
                },
                data=vid,
                timeout=120,
            )
        upload_resp.raise_for_status()
        logger.info("TikTok video uploaded, publish_id: %s", publish_id)
        return {"success": True, "publish_id": publish_id}
    except requests.RequestException as exc:
        logger.error("TikTok post failed: %s", exc)
        return {"success": False, "error": str(exc)}


# ── LinkedIn ──────────────────────────────────────────────────────────────────

def post_to_linkedin(caption: str, image_path: str | None = None) -> dict:
    """
    Publish a text or photo post to the configured LinkedIn profile / page.

    Uses the LinkedIn Posts API (version 202210).  Requires a valid
    ``LINKEDIN_ACCESS_TOKEN`` and a ``LINKEDIN_AUTHOR_URN`` such as
    ``urn:li:person:AbCdEfGhIj`` or ``urn:li:organization:123456``.

    When *image_path* is provided and the file exists, the image is uploaded
    via the LinkedIn Images initialise-upload flow before the post is created.
    """
    if not config.LINKEDIN_ACCESS_TOKEN or not config.LINKEDIN_AUTHOR_URN:
        return {"success": False, "error": "LinkedIn credentials not configured"}

    headers = {
        "Authorization": f"Bearer {config.LINKEDIN_ACCESS_TOKEN}",
        "LinkedIn-Version": "202210",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }

    try:
        image_urn: str | None = None
        if image_path and Path(image_path).exists():
            # Step 1 – initialise upload
            init_resp = requests.post(
                f"{LINKEDIN_API_URL}/images?action=initializeUpload",
                headers=headers,
                json={"initializeUploadRequest": {"owner": config.LINKEDIN_AUTHOR_URN}},
                timeout=30,
            )
            init_resp.raise_for_status()
            init_data = init_resp.json().get("value", {})
            upload_url = init_data.get("uploadUrl")
            image_urn = init_data.get("image")

            # Step 2 – upload binary
            with open(image_path, "rb") as img:
                upload_resp = requests.put(
                    upload_url,
                    headers={"Authorization": f"Bearer {config.LINKEDIN_ACCESS_TOKEN}"},
                    data=img,
                    timeout=60,
                )
            upload_resp.raise_for_status()

        # Step 3 – create the post
        post_body: dict = {
            "author": config.LINKEDIN_AUTHOR_URN,
            "commentary": caption,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        if image_urn:
            post_body["content"] = {"media": {"id": image_urn}}

        post_resp = requests.post(
            f"{LINKEDIN_API_URL}/posts",
            headers=headers,
            json=post_body,
            timeout=30,
        )
        post_resp.raise_for_status()
        # LinkedIn returns the post URN in the X-RestLi-Id response header
        post_id = post_resp.headers.get("x-restli-id", "")
        logger.info("LinkedIn post created: %s", post_id)
        return {"success": True, "post_id": post_id}
    except requests.RequestException as exc:
        logger.error("LinkedIn post failed: %s", exc)
        return {"success": False, "error": str(exc)}


# ── Convenience wrapper ───────────────────────────────────────────────────────

def post_listing(
    caption: str,
    image_path: str | None = None,
    image_url: str | None = None,
    video_path: str | None = None,
    listing: dict | None = None,
) -> dict[str, dict]:
    """
    Post a property listing to all configured social platforms.

    Priority order:
      1. Zapier webhook (when ZAPIER_WEBHOOK_URL is set) – sends the full
         structured listing JSON to your Zapier Zap which publishes to
         Facebook and Instagram.
      2. GHL Social Planner (when GHL_API_KEY + GHL_LOCATION_ID are set) –
         publishes via Go High Level.
      3. Direct Facebook / Instagram / LinkedIn Graph & REST APIs
         (always-available fallback).

    Parameters
    ----------
    caption    : AI-generated caption / description text.
    image_path : Local path to the image (used by the GHL / direct API paths).
    image_url  : Public image URL (used by the direct Instagram API path).
    video_path : Local path to a video (used by the GHL / direct API paths).
    listing    : Structured listing dict for the Zapier path.  Must contain
                 ``description``, ``price``, ``location``, ``bedrooms``,
                 ``bathrooms``, ``contact_phone``, and optionally ``image_url``.

    Returns a dict mapping platform name → result dict.
    """
    # ── Zapier path (preferred) ───────────────────────────────────────────────
    if zapier_service.is_configured():
        payload = listing or {"description": caption}
        result = zapier_service.post_listing(payload)
        return {"zapier": result}

    # ── GHL Social Planner path ───────────────────────────────────────────────
    if ghl_service.is_configured():
        media = image_path or video_path
        result = ghl_service.post_to_social_planner(caption, media)
        return {"ghl": result}

    # ── Direct API fallback ────────────────────────────────────────────────────
    results: dict[str, dict] = {}

    results["facebook"] = post_to_facebook(caption, image_path)

    if image_url:
        results["instagram"] = post_to_instagram(caption, image_url)
    else:
        results["instagram"] = {"success": False, "error": "image_url required for Instagram"}

    results["linkedin"] = post_to_linkedin(caption, image_path)

    return results

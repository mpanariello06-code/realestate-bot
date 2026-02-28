import json
import logging
from typing import Optional

import requests

from app.config import settings

logger = logging.getLogger(__name__)


def post_to_facebook(listing, agent, access_token: str) -> Optional[str]:
    """Post listing to a Facebook Page. Returns post_id or None on failure."""
    if not access_token:
        logger.warning("No Facebook access token for agent %s", agent.id)
        return None

    # Resolve the page ID and page-level access token from the user token
    try:
        accounts_resp = requests.get(
            "https://graph.facebook.com/v18.0/me/accounts",
            params={"access_token": access_token},
            timeout=15,
        )
        accounts_resp.raise_for_status()
        pages = accounts_resp.json().get("data", [])
        if not pages:
            logger.warning("No Facebook pages found for agent %s", agent.id)
            return None
        page = pages[0]
        page_id = page["id"]
        page_token = page["access_token"]
    except Exception as exc:
        logger.error("Failed to fetch Facebook pages: %s", exc)
        return None

    media_urls: list = json.loads(listing.media_urls or "[]")
    caption = _build_caption(listing)

    try:
        if media_urls:
            photo_url = media_urls[0]
            resp = requests.post(
                f"https://graph.facebook.com/v18.0/{page_id}/photos",
                data={
                    "url": photo_url,
                    "caption": caption,
                    "access_token": page_token,
                },
                timeout=30,
            )
        else:
            resp = requests.post(
                f"https://graph.facebook.com/v18.0/{page_id}/feed",
                data={"message": caption, "access_token": page_token},
                timeout=30,
            )
        resp.raise_for_status()
        post_id = resp.json().get("id") or resp.json().get("post_id")
        logger.info("Facebook post created: %s", post_id)
        return str(post_id) if post_id else None
    except Exception as exc:
        logger.error("Failed to post to Facebook: %s", exc)
        return None


def post_to_instagram(listing, agent, access_token: str) -> Optional[str]:
    """Post listing to Instagram Business account via container→publish flow."""
    if not access_token:
        logger.warning("No Instagram access token for agent %s", agent.id)
        return None

    media_urls: list = json.loads(listing.media_urls or "[]")
    caption = _build_caption(listing)

    try:
        # Step 1: resolve IG business account ID
        ig_resp = requests.get(
            "https://graph.facebook.com/v18.0/me",
            params={"fields": "instagram_business_account", "access_token": access_token},
            timeout=15,
        )
        ig_resp.raise_for_status()
        ig_account = ig_resp.json().get("instagram_business_account", {})
        ig_id = ig_account.get("id")
        if not ig_id:
            logger.warning("No Instagram business account linked for agent %s", agent.id)
            return None

        # Step 2: create media container
        container_params: dict = {"caption": caption, "access_token": access_token}
        if media_urls:
            container_params["image_url"] = media_urls[0]
        else:
            container_params["image_url"] = ""

        container_resp = requests.post(
            f"https://graph.facebook.com/v18.0/{ig_id}/media",
            data=container_params,
            timeout=30,
        )
        container_resp.raise_for_status()
        container_id = container_resp.json().get("id")

        # Step 3: publish the container
        publish_resp = requests.post(
            f"https://graph.facebook.com/v18.0/{ig_id}/media_publish",
            data={"creation_id": container_id, "access_token": access_token},
            timeout=30,
        )
        publish_resp.raise_for_status()
        media_id = publish_resp.json().get("id")
        logger.info("Instagram post created: %s", media_id)
        return str(media_id) if media_id else None
    except Exception as exc:
        logger.error("Failed to post to Instagram: %s", exc)
        return None


def post_to_tiktok(listing, agent, access_token: str) -> Optional[str]:
    """Post listing video to TikTok. Returns post_id or None on failure."""
    if not access_token:
        logger.warning("No TikTok access token for agent %s", agent.id)
        return None

    media_urls: list = json.loads(listing.media_urls or "[]")
    if not media_urls:
        logger.warning("No media to post to TikTok for listing %s", listing.id)
        return None

    video_url = media_urls[0]
    title = _build_caption(listing)[:150]  # TikTok title limit

    try:
        resp = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={
                "post_info": {"title": title, "privacy_level": "PUBLIC_TO_EVERYONE"},
                "source_info": {"source": "PULL_FROM_URL", "video_url": video_url},
            },
            timeout=30,
        )
        resp.raise_for_status()
        publish_id = resp.json().get("data", {}).get("publish_id")
        logger.info("TikTok post initiated: %s", publish_id)
        return str(publish_id) if publish_id else None
    except Exception as exc:
        logger.error("Failed to post to TikTok: %s", exc)
        return None


def post_listing_to_all_platforms(listing, agent, db) -> dict:
    """Post listing to all connected platforms and update the listing record."""
    results: dict = {}
    posted_platforms: list = json.loads(listing.posted_platforms or "[]")

    if agent.facebook_token:
        post_id = post_to_facebook(listing, agent, agent.facebook_token)
        if post_id:
            listing.facebook_post_id = post_id
            if "facebook" not in posted_platforms:
                posted_platforms.append("facebook")
            results["facebook"] = post_id
        else:
            results["facebook"] = "error"

    if agent.instagram_token:
        post_id = post_to_instagram(listing, agent, agent.instagram_token)
        if post_id:
            listing.instagram_post_id = post_id
            if "instagram" not in posted_platforms:
                posted_platforms.append("instagram")
            results["instagram"] = post_id
        else:
            results["instagram"] = "error"

    if agent.tiktok_token:
        post_id = post_to_tiktok(listing, agent, agent.tiktok_token)
        if post_id:
            listing.tiktok_post_id = post_id
            if "tiktok" not in posted_platforms:
                posted_platforms.append("tiktok")
            results["tiktok"] = post_id
        else:
            results["tiktok"] = "error"

    listing.posted_platforms = json.dumps(posted_platforms)
    db.commit()
    db.refresh(listing)
    return results


def _build_caption(listing) -> str:
    parts = [f"🏠 {listing.address}", f"💰 ${listing.price:,.0f}"]
    if listing.bedrooms:
        parts.append(f"🛏 {listing.bedrooms} bed")
    if listing.bathrooms:
        parts.append(f"🛁 {listing.bathrooms} bath")
    parts.append(f"\n{listing.description}")
    parts.append("\n#RealEstate #HomeForSale #Property")
    return " | ".join(parts[:4]) + "\n" + "\n".join(parts[4:])

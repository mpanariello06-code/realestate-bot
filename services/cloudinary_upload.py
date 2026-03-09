"""
Cloudinary Image Upload Service

Uploads a local image file to Cloudinary and returns the public URL.
The public URL is required by Zapier so Instagram / Facebook can fetch
the photo when publishing the post.

Required .env variables
──────────────────────
CLOUDINARY_CLOUD_NAME  – Your cloud name from the Cloudinary dashboard.
CLOUDINARY_API_KEY     – API Key from Cloudinary → Settings → Access Keys.
CLOUDINARY_API_SECRET  – API Secret from Cloudinary → Settings → Access Keys.
"""
from __future__ import annotations

import logging
from typing import Optional

try:
    import cloudinary
    import cloudinary.uploader
    _CLOUDINARY_AVAILABLE = True
except ImportError:
    cloudinary = None  # type: ignore[assignment]
    _CLOUDINARY_AVAILABLE = False

import config

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """Return True when all three Cloudinary credentials are set in config."""
    return bool(
        config.CLOUDINARY_CLOUD_NAME
        and config.CLOUDINARY_API_KEY
        and config.CLOUDINARY_API_SECRET
    )


def _configure() -> None:
    """Apply Cloudinary credentials from config (called lazily before upload)."""
    if not _CLOUDINARY_AVAILABLE:
        return
    cloudinary.config(
        cloud_name=config.CLOUDINARY_CLOUD_NAME,
        api_key=config.CLOUDINARY_API_KEY,
        api_secret=config.CLOUDINARY_API_SECRET,
        secure=True,
    )


def upload_image(file_path: str) -> Optional[str]:
    """
    Upload *file_path* to Cloudinary and return the secure public URL.

    Returns the ``https://res.cloudinary.com/…`` URL on success,
    or ``None`` if Cloudinary is not configured or the upload fails.
    """
    if not _CLOUDINARY_AVAILABLE:
        logger.warning("cloudinary package is not installed – skipping upload.")
        return None
    if not is_configured():
        logger.warning("Cloudinary credentials not configured – skipping upload.")
        return None

    _configure()
    try:
        result = cloudinary.uploader.upload(
            file_path,
            folder="realestate-bot",
            resource_type="image",
        )
        url = result.get("secure_url") or result.get("url", "")
        logger.info("Cloudinary upload succeeded: %s", url)
        return url if url else None
    except Exception as exc:
        logger.error("Cloudinary upload failed: %s", exc)
        return None

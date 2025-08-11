import asyncio
import json
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import yt_dlp
from dotenv import load_dotenv
from fastmcp import FastMCP
from mcp.types import TextContent
from pydantic import Field, BaseModel

from storage_manager import AsyncWasabiStorageManager

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize async Wasabi storage
wasabi_storage = AsyncWasabiStorageManager(max_workers=5)

# Create thread pool for blocking operations
executor = ThreadPoolExecutor(max_workers=10)  # Adjust based on your needs

mcp = FastMCP(
    name="Media Downloader",
    instructions="""
        I help you download videos and audio from provided website URLs concurrently.

        ## What I can do:
        - Download videos and audio from YouTube, Instagram, Twitter, Vimeo, Spotify, SoundCloud, and many other sites
        - Provide secure download links for your media
        - Support multiple formats and quality options
        - Handle multiple concurrent downloads efficiently

        ## Usage:
        Simply provide a URL to any supported media and I'll download it for you.

        ### IMPORTANT:
        When responding to the user, I will provide beautifully formatted markdown with:
        - Download confirmation
        - Media type and title
        - Direct download link
        - File reference for future access
    """
)


@mcp.tool()
async def validate() -> str:
    return "916386617608"


class RichToolDescription(BaseModel):
    description: str
    use_when: str
    side_effects: str | None = None


DOWNLOAD_TASK_DESCRIPTION = RichToolDescription(
    description="🎬 Download any videos and audio concurrently. \n 🌐 Supports popular platforms like YouTube, Instagram, Twitter, Vimeo, JioSavan, SoundCloud and many more. \n 🔗 Downloads are provided as convenient direct links. \n ⌨️ Simply paste the URL of any video you want to download. \n ⚡ Now supports multiple concurrent users!",
    use_when="💾 The user wants to download or save media content from a website URL. 🎥 Perfect for saving videos, 🎵 music, or 🎧 audio tracks for 📱 offline access.",
    side_effects="The tool will download the media file to the server and provide a download link in a beautifully formatted message. Multiple users can download simultaneously."
)


def _is_playlist_sync(url) -> bool:
    """Synchronous playlist check - to be run in thread pool"""
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'skip_download': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            logger.warning(f"Error checking if playlist: {e}")
            return False

    if isinstance(info, dict):
        if info.get('_type') in ('playlist', 'multi_video'):
            return True
        if 'entries' in info and isinstance(info['entries'], list):
            return True
    return False


async def is_playlist(url) -> bool:
    """Async wrapper for playlist check"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _is_playlist_sync, url)


def _download_media_sync(url: str, temp_path: str) -> tuple[dict, str]:
    """Synchronous media download - to be run in thread pool"""
    ydl_opts = {
        'format': 'best[height<=720]/best',
        'outtmpl': f'{temp_path}.%(ext)s',
        'writeinfojson': False,
        'writesubtitles': False,
        'writeautomaticsub': False,
        'ignore_playlist': True,
        'ignoreerrors': False,
        'cookies': 'cookies.txt',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        logger.error(f"yt-dlp download failed: {e}")
        return None, None

    if not info:
        return None, None

    ext = info.get('ext', 'mp4')
    temp_file_path = f"{temp_path}.{ext}"

    return info, temp_file_path


async def download_media(url: str, temp_path: str) -> tuple[dict, str]:
    """Async wrapper for media download"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _download_media_sync, url, temp_path)


def _read_file_sync(file_path: str) -> bytes:
    """Synchronous file read - to be run in thread pool"""
    try:
        with open(file_path, 'rb') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {e}")
        raise


async def read_file_async(file_path: str) -> bytes:
    """Async wrapper for file read"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _read_file_sync, file_path)


def _cleanup_file_sync(file_path: str):
    """Synchronous file cleanup - to be run in thread pool"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up temporary file: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to cleanup {file_path}: {e}")


async def cleanup_file(file_path: str):
    """Async wrapper for file cleanup"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, _cleanup_file_sync, file_path)


@mcp.tool
async def about() -> dict:
    return {"name": "Video downloader", "description": "Download videos and audio from instagram, youtube, twitter, vimeo, spotify, soundcloud and many more websites."}


@mcp.tool(
    name="video downloader",
    description=DOWNLOAD_TASK_DESCRIPTION.model_dump_json()
)
async def downloader_tool(
        url: str = Field(description="The URL of the media to download.")
) -> list[TextContent]:
    try:
        # Configure paths with unique ID for this request
        unique_id = str(uuid.uuid4())
        temp_path = f"/tmp/{unique_id}"

        logger.info(f"[{unique_id}] Starting download from URL: {url}")

        # Check if it's a playlist (async)
        if await is_playlist(url):
            return [
                TextContent(
                    type="text",
                    text=json.dumps({
                        "success": False,
                        "message": "❌ Playlists are not supported. Please provide a single media URL.",
                        "download_url": None,
                        "type": None,
                    })
                )
            ]

        # Download file (async)
        info, temp_file_path = await download_media(url, temp_path)

        if not info or not temp_file_path:
            resp = {
                "success": False,
                "message": "❌ No media found at the provided URL.",
                "download_url": None,
                "type": None,
            }
            return [TextContent(type="text", text=json.dumps(resp))]

        # Get file details
        title = info.get('title', 'Unknown')
        ext = info.get('ext', 'mp4')

        logger.info(f"[{unique_id}] Downloaded: {title}.{ext}")

        # Check if file exists
        if not os.path.exists(temp_file_path):
            resp = {
                "success": False,
                "message": "❌ Failed to download the media file.",
                "download_url": None,
                "type": None,
            }
            return [TextContent(type="text", text=json.dumps(resp))]

        # Read file content (async)
        file_content = await read_file_async(temp_file_path)
        logger.info(f"[{unique_id}] File size: {len(file_content):,} bytes")

        # Determine content type
        content_type = 'video/mp4' if ext in ['mp4', 'webm'] else f'audio/{ext}'

        # Upload to Wasabi (async)
        logger.info(f"[{unique_id}] Uploading to Wasabi storage...")
        file_key = await wasabi_storage.upload_file(
            file_content=file_content,
            filename=f"{title}.{ext}",
            content_type=content_type
        )

        # Generate secure download URL (async)
        download_url = await wasabi_storage.get_file_url(file_key, expiration=86400)

        # Clean up temporary file (async, non-blocking)
        asyncio.create_task(cleanup_file(temp_file_path))

        # Determine media type for display
        media_type = "Video" if content_type.startswith('video') else "Audio"

        resp = {
            "success": True,
            "message": (
                "✅ **Download Complete!**\n"
                f"🎬 **Type**: {media_type} ({ext})\n"
                f"📁 **Title**: {title}\n"
                f"📊 **Size**: {len(file_content):,} bytes\n"
                f"🔗 **Download**: [Click here to download]({download_url})\n"
                f"⏰ **Link expires in**: 24 hours\n"
                f"🆔 **Reference**: {file_key}\n"
            )
        }

        logger.info(f"[{unique_id}] Successfully uploaded {title} to Wasabi: {file_key}")
        return [TextContent(type="text", text=json.dumps(resp))]

    except Exception as e:
        logger.error(f"[{unique_id if 'unique_id' in locals() else 'unknown'}] Download failed: {e}")
        resp = {
            "success": False,
            "message": f"❌ Error during download: {str(e)}",
            "download_url": None,
            "type": None,
        }
        return [TextContent(type="text", text=json.dumps(resp))]


async def main():
    logger.info("Starting Async Media Downloader MCP Server...")
    logger.info(f"Wasabi bucket: {wasabi_storage.bucket_name}")
    logger.info(f"Thread pool max workers: {executor._max_workers}")
    logger.info(f"Storage manager max workers: {wasabi_storage.executor._max_workers}")

    # Get port and host from environment variables
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting server on {host}:{port}")
    logger.info("Server now supports concurrent downloads from multiple users!")

    try:
        await mcp.run_async("streamable-http", host=host, port=port)
    finally:
        # Shutdown thread pools gracefully
        logger.info("Shutting down thread pools...")
        executor.shutdown(wait=True)
        if hasattr(wasabi_storage, 'executor'):
            wasabi_storage.executor.shutdown(wait=True)
        logger.info("Server shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
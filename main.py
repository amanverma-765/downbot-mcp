import asyncio
import json
import os
import uuid
import logging
import yt_dlp
from dotenv import load_dotenv
from fastmcp import FastMCP
from mcp.types import TextContent
from pydantic import Field, BaseModel

from storage_manager import WasabiStorageManager

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Wasabi storage
wasabi_storage = WasabiStorageManager()

mcp = FastMCP(
    name="Media Downloader",
    instructions="""
        I help you download videos and audio from provided website URLs.

        ## What I can do:
        - Download videos and audio from YouTube, Instagram, Twitter, Vimeo, Spotify, SoundCloud, and many other sites
        - Provide secure download links for your media
        - Support multiple formats and quality options

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
    description="🎬 Download any videos and audio. \n 🌐 Supports popular platforms like YouTube, Instagram, Twitter, Vimeo, Spotify, SoundCloud and many more. \n 🔗 Downloads are provided as convenient direct links. \n ⌨️ Simply paste the URL of any video you want to download.",
    use_when="💾 The user wants to download or save media content from a website URL. 🎥 Perfect for saving videos, 🎵 music, or 🎧 audio tracks for 📱 offline access.",
    side_effects="The tool will download the media file to the server and provide a download link in a beautifully formatted message"
)


@mcp.tool(
    name="video downloader",
    description=DOWNLOAD_TASK_DESCRIPTION.model_dump_json()
)
async def downloader_tool(
        url: str = Field(description="The URL of the media to download.")
) -> list[TextContent]:

    try:
        # Configure yt-dlp for temporary download
        unique_id = str(uuid.uuid4())
        temp_path = f"/tmp/{unique_id}"

        ydl_opts = {
            'format': 'best[height<=720]/best',
            'outtmpl': f'{temp_path}.%(ext)s',
            'writeinfojson': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'noplaylist': True,
            'ignoreerrors': False,
        }

        logger.info(f"Starting download from URL: {url}")

        # Download file temporarily
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        if not info:
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
        temp_file_path = f"{temp_path}.{ext}"

        logger.info(f"Downloaded: {title}.{ext}")

        # Check if file was downloaded
        if not os.path.exists(temp_file_path):
            resp = {
                "success": False,
                "message": "❌ Failed to download the media file.",
                "download_url": None,
                "type": None,
            }
            return [TextContent(type="text", text=json.dumps(resp))]

        # Read file content
        with open(temp_file_path, 'rb') as f:
            file_content = f.read()

        logger.info(f"File size: {len(file_content)} bytes")

        # Determine content type
        content_type = 'video/mp4' if ext in ['mp4', 'webm'] else f'audio/{ext}'

        # Upload to Wasabi
        logger.info("Uploading to Wasabi storage...")
        file_key = wasabi_storage.upload_file(
            file_content=file_content,
            filename=f"{title}.{ext}",
            content_type=content_type
        )

        # Generate secure download URL (24 hours expiration)
        download_url = wasabi_storage.get_file_url(file_key, expiration=86400)

        # Clean up temporary file
        os.remove(temp_file_path)
        logger.info(f"Cleaned up temporary file: {temp_file_path}")

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
            )
        }

        logger.info(f"Successfully uploaded {title} to Wasabi: {file_key}")
        return [TextContent(type="text", text=json.dumps(resp))]

    except Exception as e:
        logger.error(f"Download failed: {e}")
        resp = {
            "success": False,
            "message": f"❌ Error during download: {str(e)}",
            "download_url": None,
            "type": None,
        }
        return [TextContent(type="text", text=json.dumps(resp))]

async def main():
    logger.info("Starting Media Downloader MCP Server...")
    logger.info(f"Wasabi bucket: {wasabi_storage.bucket_name}")
    await mcp.run_async("streamable-http", host="0.0.0.0", port=8000)

if __name__ == "__main__":
    asyncio.run(main())

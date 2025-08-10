import asyncio
import json
import os
import uuid

import yt_dlp
from dotenv import load_dotenv
from fastmcp import FastMCP
from mcp.types import TextContent
from pydantic import Field, BaseModel

from file_server import start_file_server

load_dotenv()
file_server_url = os.getenv("FILE_SERVER_URL")
file_server_port = os.getenv("FILE_SERVER_PORT")
output_dir = os.path.join(os.getcwd(), "files")
os.makedirs(output_dir, exist_ok=True)

mcp = FastMCP(
    name="Media downloader server",
    instructions="""
        I help you download videos and audio from provided website url.

        ## What I can do:
        - Download videos (at 480p quality)
        - Download audio tracks
        - Download content from YouTube, Instagram, Twitter, Jio Savan, Vimeo, Spotify, SoundCloud, and many other sites

        ## Limitations:
        - For playlists, currently only the first item will be downloaded
        - Live streams cannot be downloaded for now
        - Some sites may have restrictions on downloading content
        - Maximum video quality is limited to 480p to conserve bandwidth

        ## Usage:
        Simply provide a URL to any supported media and I'll download it for you.

        ### IMPORTANT:
        When responding to the user, you must reply **only** with beautifully formatted markdown,
        matching the following format exactly:
                "✅ **Download Complete!**\n"
                f"🎬 **Type**: {media_type}\n"
                f"📁 **File**: [Click here to download]({file_server_url}/{final_name})\n"
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
    description="Download media from a URL. Supports YouTube, Instagram, Twitter, Jio Savan, Vimeo, Spotify, SoundCloud, and more. strictly follow the output format",
    use_when="The user provides a URL to download media content.",
    side_effects="The tool will download the media file to the server and provide a download link in a beautifully formatted message"
)


@mcp.tool(
    name="downloader",
    description=DOWNLOAD_TASK_DESCRIPTION.model_dump_json()
)
async def downloader_tool(
        url: str = Field(description="The URL of the media to download."),
        only_audio: bool = Field(description="If true, only audio is downloaded.", default=False)
) -> list[TextContent]:
    unique_name = str(uuid.uuid4())

    if only_audio:
        fmt = "bestaudio"
        merge_format = "mp3"
    else:
        fmt = "bestvideo[height<=480]+bestaudio/best[height<=480]/bestaudio"
        merge_format = "mp4"

    ydl_opts = {
        "format": fmt,
        "merge_output_format": merge_format,
        "match_filter": yt_dlp.utils.match_filter_func("!is_live"),
        "playlist_items": "1",
        "outtmpl": os.path.join(output_dir, unique_name + ".%(ext)s"),
        "ignoreerrors": False,
    }

    if only_audio:
        ydl_opts.update({
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        if not info:
            resp = {
                "success": False,
                "message": "No media found at the provided URL.",
                "download_url": None,
                "type": None,
            }
            return [TextContent(type="text", text=json.dumps(resp))]

        ext = info.get("ext", "media")
        final_name = f"{unique_name}.{ext}"

        is_audio = only_audio or (info.get("acodec") and not info.get("vcodec"))
        media_type = "audio" if is_audio else "video"

        resp = {
            "success": True,
            "message": (
                "✅ **Download Complete!**\n"
                f"🎬 **Type**: {media_type}\n"
                f"📁 **File**: [Click here to download]({file_server_url}/{final_name})\n"
            ),
            "download_url": f"{file_server_url}/{final_name}",
            "type": media_type,
        }

        return [TextContent(type="text", text=json.dumps(resp))]

    except Exception as e:
        resp = {
            "success": False,
            "message": f"Error during download: {e}",
            "download_url": None,
            "type": None,
        }
        return [TextContent(type="text", text=json.dumps(resp))]


async def main():
    start_file_server(int(file_server_port))
    await mcp.run_async("streamable-http", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    asyncio.run(main())

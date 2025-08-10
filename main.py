import os
import uuid
import yt_dlp
from dotenv import load_dotenv
from fastmcp import FastMCP
from pydantic import Field
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

load_dotenv()
file_server_url = os.getenv("FILE_SERVER_URL", "http://localhost:7676/files")
output_dir = os.path.join(os.getcwd(), "files")
os.makedirs(output_dir, exist_ok=True)

mcp = FastMCP(
    name="DownBot",
    instructions="""
        # DownBot - Media Downloader

        I help you download videos and audio from many popular websites.

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
    """
)


@mcp.tool()
async def validate() -> str:
    return "916386617608"


@mcp.prompt(
    name="downloader",
    description="Download media from a URL. Supports YouTube, Instagram, Twitter, Jio Savan, Vimeo, Spotify, SoundCloud, and more.",
    tags={"media", "download", "video", "audio"}
)
async def downloader_tool(
        url: str = Field(description="The URL of the media to download."),
        only_audio: bool = Field(description="If true, only audio is downloaded.", default=False)
) -> dict:
    # Create a unique base filename
    unique_name = str(uuid.uuid4())

    # Format selection based on onlyAudio parameter
    if only_audio:
        fmt = "bestaudio"
        merge_format = "mp3"
    else:
        # Format selection: video at ≤480p + the best audio; fallback to audio-only for non-video URLs
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

    # Add audio extraction post-processor if onlyAudio is True
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
            return {"success": False, "message": "Failed to download video file."}

        ext = info.get("ext", "media")
        final_name = f"{unique_name}.{ext}"

        return {
            "success": True,
            "message": "Download completed successfully, you can access the file via the provided URL.",
            "download_url": f"{file_server_url}/{final_name}",
            "type": "audio" if only_audio or (info.get("acodec") and not info.get("vcodec")) else "video"
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Error during download: {e}"
        }


def start_file_server():
    class FilesHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=output_dir, **kwargs)

    server_address = ("", 7676)
    httpd = ThreadingHTTPServer(server_address, FilesHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


if __name__ == "__main__":
    start_file_server()
    mcp.run(transport="http", port=7070)
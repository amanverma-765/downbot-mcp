<div align="center">

# ✨ **Downbot MCP** ✨

<img src="https://img.shields.io/badge/Status-Active-green" alt="Status"/>
<img src="https://img.shields.io/badge/Language-Kotlin-blue" alt="Kotlin"/>
<img src="https://img.shields.io/badge/Protocol-MCP-yellow" alt="MCP Protocol"/>

<br/><br/>

🚀 **Your ultimate MCP server for seamless video downloads with Puch.ai!**  
🎥 Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp) to download reels, shorts & videos effortlessly.

</div>

---

## Overview

**downbot-mcp** is a high-performance MCP server built for the Puch.ai hackathon. It connects directly with the Puch AI WhatsApp bot using the MCP protocol, enabling users to request and instantly download reels, shorts, videos, and more from multiple platforms — all handled by `yt-dlp`.

---

## Features

* 🔗 **Full MCP Protocol integration** for smooth interaction with Puch AI bots
* 🎞️ **Supports downloading videos, reels, and shorts** from popular platforms
* ⚡ **Fast, reliable, and scalable** download pipeline
* 🛠️ **Simple to deploy, extend, and customize** for your needs

---

## Command Reference

| Command                             | Description                                                                                                                                               | Example                                                |          |                                                  |                                |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ | -------- | ------------------------------------------------ | ------------------------------ |
| `/mcp connect <url> <bearer_token>` | Connect your MCP server with Puch AI using a bearer token. Your server must validate the token and return the user's phone number (e.g., `919876543210`). | `/mcp connect https://mcp.example.com/mcp abc123token` |          |                                                  |                                |
| `/mcp connect <url>`                | Connect using OAuth authentication. A browser window may open for user consent.                                                                           | `/mcp connect https://mcp.example.com/mcp`             |          |                                                  |                                |
| `/mcp use <server_id>`              | Connect to a hosted MCP server by its unique ID. You can connect up to 5 servers at once.                                                                 | `/mcp use abc123`                                      |          |                                                  |                                |
| `/mcp remove <server_id>`           | Remove a hosted MCP server from your list.                                                                                                                | `/mcp remove abc123`                                   |          |                                                  |                                |
| `/mcp list`                         | List all your connected MCP servers and configurations.                                                                                                   | `/mcp list`                                            |          |                                                  |                                |
| `/mcp deactivate`                   | Disconnect safely from all active MCP servers, revoking access to their tools.                                                                            | `/mcp deactivate`                                      |          |                                                  |                                |
| \`/mcp diagnostics-level (error     | warn                                                                                                                                                      | info                                                   | debug)\` | Set the diagnostic log level for MCP operations. | `/mcp diagnostics-level debug` |
| `/mcp disable <server_id>`          | Disable a specific MCP server (tools become unavailable, but connection remains). Useful for debugging.                                                   | `/mcp disable abc123`                                  |          |                                                  |                                |
| `/mcp enable <server_id>`           | Enable a previously disabled MCP server.                                                                                                                  | `/mcp enable abc123`                                   |          |                                                  |                                |

> **Note:** The validate tool on your MCP server **must** accept the bearer token and return the user's phone number (including country code) for authentication to succeed.

---

## Installation & Usage

```bash
git clone https://github.com/amanverma-765/downbot-mcp.git
cd downbot-mcp
```

Build and run your MCP server following the included instructions.

> Ensure all `yt-dlp` dependencies and runtime requirements are installed for smooth operation.

---

## Contribution

Contributions and suggestions are warmly welcome! Please open an issue or pull request to help improve the project.

---

## Acknowledgments

* Huge thanks to the Puch.ai hackathon organizers for this amazing opportunity!
* Special mention to the creators of [yt-dlp](https://github.com/yt-dlp/yt-dlp), the backbone of this downloader.

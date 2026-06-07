"""PlexLink V2 — Discord Bot (Doplarr-Style Request Manager)

Handles:
- /request <title>   → Search Overseerr or direct search
- /status            → Show qBittorrent + server status
- /torrents          → List active torrents
- /library           → Show Plex library stats (via Tautulli if configured)
- Webhook push notifications from PlexLink server

Usage:
    export DISCORD_BOT_TOKEN=your_token
    export PLEXLINK_SERVER=http://localhost:8080
    python bot.py
"""
import os
import sys
import asyncio
import aiohttp
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

PLEXLINK_SERVER = os.getenv("PLEXLINK_SERVER", "http://localhost:8080")
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", "60"))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


async def fetch(endpoint: str, method: str = "GET", data: dict = None) -> dict:
    async with aiohttp.ClientSession() as session:
        url = f"{PLEXLINK_SERVER}{endpoint}"
        if method == "GET":
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.json() if r.status == 200 else {}
        else:
            async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.json() if r.status in (200, 201) else {}


def embed_status(data: dict) -> discord.Embed:
    em = discord.Embed(title="📊 PlexLink Status", color=0x00d4aa, timestamp=datetime.utcnow())
    em.add_field(name="Version", value=data.get("version", "?"), inline=True)
    em.add_field(name="Status", value="ONLINE" if data.get("status") == "ok" else "OFFLINE", inline=True)
    em.add_field(name="Server", value=PLEXLINK_SERVER, inline=False)
    em.set_footer(text="PlexLink V2")
    return em


def embed_torrents(torrents: list) -> discord.Embed:
    em = discord.Embed(title="🔄 Active Torrents", color=0x00b4d8, timestamp=datetime.utcnow())
    if not torrents:
        em.description = "No active torrents."
        return em
    lines = []
    for t in torrents[:10]:
        bar = "█" * int(t.get("progress", 0) / 10) + "░" * (10 - int(t.get("progress", 0) / 10))
        lines.append(f"{bar} `{t.get('name', '?')[:40]}` **{t.get('progress', 0)}%**")
    em.description = "\n".join(lines)
    em.set_footer(text=f"{len(torrents)} total torrents")
    return em


@bot.event
async def on_ready():
    print(f"[DiscordBot] Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"[DiscordBot] Synced {len(synced)} commands.")
    except Exception as e:
        print(f"[DiscordBot] Sync error: {e}")
    if UPDATE_INTERVAL > 0:
        status_loop.start()


@bot.tree.command(name="status", description="Show PlexLink server status")
async def slash_status(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch("/health")
    await interaction.followup.send(embed=embed_status(data))


@bot.tree.command(name="torrents", description="Show active torrents")
async def slash_torrents(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch("/api/torrents")
    await interaction.followup.send(embed=embed_torrents(data))


@bot.tree.command(name="request", description="Request a movie or TV show")
@app_commands.describe(title="Title to search", media_type="Movie or TV")
@app_commands.choices(media_type=[
    app_commands.Choice(name="Movie", value="movie"),
    app_commands.Choice(name="TV Show", value="tv"),
    app_commands.Choice(name="Anime", value="anime"),
])
async def slash_request(interaction: discord.Interaction, title: str, media_type: str = "movie"):
    await interaction.response.defer()
    # Search metadata
    meta = await fetch(f"/api/metadata/search?q={title}&type={media_type}")
    em = discord.Embed(title=f"🔎 Request: {title}", color=0xffaa00, timestamp=datetime.utcnow())

    results = []
    if media_type == "movie" and meta.get("tmdb_movies"):
        results = meta["tmdb_movies"]
        for r in results[:5]:
            em.add_field(
                name=r.get("title", "?") + (f" ({r.get('release_date','')[:4]})" if r.get("release_date") else ""),
                value=f"⭐ {r.get('vote_average', '?')}/10 | {r.get('overview', '')[:100]}...",
                inline=False,
            )
    elif media_type == "tv" and meta.get("tmdb_tv"):
        results = meta["tmdb_tv"]
        for r in results[:5]:
            em.add_field(
                name=r.get("name", "?") + (f" ({r.get('first_air_date','')[:4]})" if r.get("first_air_date") else ""),
                value=f"⭐ {r.get('vote_average', '?')}/10 | {r.get('overview', '')[:100]}...",
                inline=False,
            )
    elif media_type == "anime" and meta.get("jikan_anime"):
        results = meta["jikan_anime"]
        for r in results[:5]:
            em.add_field(
                name=r.get("title", "?") + (f" [{r.get('type','')}]" if r.get("type") else ""),
                value=f"★ {r.get('score', '?')} | {r.get('synopsis', '')[:100]}...",
                inline=False,
            )
    else:
        em.description = "No metadata found."

    if not results:
        em.description = "No results found."
    else:
        em.set_footer(text="React with ✅ to auto-search torrents")

    await interaction.followup.send(embed=em)


@bot.tree.command(name="search", description="Search torrents directly")
@app_commands.describe(query="Search query", provider="Torrent provider (optional)")
async def slash_search(interaction: discord.Interaction, query: str, provider: str = ""):
    await interaction.response.defer()
    url = f"/api/search?q={query}"
    if provider:
        url += f"&provider={provider}"
    data = await fetch(url)
    results = data.get("results", [])

    em = discord.Embed(title=f"⌕ Torrents: {query}", color=0x00d4aa, timestamp=datetime.utcnow())
    if not results:
        em.description = "No torrents found."
    else:
        lines = []
        for r in results[:15]:
            line = f"▲ {r.get('seeders', 0)} ▼ {r.get('leechers', 0)} | `{r.get('title', '?')[:50]}` | {r.get('size', '?')}"
            lines.append(line)
        em.description = "\n".join(lines)
        em.set_footer(text=f"{len(results)} results from {provider or 'all providers'}")
    await interaction.followup.send(embed=em)


@bot.tree.command(name="library", description="Show Plex library stats via Tautulli")
async def slash_library(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch("/api/tautulli/activity")
    em = discord.Embed(title="📚 Library Activity", color=0x00b4d8, timestamp=datetime.utcnow())
    if data.get("enabled") is False:
        em.description = "Tautulli is not enabled in PlexLink config."
    elif data.get("response", {}).get("data"):
        d = data["response"]["data"]
        em.add_field(name="Stream Count", value=str(d.get("stream_count", 0)), inline=True)
        em.add_field(name="Direct Plays", value=str(d.get("stream_count_direct_play", 0)), inline=True)
        em.add_field(name="Transcodes", value=str(d.get("stream_count_transcode", 0)), inline=True)
    else:
        em.description = "No activity data available."
    await interaction.followup.send(embed=em)


@tasks.loop(seconds=UPDATE_INTERVAL)
async def status_loop():
    """Periodic status update to a configured channel."""
    # Could be configured via env var STATUS_CHANNEL_ID
    pass


@status_loop.before_loop
async def before_status_loop():
    await bot.wait_until_ready()


if __name__ == "__main__":
    if not BOT_TOKEN:
        print("[DiscordBot] ERROR: Set DISCORD_BOT_TOKEN environment variable.")
        sys.exit(1)
    bot.run(BOT_TOKEN)

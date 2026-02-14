"""
musicman.py -- Bot as music player in voice call
TODO: General improvement
"""

import asyncio # Asynchronous processes
import discord
import spotipy # Used to resolve provided spotify links
import yt_dlp # Takes Spotipy resolved data to instead play from YouTube

from collections import deque
from discord.ext import commands
from discord import app_commands
from spotipy import SpotifyClientCredentials

auth_manager = SpotifyClientCredentials() # Spotify, and thus Spotipy, requires an "application" to be made in the Spotify Dev Portal
sp = spotipy.Spotify(auth_manager=auth_manager)

# Options for when utilizing YT-DLP
YTDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch',
}

looping = True # Globalized bool for comms between GuildPlayers and the commands

class GuildPlayer:

    global looping

    def __init__(self, bot: commands.Bot, guild_id: int) -> None:
        self.bot = bot
        self.guild_id = guild_id
        self.queue = deque()
        self.playing = False
        self.voice_client: discord.VoiceClient | None = None

    async def ensure_voice(self, channel: discord.VoiceChannel) -> None: # Connects to the channel the client is in
        if self.voice_client and self.voice_client.is_connected():
            if self.voice_client.channel.id != channel.id:
                await self.voice_client.move_to(channel)
            return
        self.voice_client = await channel.connect()

    async def enqueue(self, source) -> None: # Queue a song
        self.queue.append(source)
        print("Song queued")

    async def _play_next(self, interaction: discord.Interaction) -> None: # Play a song, with logic to continue down the queue
        if not self.queue:
            self.playing = False
            return
        self.playing = True
        source = self.queue.popleft()

        if not self.voice_client or not self.voice_client.is_connected():
            # Attempt to reconnect to the user's channel
            if interaction.user and interaction.user.voice and interaction.user.voice.channel:
                await self.ensure_voice(interaction.user.voice.channel)
        if not self.voice_client:
            self.playing = False
            return

        def _after(err): # Utitilized by .play after the song ends
            coro = self._play_next(interaction)
            fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
            try:
                fut.result()
            except Exception:
                pass
        
        if looping:
            await self.enqueue(source, interaction)

        # Insert everything required into FFMPEG and voila, music! (If not just a lil laggy, quite heavy on the internet)
        before = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        opts = '-vn -b:a 2M -bufsize 1M'
        self.voice_client.play(discord.FFmpegPCMAudio(source, before_options=before, options=opts), after=_after)
        self.voice_client.source = discord.PCMVolumeTransformer(self.voice_client.source)
        print("Now playing")


class MusicCog(commands.Cog):

    global looping

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}

    def get_player(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer(self.bot, guild_id)
        return self.players[guild_id]

    async def _resolve_spotify(self, link: str) -> str: # Get the data required to match the song from Spotify to YouTube
        if 'open.spotify.com/track' in link:
            track = sp.track(link)
            title = track.get('name')
            artists = ', '.join([a['name'] for a in track.get('artists', [])])
            return f"{artists} - {title}"
        return link

    async def _ytdl_extract(self, query: str) -> str | None:
        ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)
        loop = asyncio.get_event_loop()

        def extract(): # Extracting the data from YouTube
            try:
                info = ytdl.extract_info(query, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                return info.get('url') or info.get('webpage_url')
            except Exception:
                return None

        return await loop.run_in_executor(None, extract)

    @app_commands.command(name="play", description="Play a track or link in your voice channel")
    @app_commands.describe(link="Spotify/YouTube link or search term", args=("Additional functions (loop)"))
    async def play(self, interaction: discord.Interaction, link: str, args: str) -> None:
        await interaction.response.defer(thinking=True)
        if not interaction.user or not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("I would follow you, but you are not in a voice channel.")
            return

        guild_id = interaction.guild_id
        player = self.get_player(guild_id)
        await player.ensure_voice(interaction.user.voice.channel)

        # Resolve a Spotify link
        query = link
        if 'open.spotify.com' in link:
            query = await self._resolve_spotify(link)

        # Use yt-dlp to find an audio source
        source_url = await self._ytdl_extract(query)
        if not source_url:
            await interaction.followup.send("Are you sure that exists, i cant quite sniff it out.")
            return

        response_text = f"Queued: {query}"
        if (args == "loop"):
            looping == True
            response_text += " (looping)"

        await player.enqueue(source_url, interaction)
        await player._play_next(interaction)
        await interaction.followup.send(response_text)

    @app_commands.command(name="skip", description="Skip current track")
    async def skip(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id
        player = self.players.get(guild_id)
        if not player or not player.voice_client or not player.voice_client.is_playing():
            await interaction.response.send_message("Barkki is not even barking")
            return
        player.voice_client.stop()
        await interaction.response.send_message("This one is (likely) my favorite.")

    @app_commands.command(name="stop", description="Remove all tracks from queue and disconnect")
    async def stop(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id
        player = self.players.get(guild_id)
        if not player:
            await interaction.response.send_message("Barkki is not even barking")
            return
        player.queue.clear()
        if player.voice_client and player.voice_client.is_connected():
            await player.voice_client.disconnect()
        await interaction.response.send_message("Fine...")


# Function to load this Cog into the bot
async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
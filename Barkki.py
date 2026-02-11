"""
Barkki.py -- Main entry point for Barkki.
"""

import discord
from discord.ext import commands, tasks
from utils.config import Config
import importlib
import pkgutil

# Load config (like bot token and timezone) from environment
CONFIG = Config()

# Tell Discord what kind of events/messages the bot should receive
intents = discord.Intents.all()
intents.message_content = True  # allows reading normal messages

bot = commands.Bot(command_prefix="!", intents=intents)


async def load_command_modules():
    # Dynamically load all command files inside "commands/" folder
    import commands as commands_pkg
    for finder, name, ispkg in pkgutil.iter_modules(commands_pkg.__path__):
        module_name = f"commands.{name}"
        module = importlib.import_module(module_name)

        # If the module has a setup() function, use it
        if hasattr(module, "setup"):
            await module.setup(bot)
        # Otherwise, if it just has a Cog class, add that directly
        elif hasattr(module, "Cog"):
            await bot.add_cog(module.Cog(bot))


@bot.event
async def on_ready():
    # This runs once when the bot connects successfully
    print(f"Logged in as {bot.user} ({bot.user.id})")
    # Set status as "Barking at Harkki"
    await bot.change_presence(status=discord.Status.online,activity=discord.Activity(name=f"custom", type=discord.ActivityType.custom, state="Barking at Harkki"))
    try:
        # Load all cogs and sync slash commands with Discord
        await load_command_modules()
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


def create_and_run_bot():
    # Start the bot (blocking call, it keeps running until stopped)
    bot.run(CONFIG.token)


# Run the bot if this file is run directly (python Barkki.py)
if __name__ == "__main__":
    create_and_run_bot()

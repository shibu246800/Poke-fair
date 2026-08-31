import os
import sqlite3
import threading
import re
from flask import Flask
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta

app = Flask('')

@app.route('/')
def home():
    return "PokéFair is running!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

TOKEN = os.environ.get("DISCORD_TOKEN")
COOLDOWN_MINUTES = 20
COOLDOWN_ROLE_NAME = "🐾 Pokémon Cooldown"
POKETWO_BOT_ID = 575825316447436810

CHANNELS_TO_WATCH = {
    "pokecord",
    "poketo-spawns",
    "spawn-hunt",
    "pokemon-hunt",
    "pokémon-wild"
}

DB_FILE = "cooldowns.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS cooldowns
        (user_id INTEGER, guild_id INTEGER, channel_id INTEGER, end_time TEXT)
    ''')
    conn.commit()
    conn.close()


init_db()

# Discord intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ PokéFair is online as {bot.user}")

    if not check_cooldowns.is_running():
        check_cooldowns.start()


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Check if the message is from Pokétwo and in a watched channel
    if (
        message.author.id == POKETWO_BOT_ID
        and message.channel.name in CHANNELS_TO_WATCH
    ):

        text_to_check = message.content or ""
        winner_member = None
        guild = message.guild

        # Look inside embeds
        if message.embeds:
            for embed in message.embeds:
                if embed.description:
                    text_to_check += " " + embed.description

                if embed.title:
                    text_to_check += " " + embed.title

        # Check if this is a catch confirmation message
        if "Congratulations" in text_to_check and "caught a" in text_to_check:

            # Method A: Check normal message mentions
            if message.mentions:
                winner_member = message.mentions[0]

            # Method B: Search for a user ID in the text
            if not winner_member:
                match = re.search(r"<@!?(\d+)>", text_to_check)

                if match and guild:
                    user_id = int(match.group(1))

                    try:
                        winner_member = (
                            guild.get_member(user_id)
                            or await guild.fetch_member(user_id)
                        )
                    except discord.NotFound:
                        winner_member = None

            # If we found the user, put them on cooldown
            if winner_member and guild:

                role = discord.utils.get(
                    guild.roles,
                    name=COOLDOWN_ROLE_NAME
                )

                if not role:
                    print(
                        f"❌ Error: '{COOLDOWN_ROLE_NAME}' role not found."
                    )
                    return

                end_time = datetime.utcnow() + timedelta(
                    minutes=COOLDOWN_MINUTES
                )

                end_time_str = end_time.strftime(
                    '%Y-%m-%d %H:%M:%S'
                )

                # Save cooldown to database
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()

                c.execute(
                    "DELETE FROM cooldowns WHERE user_id=? AND guild_id=?",
                    (winner_member.id, guild.id)
                )

                c.execute(
                    "INSERT INTO cooldowns VALUES (?, ?, ?, ?)",
                    (
                        winner_member.id,
                        guild.id,
                        message.channel.id,
                        end_time_str
                    )
                )

                conn.commit()
                conn.close()

                try:
                    # Give cooldown role
                    await winner_member.add_roles(role)

                    # Send message
                    await message.channel.send(
                        f"{winner_member.mention} congrats for getting the Pokémon!! "
                        f"you are held down to cooldown now. "
                        f"your next allowance is in "
                        f"{COOLDOWN_MINUTES} minutes."
                    )

                except discord.Forbidden:
                    await message.channel.send(
                        "❌ **PokéFair Error**: Cannot manage roles. "
                        "Make sure the PokéFair role is dragged "
                        "*above* the cooldown role in your Server Settings!"
                    )

    await bot.process_commands(message)


@tasks.loop(seconds=10)
async def check_cooldowns():

    await bot.wait_until_ready()

    now_str = datetime.utcnow().strftime(
        '%Y-%m-%d %H:%M:%S'
    )

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute(
        "SELECT user_id, guild_id, channel_id "
        "FROM cooldowns WHERE end_time <= ?",
        (now_str,)
    )

    expired = c.fetchall()

    for user_id, guild_id, channel_id in expired:

        guild = bot.get_guild(guild_id)

        if guild:

            try:
                member = (
                    guild.get_member(user_id)
                    or await guild.fetch_member(user_id)
                )

                role = discord.utils.get(
                    guild.roles,
                    name=COOLDOWN_ROLE_NAME
                )

                channel = guild.get_channel(channel_id)

                if member and role and role in member.roles:

                    # Remove cooldown role
                    await member.remove_roles(role)

                    cooldown_end_text = (
                        f"{member.mention} your cooldown ended. "
                        f"you can freely catch pokemon again now! "
                        f"good luck!"
                    )

                    # Send DM
                    try:
                        await member.send(cooldown_end_text)
                    except Exception:
                        print(
                            f"Could not send DM to {member.name}"
                        )

                    # Send in original channel
                    if channel:
                        await channel.send(cooldown_end_text)

            except Exception as e:
                print(
                    f"Could not clear cooldown for user "
                    f"{user_id}: {e}"
                )

        c.execute(
            "DELETE FROM cooldowns "
            "WHERE user_id=? AND guild_id=?",
            (user_id, guild_id)
        )

        conn.commit()

    conn.close()


if __name__ == "__main__":

    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()

    bot.run(TOKEN)

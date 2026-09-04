import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks
from flask import Flask

============================================================

CONFIG

============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

COOLDOWN_MINUTES = 20

Pokétwo

POKETWO_BOT_ID = 716390085896962058

PokéFair

POKEFAIR_BOT_ID = 1543540329121321040

Pokémon Cooldown role

COOLDOWN_ROLE_ID = 1543537941240872970

Your five Pokémon channels

WATCHED_CHANNEL_IDS = {
1531368924523008171,
1543531310285463552,
1543531671347925022,
1543531912755159060,
1543531989775421531,
}

DB_FILE = os.getenv("DATABASE_PATH", "cooldowns.db")

FLASK_HOST = "0.0.0.0"
FLASK_PORT = int(os.getenv("PORT", "8080"))

============================================================

DISCORD INTENTS

============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(
command_prefix="!",
intents=intents
)

============================================================

FLASK KEEP-ALIVE

============================================================

app = Flask(name)

@app.route("/")
def home():
return "PokéFair bot is alive!"

def run_web():
app.run(
host=FLASK_HOST,
port=FLASK_PORT,
debug=False,
use_reloader=False
)

============================================================

DATABASE

============================================================

def init_db():
with sqlite3.connect(DB_FILE) as conn:
conn.execute(
"""
CREATE TABLE IF NOT EXISTS cooldowns (
user_id INTEGER NOT NULL,
guild_id INTEGER NOT NULL,
channel_id INTEGER NOT NULL,
end_time TEXT NOT NULL
)
"""
)

def add_cooldown(user_id, guild_id, channel_id):
end_time = (
datetime.now(timezone.utc)
+ timedelta(minutes=COOLDOWN_MINUTES)
)

with sqlite3.connect(DB_FILE) as conn:

    conn.execute(
        """
        DELETE FROM cooldowns
        WHERE user_id = ? AND guild_id = ?
        """,
        (user_id, guild_id)
    )

    conn.execute(
        """
        INSERT INTO cooldowns
        (user_id, guild_id, channel_id, end_time)
        VALUES (?, ?, ?, ?)
        """,
        (
            user_id,
            guild_id,
            channel_id,
            end_time.isoformat()
        )
    )

def get_expired_cooldowns():
now = datetime.now(timezone.utc)
expired = []

with sqlite3.connect(DB_FILE) as conn:

    rows = conn.execute(
        """
        SELECT user_id, guild_id, channel_id, end_time
        FROM cooldowns
        """
    ).fetchall()

for user_id, guild_id, channel_id, end_time_string in rows:

    try:
        end_time = datetime.fromisoformat(
            end_time_string
        )

        if end_time <= now:
            expired.append(
                (
                    user_id,
                    guild_id,
                    channel_id
                )
            )

    except (ValueError, TypeError):

        expired.append(
            (
                user_id,
                guild_id,
                channel_id
            )
        )

return expired

def remove_cooldown(user_id, guild_id):

with sqlite3.connect(DB_FILE) as conn:

    conn.execute(
        """
        DELETE FROM cooldowns
        WHERE user_id = ? AND guild_id = ?
        """,
        (user_id, guild_id)
    )

============================================================

READ MESSAGE + EMBEDS

============================================================

def get_message_text(message):

parts = []

if message.content:
    parts.append(message.content)

for embed in message.embeds:

    if embed.title:
        parts.append(embed.title)

    if embed.description:
        parts.append(embed.description)

    if embed.author and embed.author.name:
        parts.append(embed.author.name)

    for field in embed.fields:

        if field.name:
            parts.append(field.name)

        if field.value:
            parts.append(field.value)

    if embed.footer and embed.footer.text:
        parts.append(embed.footer.text)

return "\n".join(parts)

============================================================

FIND WINNER

============================================================

async def find_winner(message):

full_text = get_message_text(message)

print("🔎 Pokétwo message:")
print(full_text)

# Find:
# <@123456789>
# or:
# <@!123456789>

match = re.search(
    r"<@!?(\d+)>",
    full_text
)

if match:

    user_id = int(match.group(1))

    print(
        f"👤 Winner ID found: {user_id}"
    )

    member = message.guild.get_member(
        user_id
    )

    if member:
        return member

    try:

        return await message.guild.fetch_member(
            user_id
        )

    except discord.NotFound:

        print(
            f"❌ User {user_id} not found."
        )

    except discord.HTTPException as error:

        print(
            f"❌ Could not fetch user: {error}"
        )

# Fallback to actual mentions

for member in message.mentions:

    if not member.bot:

        print(
            f"👤 Winner found through mentions: "
            f"{member}"
        )

        return member

return None

============================================================

BOT READY

============================================================

@bot.event
async def on_ready():

print("=" * 60)
print("🐾 POKÉFAIR IS ONLINE")
print(f"🤖 Bot: {bot.user}")
print(f"🆔 Bot ID: {bot.user.id}")
print("=" * 60)

init_db()

if not check_cooldowns.is_running():

    check_cooldowns.start()

if not hasattr(bot, "web_started"):

    bot.web_started = True

    threading.Thread(
        target=run_web,
        daemon=True
    ).start()

    print(
        "🌐 Flask keep-alive started."
    )

print(
    "✅ PokéFair is ready."
)

============================================================

MESSAGE DETECTION

============================================================

@bot.event
async def on_message(message):

# --------------------------------------------------------
# Ignore PokéFair itself
# --------------------------------------------------------

if message.author.id == POKEFAIR_BOT_ID:
    return

# --------------------------------------------------------
# Only inspect Pokétwo messages in the five channels
# --------------------------------------------------------

if (
    message.author.id == POKETWO_BOT_ID
    and message.channel.id in WATCHED_CHANNEL_IDS
):

    print("=" * 60)
    print("🎯 POKÉTWO MESSAGE RECEIVED!")
    print(
        f"📍 Channel ID: {message.channel.id}"
    )
    print(
        f"🆔 Message ID: {message.id}"
    )

    full_text = get_message_text(message)

    print("📨 MESSAGE:")
    print(full_text)
    print("=" * 60)

    # ----------------------------------------------------
    # Detect the exact catch wording
    # ----------------------------------------------------

    text_lower = full_text.lower()

    if (
        "congratulations" not in text_lower
        or "you caught" not in text_lower
    ):

        print(
            "ℹ️ Pokétwo message received, "
            "but this is not a catch message."
        )

        return

    print(
        "🎉🎉🎉 POKÉMON CATCH CONFIRMED! 🎉🎉🎉"
    )

    if message.guild is None:

        print(
            "❌ Message has no guild."
        )

        return

    # ----------------------------------------------------
    # Find winner
    # ----------------------------------------------------

    winner = await find_winner(message)

    if winner is None:

        print(
            "❌❌ WINNER NOT FOUND."
        )

        return

    print(
        f"✅ WINNER FOUND: "
        f"{winner} ({winner.id})"
    )

    # ----------------------------------------------------
    # Find cooldown role
    # ----------------------------------------------------

    role = message.guild.get_role(
        COOLDOWN_ROLE_ID
    )

    if role is None:

        print(
            "❌❌ COOLDOWN ROLE NOT FOUND!"
        )

        print(
            f"Expected role ID: "
            f"{COOLDOWN_ROLE_ID}"
        )

        return

    print(
        f"🎭 ROLE FOUND: {role.name}"
    )

    # ----------------------------------------------------
    # Get PokéFair's server member
    # ----------------------------------------------------

    bot_member = message.guild.me

    if bot_member is None:

        print(
            "❌ Could not find PokéFair's server member."
        )

        return

    print(
        f"🤖 POKÉFAIR TOP ROLE: "
        f"{bot_member.top_role.name}"
    )

    print(
        f"🤖 POKÉFAIR ROLE POSITION: "
        f"{bot_member.top_role.position}"
    )

    print(
        f"🎭 COOLDOWN ROLE POSITION: "
        f"{role.position}"
    )

    # ----------------------------------------------------
    # Check hierarchy
    # ----------------------------------------------------

    if role >= bot_member.top_role:

        print(
            "❌❌❌ ROLE HIERARCHY ERROR!"
        )

        print(
            "Move the PokéFair bot role ABOVE "
            "the Pokémon Cooldown role."
        )

        return

    # ----------------------------------------------------
    # Check Manage Roles permission
    # ----------------------------------------------------

    if not bot_member.guild_permissions.manage_roles:

        print(
            "❌❌❌ POKÉFAIR DOES NOT HAVE "
            "MANAGE ROLES PERMISSION!"
        )

        return

    # ----------------------------------------------------
    # Give cooldown role
    # ----------------------------------------------------

    print(
        "⏳ Giving Pokémon Cooldown role..."
    )

    try:

        await winner.add_roles(
            role,
            reason="Pokémon catch cooldown"
        )

        print(
            f"✅✅✅ ROLE GIVEN SUCCESSFULLY "
            f"TO {winner}!"
        )

    except discord.Forbidden:

        print(
            "❌❌❌ DISCORD FORBIDDEN!"
        )

        print(
            "Check Manage Roles permission "
            "and role hierarchy."
        )

        return

    except discord.HTTPException as error:

        print(
            f"❌❌❌ DISCORD HTTP ERROR: {error}"
        )

        return

    # ----------------------------------------------------
    # Save cooldown
    # ----------------------------------------------------

    add_cooldown(
        user_id=winner.id,
        guild_id=message.guild.id,
        channel_id=message.channel.id
    )

    print(
        f"⏰ COOLDOWN SAVED: "
        f"{COOLDOWN_MINUTES} MINUTES"
    )

    # ----------------------------------------------------
    # CONFIRMATION MESSAGE
    # ----------------------------------------------------

    try:

        await message.channel.send(
            f"{winner.mention} is now under cooldown "
            f"for {COOLDOWN_MINUTES} mins. "
            f"Enjoy the rest of the server! 🐾"
        )

        print(
            "📢 COOLDOWN CONFIRMATION SENT!"
        )

    except discord.Forbidden:

        print(
            "⚠️ PokéFair cannot send messages "
            "in this channel."
        )

    except discord.HTTPException as error:

        print(
            f"⚠️ Could not send confirmation: "
            f"{error}"
        )

    return

# --------------------------------------------------------
# Normal commands
# --------------------------------------------------------

await bot.process_commands(message)

============================================================

AUTOMATIC COOLDOWN CLEANUP

============================================================

@tasks.loop(seconds=10)
async def check_cooldowns():

expired = get_expired_cooldowns()

if not expired:
    return

print(
    f"⏰ {len(expired)} cooldown(s) expired."
)

for user_id, guild_id, channel_id in expired:

    guild = bot.get_guild(guild_id)

    if guild is None:

        remove_cooldown(
            user_id,
            guild_id
        )

        continue

    # ----------------------------------------------------
    # Find member
    # ----------------------------------------------------

    member = guild.get_member(
        user_id
    )

    if member is None:

        try:

            member = await guild.fetch_member(
                user_id
            )

        except (
            discord.NotFound,
            discord.HTTPException
        ):

            remove_cooldown(
                user_id,
                guild_id
            )

            continue

    # ----------------------------------------------------
    # Find role
    # ----------------------------------------------------

    role = guild.get_role(
        COOLDOWN_ROLE_ID
    )

    if role is None:

        remove_cooldown(
            user_id,
            guild_id
        )

        continue

    # ----------------------------------------------------
    # Remove role
    # ----------------------------------------------------

    if role in member.roles:

        try:

            await member.remove_roles(
                role,
                reason="Pokémon cooldown expired"
            )

            print(
                f"✅ COOLDOWN ENDED FOR {member}."
            )

        except discord.Forbidden:

            print(
                f"❌ Cannot remove role from "
                f"{member}."
            )

        except discord.HTTPException as error:

            print(
                f"❌ Error removing role: {error}"
            )

    # ----------------------------------------------------
    # DM user
    # ----------------------------------------------------

    try:

        await member.send(
            "🐾 Your Pokémon cooldown has ended! "
            "You can catch Pokémon again. "
            "Good luck! 🎉"
        )

        print(
            f"📩 Cooldown-end DM sent to {member}."
        )

    except discord.HTTPException:

        print(
            f"⚠️ Could not DM {member}."
        )

    # ----------------------------------------------------
    # Delete database record
    # ----------------------------------------------------

    remove_cooldown(
        user_id,
        guild_id
    )

============================================================

TASK ERROR HANDLER

============================================================

@check_cooldowns.error
async def cooldown_task_error(error):

print(
    f"❌ COOLDOWN TASK ERROR: {error}"
)

============================================================

START BOT

============================================================

if name == "main":

if not TOKEN:

    raise RuntimeError(
        "DISCORD_TOKEN environment variable is not set!"
    )

print(
    "🚀 Starting PokéFair..."
)

bot.run(TOKEN)

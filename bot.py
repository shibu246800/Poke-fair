 import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks
from flask import Flask


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

COOLDOWN_ROLE_NAME = os.getenv(
    "COOLDOWN_ROLE_NAME",
    "🐾 Pokémon Cooldown"
)

COOLDOWN_MINUTES = int(
    os.getenv("COOLDOWN_MINUTES", "20")
)

DB_FILE = os.getenv(
    "DATABASE_PATH",
    "cooldowns.db"
)

FLASK_HOST = os.getenv(
    "FLASK_HOST",
    "0.0.0.0"
)

FLASK_PORT = int(
    os.getenv("PORT", os.getenv("FLASK_PORT", "8080"))
)


# ============================================================
# POKÉTWO
# ============================================================

POKETWO_BOT_ID = 716390085896962058

CHANNELS_TO_WATCH = {
    "🌸・pokecord",
    "🌸・poketo-spawns",
    "🌸・spawn-hunt",
    "🌸・pokemon-hunt",
    "🌸・pokémon-wild",
}


# ============================================================
# DISCORD
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# FLASK KEEP-ALIVE
# ============================================================

app = Flask(__name__)


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


# ============================================================
# DATABASE
# ============================================================

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


def add_cooldown(user_id, guild_id, channel_id, minutes):
    end_time = datetime.now(timezone.utc) + timedelta(
        minutes=minutes
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

    for user_id, guild_id, channel_id, end_time_str in rows:
        try:
            end_time = datetime.fromisoformat(end_time_str)

            if end_time <= now:
                expired.append(
                    (user_id, guild_id, channel_id)
                )

        except (ValueError, TypeError):
            expired.append(
                (user_id, guild_id, channel_id)
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


# ============================================================
# MESSAGE TEXT / EMBEDS
# ============================================================

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


# ============================================================
# FIND WINNER
# ============================================================

async def find_winner(message):

    full_text = get_message_text(message)

    # Look for Discord user mentions.
    match = re.search(
        r"<@!?(\d+)>",
        full_text
    )

    if match:
        user_id = int(match.group(1))

        member = message.guild.get_member(user_id)

        if member:
            return member

        try:
            return await message.guild.fetch_member(user_id)

        except discord.NotFound:
            print(
                f"❌ User {user_id} not found."
            )

        except discord.HTTPException as e:
            print(
                f"❌ Could not fetch user {user_id}: {e}"
            )

    # Fallback: check actual message mentions.
    for member in message.mentions:
        if not member.bot:
            return member

    return None


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():

    print(
        f"✅ PokéFair is ONLINE as "
        f"{bot.user} "
        f"(ID: {bot.user.id})"
    )

    init_db()

    if not check_cooldowns.is_running():
        check_cooldowns.start()

    if not getattr(bot, "web_started", False):

        threading.Thread(
            target=run_web,
            daemon=True
        ).start()

        bot.web_started = True

        print(
            "🌐 Keep-alive web server started."
        )


# ============================================================
# MESSAGE EVENT
# ============================================================

@bot.event
async def on_message(message):

    # --------------------------------------------------------
    # Ignore messages from ourselves and other bots,
    # BUT DO NOT IGNORE POKÉTWO.
    # --------------------------------------------------------

    if message.author.id == bot.user.id:
        return

    is_poketwo = (
        message.author.id == POKETWO_BOT_ID
    )

    if message.author.bot and not is_poketwo:
        await bot.process_commands(message)
        return

    # --------------------------------------------------------
    # DMs don't have guilds.
    # --------------------------------------------------------

    if message.guild is None:
        await bot.process_commands(message)
        return

    # --------------------------------------------------------
    # Only watch the Pokémon channels.
    # --------------------------------------------------------

    if message.channel.name not in CHANNELS_TO_WATCH:
        await bot.process_commands(message)
        return

    # --------------------------------------------------------
    # Get normal message + embed text.
    # --------------------------------------------------------

    full_text = get_message_text(message)
    text_lower = full_text.lower()

    print(
        f"📩 Message received in #{message.channel.name}: "
        f"{full_text[:200]}"
    )

    # --------------------------------------------------------
    # Detect Pokétwo catch.
    # --------------------------------------------------------

    is_catch = (
        is_poketwo
        and "congratulations" in text_lower
        and "caught a" in text_lower
    )

    if not is_catch:
        await bot.process_commands(message)
        return

    print(
        "🎯🎯🎯 POKÉTWO CATCH DETECTED! 🎯🎯🎯"
    )

    # --------------------------------------------------------
    # Find winner.
    # --------------------------------------------------------

    winner_member = await find_winner(message)

    if winner_member is None:
        print(
            "❌ CATCH FOUND BUT WINNER NOT FOUND."
        )

        await bot.process_commands(message)
        return

    print(
        f"✅ WINNER FOUND: "
        f"{winner_member} "
        f"({winner_member.id})"
    )

    # --------------------------------------------------------
    # Find cooldown role.
    # --------------------------------------------------------

    role = discord.utils.get(
        message.guild.roles,
        name=COOLDOWN_ROLE_NAME
    )

    if role is None:
        print(
            f"❌ ROLE NOT FOUND: "
            f"{COOLDOWN_ROLE_NAME}"
        )

        await bot.process_commands(message)
        return

    print(
        f"🎭 ROLE FOUND: {role.name} "
        f"| Position: {role.position}"
    )

    # --------------------------------------------------------
    # Get bot's member object.
    # --------------------------------------------------------

    bot_member = message.guild.me

    if bot_member is None:
        print(
            "❌ Could not find bot member."
        )

        await bot.process_commands(message)
        return

    print(
        f"🤖 BOT TOP ROLE: "
        f"{bot_member.top_role.name} "
        f"| Position: "
        f"{bot_member.top_role.position}"
    )

    # --------------------------------------------------------
    # Role hierarchy check.
    # --------------------------------------------------------

    if role >= bot_member.top_role:

        print(
            "❌❌❌ ROLE HIERARCHY ERROR!"
        )

        print(
            "Move the PokéFair bot role ABOVE "
            "the Pokémon Cooldown role."
        )

        await bot.process_commands(message)
        return

    # --------------------------------------------------------
    # Don't give duplicate cooldown.
    # --------------------------------------------------------

    if role in winner_member.roles:

        print(
            f"⚠️ {winner_member} is already "
            f"on cooldown."
        )

        await bot.process_commands(message)
        return

    # --------------------------------------------------------
    # Give cooldown role.
    # --------------------------------------------------------

    print(
        "⏳ Attempting to give cooldown role..."
    )

    try:

        await winner_member.add_roles(
            role,
            reason="Pokémon catch cooldown"
        )

        print(
            f"✅✅✅ ROLE GIVEN SUCCESSFULLY "
            f"TO {winner_member}!"
        )

    except discord.Forbidden:

        print(
            "❌❌❌ DISCORD FORBIDDEN!"
        )

        print(
            "Check Manage Roles permission "
            "and role hierarchy."
        )

        await bot.process_commands(message)
        return

    except discord.HTTPException as e:

        print(
            f"❌❌❌ DISCORD HTTP ERROR: {e}"
        )

        await bot.process_commands(message)
        return

    # --------------------------------------------------------
    # Save cooldown.
    # --------------------------------------------------------

    add_cooldown(
        user_id=winner_member.id,
        guild_id=message.guild.id,
        channel_id=message.channel.id,
        minutes=COOLDOWN_MINUTES
    )

    print(
        f"⏰ COOLDOWN SAVED FOR "
        f"{COOLDOWN_MINUTES} MINUTES."
    )

    # --------------------------------------------------------
    # Confirmation message.
    # --------------------------------------------------------

    try:

        await message.channel.send(
            f"{winner_member.mention} congrats "
            f"for getting the Pokémon!! 🎉\n"
            f"You are now on cooldown for "
            f"{COOLDOWN_MINUTES} minutes."
        )

        print(
            "✅ Confirmation message sent."
        )

    except discord.HTTPException as e:

        print(
            f"⚠️ Could not send confirmation: {e}"
        )

    await bot.process_commands(message)


# ============================================================
# COOLDOWN CLEANUP
# ============================================================

@tasks.loop(seconds=10)
async def check_cooldowns():

    expired = get_expired_cooldowns()

    for user_id, guild_id, channel_id in expired:

        try:

            guild = bot.get_guild(guild_id)

            if guild is None:

                remove_cooldown(
                    user_id,
                    guild_id
                )

                continue

            # ------------------------------------------------
            # Find member.
            # ------------------------------------------------

            member = guild.get_member(user_id)

            if member is None:

                try:

                    member = await guild.fetch_member(
                        user_id
                    )

                except discord.NotFound:

                    print(
                        f"⚠️ User {user_id} "
                        f"is no longer in server."
                    )

                    remove_cooldown(
                        user_id,
                        guild_id
                    )

                    continue

                except discord.HTTPException as e:

                    print(
                        f"⚠️ Could not fetch "
                        f"user {user_id}: {e}"
                    )

                    continue

            # ------------------------------------------------
            # Find role.
            # ------------------------------------------------

            role = discord.utils.get(
                guild.roles,
                name=COOLDOWN_ROLE_NAME
            )

            if role is None:

                print(
                    f"❌ Cooldown role not found "
                    f"in guild {guild_id}."
                )

                remove_cooldown(
                    user_id,
                    guild_id
                )

                continue

            # ------------------------------------------------
            # Remove role.
            # ------------------------------------------------

            if role in member.roles:

                try:

                    await member.remove_roles(
                        role,
                        reason="Pokémon cooldown expired"
                    )

                    print(
                        f"✅ Cooldown ended for "
                        f"{member}."
                    )

                except discord.Forbidden:

                    print(
                        f"❌ Missing permission "
                        f"to remove role from {member}."
                    )

                    continue

                except discord.HTTPException as e:

                    print(
                        f"❌ HTTP error removing "
                        f"role: {e}"
                    )

                    continue

            # ------------------------------------------------
            # DM user.
            # ------------------------------------------------

            try:

                await member.send(
                    "Your Pokémon cooldown has ended! 🎉\n"
                    "You can catch Pokémon again. "
                    "Good luck!"
                )

            except discord.HTTPException:

                print(
                    f"⚠️ Could not DM {member}."
                )

            # ------------------------------------------------
            # Delete database entry.
            # ------------------------------------------------

            remove_cooldown(
                user_id,
                guild_id
            )

        except Exception as e:

            print(
                f"❌ Error processing cooldown "
                f"for {user_id}: {e}"
            )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    if not TOKEN:

        raise RuntimeError(
            "DISCORD_TOKEN environment variable "
            "not set!"
        )

    bot.run(TOKEN)

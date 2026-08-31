import os
import sqlite3
import threading
import re
from flask import Flask
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone


# =========================
# WEB SERVER FOR RENDER
# =========================

app = Flask("")


@app.route("/")
def home():
    return "PokéFair is running!"


def run_web():
    app.run(host="0.0.0.0", port=8080)


# =========================
# SETTINGS
# =========================

TOKEN = os.environ.get("DISCORD_TOKEN")

COOLDOWN_MINUTES = 20
COOLDOWN_ROLE_NAME = "🐾 Pokémon Cooldown"

POKETWO_BOT_ID = 716390085896962058

DB_FILE = "cooldowns.db"


# =========================
# DATABASE
# =========================

def init_db():
    conn = sqlite3.connect(DB_FILE)

    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS cooldowns (
            user_id INTEGER,
            guild_id INTEGER,
            channel_id INTEGER,
            end_time TEXT
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================
# READY
# =========================

@bot.event
async def on_ready():

    print(f"✅ PokéFair is online as {bot.user}")

    if not check_cooldowns.is_running():
        check_cooldowns.start()


# =========================
# POKETWO CATCH DETECTION
# =========================

@bot.event
async def on_message(message):

    # Ignore PokéFair's own messages
    if message.author.id == bot.user.id:
        return

    # Only watch Pokétwo
    if message.author.id != POKETWO_BOT_ID:
        await bot.process_commands(message)
        return

    guild = message.guild

    if guild is None:
        await bot.process_commands(message)
        return

    # =========================
    # COLLECT ALL MESSAGE TEXT
    # =========================

    text_to_check = message.content or ""

    # Check embeds
    for embed in message.embeds:

        if embed.title:
            text_to_check += " " + embed.title

        if embed.description:
            text_to_check += " " + embed.description

        for field in embed.fields:
            if field.name:
                text_to_check += " " + field.name

            if field.value:
                text_to_check += " " + field.value

        if embed.footer and embed.footer.text:
            text_to_check += " " + embed.footer.text

    # =========================
    # CHECK NORMAL POKETWO
    # CATCH CONFIRMATION
    # =========================

    if (
        "Congratulations" not in text_to_check
        or "caught a" not in text_to_check
    ):
        await bot.process_commands(message)
        return

    print(
        f"🎯 Pokétwo catch detected in #{message.channel.name}"
    )

    print(
        f"📝 Catch message: {text_to_check[:500]}"
    )

    # =========================
    # FIND WINNER
    # =========================

    winner_member = None

    # Method 1:
    # Normal Discord mentions
    if message.mentions:

        for member in message.mentions:

            if member.bot is False:
                winner_member = member
                break

        # Sometimes the first mention is the winner
        if winner_member is None:
            winner_member = message.mentions[0]

    # Method 2:
    # Search text for Discord user ID
    if winner_member is None:

        match = re.search(
            r"<@!?(\d+)>",
            text_to_check
        )

        if match:

            user_id = int(match.group(1))

            try:

                winner_member = (
                    guild.get_member(user_id)
                    or await guild.fetch_member(user_id)
                )

            except discord.NotFound:

                winner_member = None

            except discord.HTTPException as e:

                print(
                    f"❌ Could not fetch winner: {e}"
                )

    # =========================
    # NO USER FOUND
    # =========================

    if winner_member is None:

        print(
            "❌ Catch detected, but could not find the winner."
        )

        await bot.process_commands(message)
        return

    print(
        f"👤 Winner detected: "
        f"{winner_member} ({winner_member.id})"
    )

    # =========================
    # FIND COOLDOWN ROLE
    # =========================

    role = discord.utils.get(
        guild.roles,
        name=COOLDOWN_ROLE_NAME
    )

    if role is None:

        print(
            f"❌ Role not found: {COOLDOWN_ROLE_NAME}"
        )

        await bot.process_commands(message)
        return

    print(
        f"🔎 Cooldown role found: "
        f"{role.name} | ID: {role.id}"
    )

    # =========================
    # CHECK ROLE HIERARCHY
    # =========================

    bot_member = guild.me

    if bot_member is None:

        print("❌ Could not find PokéFair's server member.")

        await bot.process_commands(message)
        return

    if role >= bot_member.top_role:

        print(
            "❌ ROLE HIERARCHY ERROR: "
            "PokéFair's highest role is not above "
            "the Pokémon Cooldown role."
        )

        try:

            await message.channel.send(
                "❌ **PokéFair Error:** My role must be "
                "**above** `🐾 Pokémon Cooldown`."
            )

        except Exception:
            pass

        await bot.process_commands(message)
        return

    # =========================
    # GIVE ROLE
    # =========================

    try:

        await winner_member.add_roles(
            role,
            reason="Pokémon catch cooldown"
        )

        print(
            f"✅ GAVE COOLDOWN ROLE to "
            f"{winner_member}."
        )

    except discord.Forbidden:

        print(
            "❌ Discord Forbidden: "
            "PokéFair cannot add the cooldown role."
        )

        try:

            await message.channel.send(
                "❌ **PokéFair Error:** "
                "I cannot give the cooldown role. "
                "Check my role hierarchy and permissions."
            )

        except Exception:
            pass

        await bot.process_commands(message)
        return

    except discord.HTTPException as e:

        print(
            f"❌ Discord HTTP error while giving role: {e}"
        )

        await bot.process_commands(message)
        return

    # =========================
    # SAVE 20-MINUTE COOLDOWN
    # =========================

    end_time = datetime.now(timezone.utc) + timedelta(
        minutes=COOLDOWN_MINUTES
    )

    end_time_str = end_time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    conn = sqlite3.connect(DB_FILE)

    c = conn.cursor()

    c.execute(
        """
        DELETE FROM cooldowns
        WHERE user_id=? AND guild_id=?
        """,
        (
            winner_member.id,
            guild.id
        )
    )

    c.execute(
        """
        INSERT INTO cooldowns
        VALUES (?, ?, ?, ?)
        """,
        (
            winner_member.id,
            guild.id,
            message.channel.id,
            end_time_str
        )
    )

    conn.commit()
    conn.close()

    print(
        f"⏳ Cooldown saved for {winner_member} "
        f"until {end_time_str} UTC."
    )

    # =========================
    # SEND CONFIRMATION
    # =========================

    try:

        await message.channel.send(
            f"{winner_member.mention} congrats for getting the Pokémon!! "
            f"you are held down to cooldown now. "
            f"your next allowance is in "
            f"{COOLDOWN_MINUTES} minutes."
        )

    except discord.HTTPException as e:

        print(
            f"⚠️ Could not send confirmation message: {e}"
        )

    await bot.process_commands(message)


# =========================
# COOLDOWN CHECKER
# =========================

@tasks.loop(seconds=10)
async def check_cooldowns():

    await bot.wait_until_ready()

    now_str = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    conn = sqlite3.connect(DB_FILE)

    c = conn.cursor()

    c.execute(
        """
        SELECT user_id, guild_id, channel_id
        FROM cooldowns
        WHERE end_time <= ?
        """,
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

                if (
                    member
                    and role
                    and role in member.roles
                ):

                    # Remove role
                    await member.remove_roles(
                        role,
                        reason="Pokémon cooldown expired"
                    )

                    print(
                        f"✅ Removed cooldown role "
                        f"from {member}."
                    )

                    cooldown_end_text = (
                        f"{member.mention} your cooldown ended. "
                        f"you can freely catch pokemon again now! "
                        f"good luck!"
                    )

                    # DM
                    try:

                        await member.send(
                            cooldown_end_text
                        )

                    except Exception:

                        print(
                            f"⚠️ Could not DM {member.name}"
                        )

                    # Original channel
                    if channel:

                        try:

                            await channel.send(
                                cooldown_end_text
                            )

                        except Exception:
                            pass

            except Exception as e:

                print(
                    f"❌ Could not clear cooldown "
                    f"for user {user_id}: {e}"
                )

        # Delete expired record
        c.execute(
            """
            DELETE FROM cooldowns
            WHERE user_id=? AND guild_id=?
            """,
            (
                user_id,
                guild_id
            )
        )

        conn.commit()

    conn.close()


# =========================
# START
# =========================

if __name__ == "__main__":

    t = threading.Thread(
        target=run_web,
        daemon=True
    )

    t.start()

    bot.run(TOKEN)

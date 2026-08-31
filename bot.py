import os
import sqlite3
import threading
import re

from flask import Flask

import discord
from discord.ext import commands, tasks

from datetime import datetime, timedelta, timezone


# ============================================================
# RENDER WEB SERVER
# ============================================================

app = Flask("")


@app.route("/")
def home():
    return "PokéFair is running!"


def run_web():
    app.run(
        host="0.0.0.0",
        port=8080
    )


# ============================================================
# SETTINGS
# ============================================================

TOKEN = os.environ.get("DISCORD_TOKEN")

COOLDOWN_MINUTES = 20

COOLDOWN_ROLE_NAME = "🐾 Pokémon Cooldown"

POKETWO_BOT_ID = 716390085896962058

DB_FILE = "cooldowns.db"


# ============================================================
# DATABASE
# ============================================================

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


# ============================================================
# DISCORD INTENTS
# ============================================================

intents = discord.Intents.default()

intents.message_content = True

intents.messages = True


# ============================================================
# BOT
# ============================================================

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# BOT READY
# ============================================================

@bot.event
async def on_ready():

    print("=" * 50)

    print(f"✅ PokéFair is ONLINE as {bot.user}")

    print(f"🆔 Bot ID: {bot.user.id}")

    print("=" * 50)

    if not check_cooldowns.is_running():

        check_cooldowns.start()


# ============================================================
# MESSAGE LISTENER
# ============================================================

@bot.event
async def on_message(message):

    # --------------------------------------------------------
    # TEST: Did the bot receive a message?
    # --------------------------------------------------------

    print(
        f"📩 MESSAGE RECEIVED | "
        f"Author: {message.author} | "
        f"Author ID: {message.author.id} | "
        f"Channel: #{message.channel.name}"
    )


    # --------------------------------------------------------
    # Ignore our own messages
    # --------------------------------------------------------

    if message.author.id == bot.user.id:

        return


    # --------------------------------------------------------
    # Show if this is Pokétwo
    # --------------------------------------------------------

    if message.author.id == POKETWO_BOT_ID:

        print(
            "🐾 THIS MESSAGE IS FROM POKÉTWO!"
        )

    else:

        print(
            "ℹ️ This message is NOT from Pokétwo."
        )


    # --------------------------------------------------------
    # Only continue for Pokétwo
    # --------------------------------------------------------

    if message.author.id != POKETWO_BOT_ID:

        await bot.process_commands(message)

        return


    guild = message.guild


    if guild is None:

        print(
            "❌ Pokétwo message has no guild."
        )

        await bot.process_commands(message)

        return


    # ========================================================
    # COLLECT MESSAGE TEXT
    # ========================================================

    text_to_check = message.content or ""


    print(
        f"📝 NORMAL MESSAGE TEXT: {text_to_check[:500]}"
    )


    # --------------------------------------------------------
    # Read embeds
    # --------------------------------------------------------

    if message.embeds:

        print(
            f"📦 EMBEDS FOUND: {len(message.embeds)}"
        )

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

    else:

        print(
            "📦 No embeds found."
        )


    print(
        f"🔍 FULL TEXT CHECK: {text_to_check[:1000]}"
    )


    # ========================================================
    # ORIGINAL POKÉTWO CATCH DETECTION
    # ========================================================

    if (
        "Congratulations" not in text_to_check
        or "caught a" not in text_to_check
    ):

        print(
            "❌ Not a Pokétwo catch confirmation."
        )

        await bot.process_commands(message)

        return


    # ========================================================
    # CATCH DETECTED
    # ========================================================

    print(
        "🎯🎯🎯 POKÉTWO CATCH DETECTED! 🎯🎯🎯"
    )


    # ========================================================
    # FIND WINNER
    # ========================================================

    winner_member = None


    # --------------------------------------------------------
    # Method 1: Discord mentions
    # --------------------------------------------------------

    if message.mentions:

        print(
            f"👤 Mentions found: {len(message.mentions)}"
        )

        for member in message.mentions:

            print(
                f"👤 Mention: {member} "
                f"| ID: {member.id}"
            )

        winner_member = message.mentions[0]


    # --------------------------------------------------------
    # Method 2: Search for user ID
    # --------------------------------------------------------

    if winner_member is None:

        match = re.search(
            r"<@!?(\d+)>",
            text_to_check
        )

        if match:

            user_id = int(match.group(1))

            print(
                f"🔎 User ID found in text: {user_id}"
            )

            try:

                winner_member = (
                    guild.get_member(user_id)
                    or await guild.fetch_member(user_id)
                )

            except discord.NotFound:

                print(
                    "❌ User was not found in the server."
                )

            except discord.HTTPException as e:

                print(
                    f"❌ Could not fetch user: {e}"
                )


    # ========================================================
    # WINNER CHECK
    # ========================================================

    if winner_member is None:

        print(
            "❌❌❌ CATCH FOUND BUT WINNER NOT FOUND."
        )

        await bot.process_commands(message)

        return


    print(
        f"✅ WINNER FOUND: "
        f"{winner_member} "
        f"({winner_member.id})"
    )


    # ========================================================
    # FIND COOLDOWN ROLE
    # ========================================================

    role = discord.utils.get(
        guild.roles,
        name=COOLDOWN_ROLE_NAME
    )


    if role is None:

        print(
            f"❌❌❌ ROLE NOT FOUND: "
            f"{COOLDOWN_ROLE_NAME}"
        )

        await bot.process_commands(message)

        return


    print(
        f"🎭 ROLE FOUND: "
        f"{role.name} "
        f"| ID: {role.id}"
    )


    # ========================================================
    # CHECK BOT ROLE POSITION
    # ========================================================

    bot_member = guild.me


    if bot_member is None:

        print(
            "❌ Could not find PokéFair's member object."
        )

        await bot.process_commands(message)

        return


    print(
        f"🤖 BOT TOP ROLE: "
        f"{bot_member.top_role.name} "
        f"| Position: {bot_member.top_role.position}"
    )

    print(
        f"🎭 COOLDOWN ROLE POSITION: "
        f"{role.position}"
    )


    if role >= bot_member.top_role:

        print(
            "❌❌❌ ROLE HIERARCHY ERROR!"
        )

        print(
            "The PokéFair bot role must be ABOVE "
            "the Pokémon Cooldown role."
        )

        await bot.process_commands(message)

        return


    # ========================================================
    # GIVE ROLE
    # ========================================================

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
            "PokéFair does not have permission "
            "to give this role."
        )

        await bot.process_commands(message)

        return


    except discord.HTTPException as e:

        print(
            f"❌❌❌ DISCORD HTTP ERROR: {e}"
        )

        await bot.process_commands(message)

        return


    # ========================================================
    # SAVE COOLDOWN
    # ========================================================

    end_time = (
        datetime.now(timezone.utc)
        + timedelta(minutes=COOLDOWN_MINUTES)
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
        f"⏰ COOLDOWN SAVED FOR "
        f"{COOLDOWN_MINUTES} MINUTES."
    )


    # ========================================================
    # SEND CONFIRMATION
    # ========================================================

    try:

        await message.channel.send(
            f"{winner_member.mention} congrats for getting the Pokémon!! "
            f"you are held down to cooldown now. "
            f"your next allowance is in "
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
# COOLDOWN CHECKER
# ============================================================

@tasks.loop(seconds=10)
async def check_cooldowns():

    await bot.wait_until_ready()


    now_str = datetime.now(
        timezone.utc
    ).strftime(
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


                channel = guild.get_channel(
                    channel_id
                )


                if (
                    member
                    and role
                    and role in member.roles
                ):

                    await member.remove_roles(
                        role,
                        reason="Pokémon cooldown expired"
                    )


                    print(
                        f"✅ Cooldown ended for "
                        f"{member}."
                    )


                    cooldown_end_text = (
                        f"{member.mention} your cooldown ended. "
                        f"you can freely catch pokemon again now! "
                        f"good luck!"
                    )


                    try:

                        await member.send(
                            cooldown_end_text
                        )

                    except Exception:

                        print(
                            f"⚠️ Could not DM {member.name}"
                        )


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
                    f"for {user_id}: {e}"
                )


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


# ============================================================
# START BOT
# ============================================================

if __name__ == "__main__":

    web_thread = threading.Thread(
        target=run_web,
        daemon=True
    )

    web_thread.start()


    bot.run(TOKEN)

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
# POKÉTWO CHANNELS
# ============================================================

CHANNELS_TO_WATCH = {
    "🌸・pokecord",
    "🌸・poketo-spawns",
    "🌸・spawn-hunt",
    "🌸・pokemon-hunt",
    "🌸・pokémon-wild",
}


# ============================================================
# DISCORD INTENTS
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


def add_cooldown(
    user_id: int,
    guild_id: int,
    channel_id: int,
    minutes: int
):
    end_time = (
        datetime.now(timezone.utc)
        + timedelta(minutes=minutes)
    )

    end_str = end_time.isoformat()

    with sqlite3.connect(DB_FILE) as conn:

        # Remove any old cooldown for this user/server.
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
                end_str
            )
        )


def get_expired_cooldowns():
    now = datetime.now(timezone.utc)

    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute(
            """
            SELECT user_id, guild_id, channel_id, end_time
            FROM cooldowns
            """
        ).fetchall()

    expired = []

    for user_id, guild_id, channel_id, end_time_str in rows:

        try:
            end_time = datetime.fromisoformat(end_time_str)

            if end_time <= now:
                expired.append(
                    (
                        user_id,
                        guild_id,
                        channel_id
                    )
                )

        except ValueError:
            # Bad database entry — treat it as expired.
            expired.append(
                (
                    user_id,
                    guild_id,
                    channel_id
                )
            )

    return expired


def remove_cooldown(
    user_id: int,
    guild_id: int
):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            """
            DELETE FROM cooldowns
            WHERE user_id = ? AND guild_id = ?
            """,
            (user_id, guild_id)
        )


# ============================================================
# POKÉTWO CATCH DETECTION
# ============================================================

def get_message_text(message: discord.Message) -> str:
    """
    Collect normal message content and embed text.

    Pokétwo often puts catch information inside an embed,
    so checking only message.content isn't reliable.
    """

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


def find_winner(
    message: discord.Message
):
    """
    Try to identify the person

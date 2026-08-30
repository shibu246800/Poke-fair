import os
import sqlite3
import asyncio
import threading
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
    c.execute('''CREATE TABLE IF NOT EXISTS cooldowns 
                 (user_id INTEGER, guild_id INTEGER, channel_id INTEGER, end_time TEXT)''')
    conn.commit()
    conn.close()

init_db()

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True

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

    if message.author.id == POKETWO_BOT_ID and message.channel.name in CHANNELS_TO_WATCH:
        if "Congratulations" in message.content and "caught a" in message.content:
            if message.mentions:
                winner = message.mentions[0] # Grab the specific user
                guild = message.guild
                
                role = discord.utils.get(guild.roles, name=COOLDOWN_ROLE_NAME)
                if not role:
                    print(f"❌ Error: '{COOLDOWN_ROLE_NAME}' role not found.")
                    return

                end_time = datetime.utcnow() + timedelta(minutes=COOLDOWN_MINUTES)
                end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')

                # Save to database (Includes channel tracking)
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("DELETE FROM cooldowns WHERE user_id=? AND guild_id=?", (winner.id, guild.id))
                c.execute("INSERT INTO cooldowns VALUES (?, ?, ?, ?)", (winner.id, guild.id, message.channel.id, end_time_str))
                conn.commit()
                conn.close()

                try:
                    # Give role right away
                    await winner.add_roles(role)
                    # Send custom text message in same channel right away
                    await message.channel.send(f"{winner.mention} congrats for getting the Pokémon!! you are held down to cooldown now. your next allowance is in {COOLDOWN_MINUTES} minutes.")
                except discord.Forbidden:
                    await message.channel.send("❌ **PokéFair Error**: Cannot manage roles. Drag my role *above* the cooldown role in Server Settings!")

    await bot.process_commands(message)

@tasks.loop(seconds=10)
async def check_cooldowns():
    await bot.wait_until_ready()
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id, guild_id, channel_id FROM cooldowns WHERE end_time <= ?", (now_str,))
    expired = c.fetchall()

    for user_id, guild_id, channel_id in expired:
        guild = bot.get_guild(guild_id)
        if guild:
            try:
                member = guild.get_member(user_id) or await guild.fetch_member(user_id)
                role = discord.utils.get(guild.roles, name=COOLDOWN_ROLE_NAME)
                channel = guild.get_channel(channel_id)
                
                if member and role and role in member.roles:
                    # Remove the role
                    await member.remove_roles(role)
                    
                    cooldown_end_text = f"{member.mention} your cooldown ended. you can freely catch pokemon again now! good luck!"
                    
                    # 1. Mention in DM
                    try:
                        await member.send(cooldown_end_text)
                    except Exception:
                        print(f"Could not send DM to {member.name}")
                        
                    # 2. Mention in the #chat channel where they caught it
                    if channel:
                        await channel.send(cooldown_end_text)
                        
            except Exception as e:
                print(f"Could not clear cooldown for user {user_id}: {e}")
        
        c.execute("DELETE FROM cooldowns WHERE user_id=? AND guild_id=?", (user_id, guild_id))
        conn.commit()

    conn.close()

if __name__ == "__main__":
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()
    bot.run(TOKEN)

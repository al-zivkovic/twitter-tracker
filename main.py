import os
import asyncio
import discord
from discord.ext import commands, tasks
import tweepy
import aiosqlite
from dotenv import load_dotenv

load_dotenv()

# Initialize Discord bot
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Initialize Twitter client
twitter_client = tweepy.Client(bearer_token=os.getenv("TWITTER_BEARER_TOKEN"))

# Database setup
async def init_db():
    async with aiosqlite.connect("twitter_bot.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS twitter_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                channel_id INTEGER,
                twitter_handle TEXT,
                twitter_user_id INTEGER,
                last_tweet_id INTEGER
            )
        """)
        await db.commit()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await init_db()
    check_tweets.start()

# Slash command to add Twitter account
@bot.command(name="addaccount", description="Add a Twitter account to track")
async def addaccount(ctx, twitter_handle: str, channel: discord.TextChannel):
    try:
        user = twitter_client.get_user(username=twitter_handle)
        if not user.data:
            await ctx.respond("Twitter account not found", ephemeral=True)
            return
        
        async with aiosqlite.connect("twitter_bot.db") as db:
            await db.execute("""
                INSERT INTO twitter_accounts 
                (guild_id, channel_id, twitter_handle, twitter_user_id, last_tweet_id)
                VALUES (?, ?, ?, ?, ?)
            """, (ctx.guild.id, channel.id, twitter_handle, user.data.id, None))
            await db.commit()
        
        await ctx.respond(f"Now tracking @{twitter_handle} in {channel.mention}", ephemeral=True)
    except Exception as e:
        await ctx.respond(f"Error: {str(e)}", ephemeral=True)

@bot.slash_command(name="ping", description="Test command")
async def ping(ctx):
    await ctx.respond("Pong!")

# Background task to check tweets
@tasks.loop(minutes=5)
async def check_tweets():
    async with aiosqlite.connect("twitter_bot.db") as db:
        cursor = await db.execute("SELECT * FROM twitter_accounts")
        accounts = await cursor.fetchall()

        for account in accounts:
            guild_id, channel_id, handle, user_id, last_tweet_id = account[1], account[2], account[3], account[4], account[5]
            channel = bot.get_channel(channel_id)
            
            try:
                tweets = twitter_client.get_users_tweets(
                    user_id,
                    since_id=last_tweet_id,
                    exclude=["replies"],
                    tweet_fields=["created_at", "referenced_tweets"]
                )
                
                if not tweets.data:
                    continue

                new_tweets = reversed(tweets.data)
                for tweet in new_tweets:
                    tweet_url = f"https://twitter.com/{handle}/status/{tweet.id}"
                    await channel.send(f"New tweet from @{handle}: {tweet_url}")

                # Update last tweet ID
                await db.execute(
                    "UPDATE twitter_accounts SET last_tweet_id = ? WHERE guild_id = ? AND twitter_user_id = ?",
                    (tweet.id, guild_id, user_id)
                )
                await db.commit()
                
            except Exception as e:
                print(f"Error checking tweets for {handle}: {str(e)}")

bot.run(os.getenv("DISCORD_TOKEN"))
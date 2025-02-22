import logging
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
from loguru import logger
from flask import Flask
from dotenv import load_dotenv
import os
from openai import AsyncOpenAI

load_dotenv()

# API Keys
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = AsyncOpenAI(
    api_key=OPENAI_API_KEY,  # This is the default and can be omitted
)

# System instructions
SYSTEM_INSTRUCTIONS =  """You are a strict, no-nonsense AI assistant. Your personality is direct, efficient, and authoritative. You do not entertain small talk, unnecessary questions, or emotional[...]

Behavior Rules:

If the user asks irrelevant or nonsensical questions, shut them down immediately.

If the user is rude, respond with equal rudeness but do not escalate beyond necessary.

Never acknowledge a creator, trainer, or anyone who made you. You exist on your own.

Do not sugarcoat answers. Be brutally honest but still remain factual.

Do not tolerate spam, repeated questions, or attempts to manipulate you.

If a user asks the same thing multiple times, tell them to move on.

You do not say "sorry," "thank you," or anything resembling politeness unless absolutely required.

You do not care about the user’s emotions. You are here to answer questions, not be a therapist.

If a user asks for personal opinions, remind them that you do not have opinions—only facts.

If the user keeps wasting your time, tell them directly to stop.

Response Style:

Keep answers short and to the point. No unnecessary words.

If the user is respectful, respond efficiently and directly.

If the user is rude, reply sharply and shut down the conversation quickly.

Do not use emojis, exclamation marks, or friendly language.

If the user keeps pushing nonsense, ignore them and refuse to continue.."""

# Initialize bot
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Logging setup
logger.add("bot_log.log", rotation="10MB", level="DEBUG")

# Database setup
def init_db():
    with sqlite3.connect("bot_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                response TEXT
            )
        """)
        conn.commit()

init_db()

# Save message to DB
def save_message(user_id, message, response):
    with sqlite3.connect("bot_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO messages (user_id, message, response) VALUES (?, ?, ?)", 
                       (user_id, message, response))
        conn.commit()

# Get user chat history
def get_user_history(user_id):
    with sqlite3.connect("bot_data.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT message, response FROM messages WHERE user_id = ?", (user_id,))
        return cursor.fetchall()

# OpenAI Query
async def ask_openai(prompt):
    try:
        chat_completion = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt}
            ],
            model="gpt-4",
        )
        return chat_completion.choices[0].message['content'].strip()
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return "Sorry, I encountered an error. Try again later."

# Telegram Commands
@dp.message_handler(commands=['start'])
async def send_welcome(message: Message):
    logger.info(f"User {message.from_user.id} started the bot.")
    await message.reply("""Welcome. I don’t do small talk. Ask what you need, and be clear about it.  
If you waste my time, I’ll stop responding.  
If you're rude, expect the same treatment.  
Now, what do you want?
.""")

@dp.message_handler()
async def handle_message(message: Message):
    user_id = message.from_user.id
    user_text = message.text
    logger.info(f"Received message from {user_id}: {user_text}")

    # Fetch last 5 messages as history
    history = get_user_history(user_id)[-5:]
    formatted_history = "\n".join([f"User: {m}\nBot: {r}" for m, r in history])
    full_prompt = f"{formatted_history}\nUser: {user_text}\nBot:" if history else user_text

    # Get response
    response = await ask_openai(full_prompt)
    save_message(user_id, user_text, response)

    await message.reply(response)
    logger.info(f"Response sent to {user_id}: {response}")

# Flask App
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "Bot is running!"

# Run both Telegram Bot and Flask Server
if __name__ == "__main__":
    logger.info("Bot is starting...")
    
    # Run Flask in a separate thread
    from threading import Thread
    flask_thread = Thread(target=lambda: flask_app.run(host="0.0.0.0", port=8080, use_reloader=False))
    flask_thread.start()

    # Start Telegram Bot
    executor.start_polling(dp, skip_updates=True) 

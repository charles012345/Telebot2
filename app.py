import logging
import sqlite3
import openai
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
from loguru import logger
from flask import Flask, request
from dotenv import load_dotenv
import os
from filelock import FileLock, Timeout

load_dotenv()

# Telegram and OpenAI API keys
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# System instructions
SYSTEM_INSTRUCTIONS = "You are an AI-powered assistant. Be helpful and concise."

# Initialize bot and dispatcher
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Setup logging
logger.add("bot_log.log", rotation="10MB", level="DEBUG")

# Database setup
def init_db():
    conn = sqlite3.connect("bot_data.db")
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
    conn.close()

init_db()

# Function to store messages in database
def save_message(user_id, message, response):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (user_id, message, response) VALUES (?, ?, ?)", 
                   (user_id, message, response))
    conn.commit()
    conn.close()

# Function to retrieve user history
def get_user_history(user_id):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT message, response FROM messages WHERE user_id = ?", (user_id,))
    history = cursor.fetchall()
    conn.close()
    return history

# OpenAI query function
async def ask_openai(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "system", "content": SYSTEM_INSTRUCTIONS},
                      {"role": "user", "content": prompt}]
        )
        return response['choices'][0]['message']['content'].strip()
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return "Sorry, I encountered an error. Try again later."

# Command handler
@dp.message_handler(commands=['start'])
async def send_welcome(message: Message):
    logger.info(f"User {message.from_user.id} started the bot.")
    await message.reply("Hello! Send me a message, and I'll respond using OpenAI.")

# Message handler
@dp.message_handler()
async def handle_message(message: Message):
    user_id = message.from_user.id
    user_text = message.text
    logger.info(f"Received message from {user_id}: {user_text}")

    # Fetch previous history
    history = get_user_history(user_id)
    formatted_history = "\n".join([f"User: {m}\nBot: {r}" for m, r in history[-5:]])
    full_prompt = f"{formatted_history}\nUser: {user_text}\nBot:" if history else user_text

    # Get OpenAI response
    response = await ask_openai(full_prompt)
    save_message(user_id, user_text, response)
    response_text = f"Message from user: {user_id}\n{response}"
    
    await message.reply(response_text)
    logger.info(f"Response sent to {user_id}: {response}")

# Flask application
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "Bot is running!"

if __name__ == "__main__":
    lock = FileLock("/tmp/bot.lock")
    try:
        with lock.acquire(timeout=10):
            logger.info("Bot is starting...")
            loop = asyncio.get_event_loop()
            loop.create_task(executor.start_polling(dp, skip_updates=True))
            flask_app.run(host="0.0.0.0", port=8080)
    except Timeout:
        logger.error("Another instance of the bot is already running.")
    except Exception as e:
        logger.error(f"Failed to start Flask server: {e}")

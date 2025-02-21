import logging
import sqlite3
import openai
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
from loguru import logger
from flask import Flask
from dotenv import load_dotenv
import os

load_dotenv()

# API Keys
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# System instructions
SYSTEM_INSTRUCTIONS = "You are an AI-powered assistant. Be helpful and concise."

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
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt}
            ]
        )
        return response['choices'][0]['message']['content'].strip()
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return "Sorry, I encountered an error. Try again later."

# Telegram Commands
@dp.message_handler(commands=['start'])
async def send_welcome(message: Message):
    logger.info(f"User {message.from_user.id} started the bot.")
    await message.reply("Hello! Send me a message, and I'll respond using OpenAI.")

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

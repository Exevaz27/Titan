
import asyncio
import sys
import os
from dotenv import load_dotenv

load_dotenv('/home/exevaz27/titan/.env')
sys.path.insert(0, '/home/exevaz27/titan')

from integrations.telegram_bot import TelegramBotService
import httpx

async def run_test():
    bot = TelegramBotService()
    bot.token = os.getenv("TELEGRAM_BOT_TOKEN")
    bot.allowed_user_id = os.getenv("TELEGRAM_ALLOWED_USER_ID")
    bot.api_url = f"https://api.telegram.org/bot{bot.token}"
    bot.file_url = f"https://api.telegram.org/file/bot{bot.token}"
    bot.client = httpx.AsyncClient(timeout=30.0)

    chat_id = int(bot.allowed_user_id)
    print(f"Testing _handle_text_message with from_voice=True for chat_id={chat_id}...")

    # Test processing a voice message
    test_text = "hola titán cómo estás"
    await bot._handle_text_message(chat_id, test_text, from_voice=True)
    print("Test executed successfully!")

    await bot.client.aclose()

asyncio.run(run_test())

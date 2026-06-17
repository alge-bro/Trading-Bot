import os
from dotenv import load_dotenv

load_dotenv()

ALPACA_API_KEY    = os.environ.get('ALPACA_API_KEY', '')
ALPACA_SECRET_KEY = os.environ.get('ALPACA_SECRET_KEY', '')
ALPACA_ENDPOINT   = os.environ.get('ALPACA_ENDPOINT', 'https://paper-api.alpaca.markets/v2')

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID   = os.environ.get('TELEGRAM_CHAT_ID', '')

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

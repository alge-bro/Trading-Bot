# notifications.py
import requests
import config

def send_sms(message):
    """
    Sends a Telegram message to your chat using your bot.
    Replaces Twilio SMS functionality.
    """
    try:
        if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
            print("🚫 Telegram credentials missing. Skipping message.")
            return

        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": message
        }

        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print(f"✅ Telegram message sent: {message}")
        else:
            print(f"❌ Telegram error [{response.status_code}]: {response.text}")

    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

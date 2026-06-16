#test_telegram.py
import requests
import config

def test_telegram_message():
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": "✅ Telegram is alive and sending! 🚀"
    }

    response = requests.post(url, data=payload)

    if response.status_code == 200:
        print("✅ Test message sent successfully!")
    else:
        print(f"❌ Failed to send message: {response.status_code} - {response.text}")

if __name__ == "__main__":
    test_telegram_message()

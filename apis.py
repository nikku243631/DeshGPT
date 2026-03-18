import os
import requests
from datetime import datetime
import pytz

def get_ai_response(message):
    try:
        msg = message.lower()

        # Basic replies
        if msg in ["hi", "hello", "hey"]:
            return "Hello bhai 😄 kaise ho?"

        # Time (India)
        if "time" in msg:
            india = pytz.timezone('Asia/Kolkata')
            return datetime.now(india).strftime("Abhi India time hai: %H:%M:%S")

        # Date
        if "date" in msg:
            india = pytz.timezone('Asia/Kolkata')
            return datetime.now(india).strftime("Aaj ki date hai: %d-%m-%Y")

        # Gemini API
        gemini_key = os.getenv("GEMINI_API_KEY")

        if gemini_key:
            url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={gemini_key}"

            headers = {
                "Content-Type": "application/json"
            }

            data = {
                "contents": [
                    {
                        "parts": [{"text": message}]
                    }
                ]
            }

            res = requests.post(url, headers=headers, json=data)
            result = res.json()

            try:
                return result["candidates"][0]["content"]["parts"][0]["text"]
            except:
                return "API se response nahi aaya bhai 😅"

        return "API key nahi mili bhai 😅"

    except Exception as e:
        return "Error: " + str(e)

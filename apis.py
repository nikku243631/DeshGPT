import os
import requests
from datetime import datetime

def get_ai_response(message):
    try:
        if message.lower() in ["hi", "hello"]:
            return "Hello bhai 😄 kaise ho?"

        if "time" in message.lower():
            return datetime.now().strftime("Abhi time hai: %H:%M:%S")

        # Gemini API
        gemini_key = os.getenv("GEMINI_API_KEY")

        if gemini_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={gemini_key}"
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{"parts": [{"text": message}]}]
            }

            res = requests.post(url, headers=headers, json=data)
            result = res.json()

            return result["candidates"][0]["content"]["parts"][0]["text"]

        return "API key nahi mili bhai 😅"

    except Exception as e:
        return "Error: " + str(e)

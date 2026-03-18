import requests
import datetime
import wikipedia
import os
from bs4 import BeautifulSoup
from groq import Groq
import google.generativeai as genai

# API KEYS
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Setup
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

def ai_reply(msg):
    try:
        response = groq_client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": msg}]
        )
        return response.choices[0].message.content
    except:
        try:
            model = genai.GenerativeModel("gemini-pro")
            res = model.generate_content(msg)
            return res.text
        except:
            return "AI error"

def get_ai_response(msg):

    msg_lower = msg.lower()

    # Time
    if "time" in msg_lower:
        return datetime.datetime.now().strftime("⏰ %H:%M:%S")

    # Date
    if "date" in msg_lower or "day" in msg_lower:
        return datetime.datetime.now().strftime("📅 %A, %d %B %Y")

    # Wikipedia
    if "who is" in msg_lower or "what is" in msg_lower:
        try:
            return wikipedia.summary(msg, sentences=2)
        except:
            pass

    # Web Search
    try:
        url = f"https://duckduckgo.com/html/?q={msg}"
        res = requests.get(url)
        soup = BeautifulSoup(res.text, "html.parser")
        results = soup.find_all("a", class_="result__a", limit=3)

        if results:
            output = "🔎 Top Results:\n"
            for r in results:
                output += "- " + r.text + "\n"
            return output
    except:
        pass

    # AI fallback
    return ai_reply(msg)

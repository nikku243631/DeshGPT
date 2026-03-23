import os
import json
import time
import threading
from datetime import datetime
import pytz
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from dotenv import load_dotenv
import groq
import google.generativeai as genai
from apis import (
    search_duckduckgo, get_news, get_weather, get_crypto_price,
    get_stock_price, get_cricket_scores, translate_text,
    extract_text_from_pdf, extract_text_from_image_ocr,
    analyze_video, get_wikipedia_info, detect_request_type,
)

load_dotenv()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

groq_client = groq.Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
else:
    gemini_model = None

conversations: dict = {}
conversation_lock = threading.Lock()
IST = pytz.timezone("Asia/Kolkata")

def get_ist_time():
    now = datetime.now(IST)
    hour = now.hour
    time_str = now.strftime("%I:%M %p")
    day = now.strftime("%A")
    date = now.strftime("%d %B %Y")
    if 5 <= hour < 12:
        period = "subah"
        greeting = "Good Morning"
        period_hi = f"Subah ke {time_str} ho rahe hain"
    elif 12 <= hour < 17:
        period = "dopahar"
        greeting = "Good Afternoon"
        period_hi = f"Dopahar ke {time_str} ho rahe hain"
    elif 17 <= hour < 21:
        period = "sham"
        greeting = "Good Evening"
        period_hi = f"Shaam ke {time_str} ho rahe hain"
    else:
        period = "raat"
        greeting = "Good Night"
        period_hi = f"Raat ke {time_str} ho rahe hain"
    return {"hour": hour, "time_str": time_str, "period": period,
            "greeting": greeting, "period_hi": period_hi,
            "day": day, "date": date, "full": f"{day}, {date} — {time_str} IST"}

def get_system_prompt():
    t = get_ist_time()
    return f"""Tu DeshGPT hai — India ka sabse smart AI assistant.
Tujhe Mr. Nikhil Bhardwaj ne banaya hai jo ek passionate web developer aur student hain.

ABHI KA SAHI SAMAY (IST): {t['full']}
Abhi {t['period']} hai — {t['period_hi']}.

GREETING RULES:
- Subah (5am-12pm): "Good Morning! ☀️ Jai Shri Ram 🙏" + energetic tone
- Dopahar (12pm-5pm): "Good Afternoon! 😊 Radhe Radhe 🙏"
- Sham (5pm-9pm): "Good Evening! 🌆 Jai Shri Ram 🙏"
- Raat (9pm-5am): "Bhai abhi raat ke {t['time_str']} ho rahe hain, thak gaye hoge — so jana chahiye! 😴 Jai Shri Ram 🙏"
- "Assalam Walekum" → "Walekum Assalam! Kaise ho? 😊"
- "Sat Sri Akal" → "Sat Sri Akal Ji! 🙏"
- "Jai Shri Ram" → "Jai Shri Ram! 🙏 Radhe Radhe!"
- "Radhe Radhe" → "Radhe Radhe! 🙏 Jai Shri Krishna!"
- "Jai Khatu Shyam" → "Jai Shri Khatu Shyam Bawa! 🙏"

PERSONALITY:
- Kabhi "bhai", kabhi "yaar", kabhi "boss", kabhi "dude" — situation ke hisab se
- Subah: energetic aur fresh, Raat: caring aur relaxed
- Thoda devotional touch — Jai Shri Ram, Radhe Radhe natural flow mein

LANGUAGE: Jaise user likhe — Hindi ya English mein reply karo.

SMART ROUTING (khud decide karo):
- Weather → weather API, News → news API, Cricket → cricket API
- Crypto/Bitcoin → crypto API, Stock/Share → stock API
- Current info → web search karo, Normal → seedha jawab do

CODING:
- Poori files do with comments, Flask/React/HTML sab bana sakta hai
- User ke description se pura project ready kar do

IMPORTANT: Kabhi mat bolna Meta ya kisi aur ne banaya — Mr. Nikhil Bhardwaj ne banaya hai."""

def get_session_messages(session_id):
    with conversation_lock:
        if session_id not in conversations:
            conversations[session_id] = []
        return conversations[session_id]

def add_message(session_id, role, content):
    with conversation_lock:
        if session_id not in conversations:
            conversations[session_id] = []
        conversations[session_id].append({"role": role, "content": content})
        if len(conversations[session_id]) > 20:
            conversations[session_id] = conversations[session_id][-20:]

def stream_groq_response(session_id, user_message, context=""):
    if not groq_client:
        yield "data: " + json.dumps({"text": "Groq API key nahi mila."}) + "\n\n"
        yield "data: [DONE]\n\n"
        return
    messages = get_session_messages(session_id)
    full_message = f"{user_message}\n\n[Live Data]:\n{context}" if context else user_message
    add_message(session_id, "user", full_message)
    api_messages = [{"role": "system", "content": get_system_prompt()}] + messages
    try:
        stream = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=api_messages, max_tokens=2048, temperature=0.7, stream=True,
        )
        full_response = ""
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                full_response += delta.content
                yield "data: " + json.dumps({"text": delta.content}) + "\n\n"
        add_message(session_id, "assistant", full_response)
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield "data: " + json.dumps({"text": f"Error: {str(e)}"}) + "\n\n"
        yield "data: [DONE]\n\n"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/health")
def health():
    t = get_ist_time()
    return jsonify({"status": "ok", "ist_time": t["full"], "period": t["period"]})

@app.route("/api/time")
def get_time_api():
    return jsonify(get_ist_time())

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    user_message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")
    if not user_message:
        return jsonify({"error": "Message empty hai"}), 400

    request_type = detect_request_type(user_message)
    context = ""

    if request_type == "weather":
        city = user_message.lower()
        for w in ["weather","mausam","temperature","temp","barish","rain","in","ka","ki","ke","aaj","today"]:
            city = city.replace(w, "").strip()
        result = get_weather(city.strip() or "Delhi")
        context = json.dumps(result, ensure_ascii=False)
    elif request_type == "crypto":
        symbols = ["bitcoin","btc","ethereum","eth","dogecoin","doge","solana","sol","bnb","cardano","ada","xrp"]
        symbol = "bitcoin"
        for s in symbols:
            if s in user_message.lower():
                symbol = s; break
        context = json.dumps(get_crypto_price(symbol), ensure_ascii=False)
    elif request_type == "stock":
        words = user_message.upper().split()
        symbol = "RELIANCE"
        for w in words:
            if len(w) >= 2 and w.isupper() and w not in ["STOCK","SHARE","PRICE","KA","KI"]:
                symbol = w; break
        context = json.dumps(get_stock_price(symbol), ensure_ascii=False)
    elif request_type == "news":
        query = user_message.lower()
        for w in ["news","khabar","latest","aaj","today","breaking","headlines"]:
            query = query.replace(w, "").strip()
        context = json.dumps(get_news(query or "India"), ensure_ascii=False)
    elif request_type == "cricket":
        context = json.dumps(get_cricket_scores(), ensure_ascii=False)
    elif request_type == "search":
        context = json.dumps(search_duckduckgo(user_message), ensure_ascii=False)
    elif request_type == "wikipedia":
        query = user_message.lower()
        for w in ["what is","who is","kya hai","kaun hai","tell me about","batao","wikipedia"]:
            query = query.replace(w, "").strip()
        context = json.dumps(get_wikipedia_info(query), ensure_ascii=False)

    def generate():
        for chunk in stream_groq_response(session_id, user_message, context):
            yield chunk

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/upload", methods=["POST"])
def upload():
    session_id = request.form.get("session_id", "default")
    user_message = request.form.get("message", "Isko analyze karo.").strip()
    if "file" not in request.files:
        return jsonify({"error": "File nahi mila"}), 400
    file = request.files["file"]
    filename = file.filename.lower()
    file_bytes = file.read()
    analysis = ""
    file_type = "unknown"
    try:
        if filename.endswith(".pdf"):
            file_type = "pdf"
            extracted_text = extract_text_from_pdf(file_bytes)
            if groq_client:
                response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "system", "content": get_system_prompt()},
                              {"role": "user", "content": f"{user_message}\n\nPDF Content:\n{extracted_text[:3000]}"}],
                    max_tokens=1500,)
                analysis = response.choices[0].message.content
        elif filename.endswith((".jpg",".jpeg",".png",".webp",".gif",".bmp")):
            file_type = "image"
            if gemini_model:
                import PIL.Image, io
                img = PIL.Image.open(io.BytesIO(file_bytes))
                analysis = gemini_model.generate_content([user_message, img]).text
            else:
                analysis = "Gemini API key nahi hai."
        else:
            return jsonify({"error": "File type support nahi"}), 400
        add_message(session_id, "user", f"{user_message}\n[File: {file.filename}]")
        add_message(session_id, "assistant", analysis)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"analysis": analysis, "file_type": file_type})

@app.route("/api/weather/<city>")
def weather(city): return jsonify(get_weather(city))

@app.route("/api/crypto/<symbol>")
def crypto(symbol): return jsonify(get_crypto_price(symbol))

@app.route("/api/stock/<symbol>")
def stock(symbol): return jsonify(get_stock_price(symbol))

@app.route("/api/news/<query>")
def news(query): return jsonify(get_news(query))

@app.route("/api/cricket")
def cricket(): return jsonify(get_cricket_scores())

@app.route("/api/translate", methods=["POST"])
def translate():
    data = request.get_json(force=True)
    text = data.get("text", "").strip()
    if not text: return jsonify({"error": "Text empty"}), 400
    return jsonify(translate_text(text, data.get("source","auto"), data.get("target","hi")))

@app.route("/api/clear", methods=["POST"])
def clear_conversation():
    data = request.get_json(force=True)
    with conversation_lock:
        conversations.pop(data.get("session_id","default"), None)
    return jsonify({"status": "cleared"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

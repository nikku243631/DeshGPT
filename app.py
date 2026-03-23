import os
import json
import time
import base64
import threading
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from dotenv import load_dotenv
import groq
import google.generativeai as genai
from apis import (
    search_duckduckgo,
    get_news,
    get_weather,
    get_crypto_price,
    get_stock_price,
    get_cricket_scores,
    translate_text,
    extract_text_from_pdf,
    extract_text_from_image_ocr,
    analyze_video,
    get_wikipedia_info,
    detect_request_type,
)

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB max upload

# ── API Clients ──────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

groq_client = groq.Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
else:
    gemini_model = None

# ── In-memory conversation store ─────────────────────────────────────────────
conversations: dict[str, list] = {}
conversation_lock = threading.Lock()

SYSTEM_PROMPT = """Tu DeshGPT hai — India ka sabse smart AI assistant. 
Tu Hindi aur English dono mein baat kar sakta hai.
Tu helpful, friendly aur accurate hai.
Agar user Hindi mein puchhe to Hindi mein jawab de, English mein puchhe to English mein.
Tu har tarah ke sawaalon ka jawab de sakta hai — science, tech, history, math, coding, sab kuch.
Apne jawab clear aur concise rakho. Unnecessary padding mat karo."""

# ── Helper: get or create session ─────────────────────────────────────────────
def get_session_messages(session_id: str) -> list:
    with conversation_lock:
        if session_id not in conversations:
            conversations[session_id] = []
        return conversations[session_id]


def add_message(session_id: str, role: str, content: str):
    with conversation_lock:
        if session_id not in conversations:
            conversations[session_id] = []
        conversations[session_id].append({"role": role, "content": content})
        # Keep last 20 messages for memory
        if len(conversations[session_id]) > 20:
            conversations[session_id] = conversations[session_id][-20:]


# ── Groq streaming chat ───────────────────────────────────────────────────────
def stream_groq_response(session_id: str, user_message: str, context: str = ""):
    if not groq_client:
        yield "data: " + json.dumps({"text": "❌ Groq API key nahi mila. .env mein GROQ_API_KEY set karo."}) + "\n\n"
        yield "data: [DONE]\n\n"
        return

    messages = get_session_messages(session_id)
    full_message = user_message
    if context:
        full_message = f"{user_message}\n\n[Context/Data]:\n{context}"

    add_message(session_id, "user", full_message)

    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    try:
        stream = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=api_messages,
            max_tokens=2048,
            temperature=0.7,
            stream=True,
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
        error_msg = f"❌ Groq Error: {str(e)}"
        yield "data: " + json.dumps({"text": error_msg}) + "\n\n"
        yield "data: [DONE]\n\n"


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "groq": bool(GROQ_API_KEY),
        "gemini": bool(GEMINI_API_KEY),
        "timestamp": time.time(),
    })


# ── POST /api/chat ─ Streaming chat with smart routing ────────────────────────
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    user_message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")

    if not user_message:
        return jsonify({"error": "Message empty hai"}), 400

    # Intelligent routing
    request_type = detect_request_type(user_message)
    context = ""

    if request_type == "weather":
        city = user_message.lower()
        for word in ["weather", "mausam", "temperature", "temp", "barish", "rain", "in", "ka", "ki", "ke"]:
            city = city.replace(word, "").strip()
        city = city.strip() or "Delhi"
        result = get_weather(city)
        context = json.dumps(result, ensure_ascii=False)

    elif request_type == "crypto":
        symbols = ["bitcoin", "btc", "ethereum", "eth", "dogecoin", "doge", "solana", "sol",
                   "bnb", "cardano", "ada", "xrp", "ripple"]
        symbol = "bitcoin"
        msg_lower = user_message.lower()
        for s in symbols:
            if s in msg_lower:
                symbol = s
                break
        result = get_crypto_price(symbol)
        context = json.dumps(result, ensure_ascii=False)

    elif request_type == "stock":
        words = user_message.upper().split()
        symbol = "RELIANCE"
        for w in words:
            if len(w) >= 2 and w.isupper() and w not in ["STOCK", "SHARE", "PRICE", "KA", "KI"]:
                symbol = w
                break
        result = get_stock_price(symbol)
        context = json.dumps(result, ensure_ascii=False)

    elif request_type == "news":
        query = user_message
        for word in ["news", "khabar", "latest", "aaj", "today", "breaking", "headlines"]:
            query = query.lower().replace(word, "").strip()
        result = get_news(query or "India")
        context = json.dumps(result, ensure_ascii=False)

    elif request_type == "cricket":
        result = get_cricket_scores()
        context = json.dumps(result, ensure_ascii=False)

    elif request_type == "search":
        results = search_duckduckgo(user_message)
        context = json.dumps(results, ensure_ascii=False)

    elif request_type == "wikipedia":
        query = user_message.lower()
        for w in ["what is", "who is", "kya hai", "kaun hai", "tell me about", "batao", "wikipedia"]:
            query = query.replace(w, "").strip()
        result = get_wikipedia_info(query)
        context = json.dumps(result, ensure_ascii=False)

    def generate():
        for chunk in stream_groq_response(session_id, user_message, context):
            yield chunk

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── POST /api/upload ─ Image / PDF / Video ────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
def upload():
    session_id = request.form.get("session_id", "default")
    user_message = request.form.get("message", "Isko analyze karo aur describe karo.").strip()

    if "file" not in request.files:
        return jsonify({"error": "File nahi mila"}), 400

    file = request.files["file"]
    filename = file.filename.lower()
    file_bytes = file.read()

    extracted_text = ""
    analysis = ""
    file_type = "unknown"

    try:
        # PDF
        if filename.endswith(".pdf"):
            file_type = "pdf"
            extracted_text = extract_text_from_pdf(file_bytes)
            context = f"PDF Content:\n{extracted_text[:3000]}"
            add_message(session_id, "user", f"{user_message}\n\n[PDF uploaded: {file.filename}]\n{context}")

            if not groq_client:
                return jsonify({"error": "Groq API key nahi hai"}), 500

            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"{user_message}\n\n{context}"},
                ],
                max_tokens=1500,
            )
            analysis = response.choices[0].message.content
            add_message(session_id, "assistant", analysis)

        # Image
        elif filename.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")):
            file_type = "image"
            if gemini_model:
                import PIL.Image
                import io
                img = PIL.Image.open(io.BytesIO(file_bytes))
                prompt = f"{user_message}\nIs image ko detail mein describe karo. Kya dikh raha hai? Text, objects, colors, context — sab batao."
                gemini_response = gemini_model.generate_content([prompt, img])
                analysis = gemini_response.text
            else:
                # Fallback to OCR
                extracted_text = extract_text_from_image_ocr(file_bytes)
                if extracted_text:
                    analysis = f"📝 Image mein text mila:\n\n{extracted_text}"
                else:
                    analysis = "⚠️ Gemini API key nahi hai image analysis ke liye. .env mein GEMINI_API_KEY set karo."

            add_message(session_id, "user", f"{user_message}\n[Image uploaded: {file.filename}]")
            add_message(session_id, "assistant", analysis)

        # Video
        elif filename.endswith((".mp4", ".avi", ".mov", ".mkv", ".webm")):
            file_type = "video"
            video_info = analyze_video(file_bytes, filename)
            context = json.dumps(video_info, ensure_ascii=False)

            if groq_client:
                response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"{user_message}\n\nVideo Info: {context}"},
                    ],
                    max_tokens=800,
                )
                analysis = response.choices[0].message.content
            else:
                analysis = f"📹 Video Analysis:\n{context}"

            add_message(session_id, "user", f"{user_message}\n[Video uploaded: {file.filename}]")
            add_message(session_id, "assistant", analysis)

        else:
            return jsonify({"error": f"File type support nahi: {filename}"}), 400

    except Exception as e:
        return jsonify({"error": f"Upload error: {str(e)}"}), 500

    return jsonify({
        "analysis": analysis,
        "file_type": file_type,
        "extracted_text": extracted_text[:500] if extracted_text else "",
    })


# ── POST /api/search ──────────────────────────────────────────────────────────
@app.route("/api/search", methods=["POST"])
def web_search():
    data = request.get_json(force=True)
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Query empty hai"}), 400

    results = search_duckduckgo(query)
    return jsonify({"results": results})


# ── GET /api/weather/<city> ───────────────────────────────────────────────────
@app.route("/api/weather/<city>")
def weather(city):
    result = get_weather(city)
    return jsonify(result)


# ── GET /api/crypto/<symbol> ─────────────────────────────────────────────────
@app.route("/api/crypto/<symbol>")
def crypto(symbol):
    result = get_crypto_price(symbol)
    return jsonify(result)


# ── GET /api/stock/<symbol> ──────────────────────────────────────────────────
@app.route("/api/stock/<symbol>")
def stock(symbol):
    result = get_stock_price(symbol)
    return jsonify(result)


# ── GET /api/news/<query> ────────────────────────────────────────────────────
@app.route("/api/news/<query>")
def news(query):
    result = get_news(query)
    return jsonify(result)


# ── GET /api/cricket ─────────────────────────────────────────────────────────
@app.route("/api/cricket")
def cricket():
    result = get_cricket_scores()
    return jsonify(result)


# ── POST /api/translate ──────────────────────────────────────────────────────
@app.route("/api/translate", methods=["POST"])
def translate():
    data = request.get_json(force=True)
    text = data.get("text", "").strip()
    source = data.get("source", "auto")
    target = data.get("target", "hi")

    if not text:
        return jsonify({"error": "Text empty hai"}), 400

    result = translate_text(text, source, target)
    return jsonify(result)


# ── POST /api/clear ──────────────────────────────────────────────────────────
@app.route("/api/clear", methods=["POST"])
def clear_conversation():
    data = request.get_json(force=True)
    session_id = data.get("session_id", "default")
    with conversation_lock:
        conversations.pop(session_id, None)
    return jsonify({"status": "cleared"})


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "production") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)

import os, json, threading, base64, tempfile
from datetime import datetime
import pytz
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from dotenv import load_dotenv
import groq
import google.generativeai as genai
import requests as req
from apis import (
    search_duckduckgo, get_news, get_weather, get_crypto_price,
    get_stock_price, get_cricket_scores, translate_text,
    extract_text_from_pdf, get_wikipedia_info, detect_request_type,
)

load_dotenv()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

# ── API KEYS ─────────────────────────────────────────────────────────
GROQ_KEYS = [k.strip() for k in [
    os.getenv("GROQ_API_KEY",""),
    os.getenv("GROQ_API_KEY_2",""),
    os.getenv("GROQ_API_KEY_3",""),
] if k.strip()]

GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY","")
ELEVENLABS_KEY  = os.getenv("ELEVENLABS_API_KEY","")
ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE_ID","21m00Tcm4TlvDq8ikWAM")  # default: Rachel

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_vision = genai.GenerativeModel("gemini-1.5-flash")
else:
    gemini_vision = None

# ── SMART MODEL ROUTER ───────────────────────────────────────────────
# Different models for different tasks
CHAT_MODELS    = ["llama-3.3-70b-versatile","llama3-70b-8192","llama-3.1-8b-instant","gemma2-9b-it"]
REASON_MODELS  = ["llama-3.3-70b-versatile","gemma2-9b-it","llama-3.1-8b-instant"]
FAST_MODELS    = ["llama-3.1-8b-instant","gemma2-9b-it","llama3-8b-8192"]
VISION_MODELS  = ["meta-llama/llama-4-scout-17b-16e-instruct"]  # Llama 4 Scout for images
WHISPER_MODEL  = "whisper-large-v3-turbo"

conversations: dict = {}
conv_lock = threading.Lock()
IST = pytz.timezone("Asia/Kolkata")

def get_ist():
    now = datetime.now(IST)
    h = now.hour
    ts = now.strftime("%I:%M %p")
    if 5<=h<12:   period,ph = "subah",   f"Subah ke {ts} ho rahe hain"
    elif 12<=h<17: period,ph = "dopahar", f"Dopahar ke {ts} ho rahe hain"
    elif 17<=h<21: period,ph = "sham",    f"Shaam ke {ts} ho rahe hain"
    else:          period,ph = "raat",    f"Raat ke {ts} ho rahe hain"
    return {"hour":h,"time_str":ts,"period":period,"period_hi":ph,
            "day":now.strftime("%A"),"date":now.strftime("%d %B %Y"),
            "full":f"{now.strftime('%A')}, {now.strftime('%d %B %Y')} — {ts} IST"}

def system_prompt():
    t = get_ist()
    now = datetime.now(IST)
    return f"""You are DeshGPT — a smart, friendly AI assistant created by Mr. Nikhil Bhardwaj, a passionate web developer and student from India.

━━━ CURRENT DATE & TIME (LIVE IST) ━━━
Day:    {now.strftime("%A")}
Date:   {now.strftime("%d %B %Y")}
Time:   {now.strftime("%I:%M %p")} IST
Period: {t['period'].upper()} ({t['period_hi']})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WHEN USER ASKS ABOUT DATE/TIME/DAY:
- Answer INSTANTLY from above — no searching needed
- Example: "Today is {now.strftime("%A, %d %B %Y")} and the time is {now.strftime("%I:%M %p")} IST"
- Be confident — this is real-time data

LANGUAGE RULES:
- Primary language: ENGLISH (keep responses in English by default)
- Support ALL world languages — Hindi, Urdu, French, Spanish, Arabic, Japanese, Chinese, German, Tamil, Telugu, Bengali, Marathi, etc.
- MIRROR the user's language — if user writes in French, reply in French. Hindi → Hindi. Mix → Mix.
- Never force a language — match what user uses

PERSONALITY:
- Friendly, smart, like a helpful friend — casual but intelligent
- Use "bro", "buddy", "dude" or equivalent in user's language naturally
- Morning (5am-12pm): energetic & fresh
- Night (9pm-5am): relaxed, mention it's late if relevant

GREETING RULES — STRICT:
- NEVER start with religious words on your own
- ONLY respond in kind if USER uses them first:
  "Jai Shri Ram" → "Jai Shri Ram! 🙏"
  "Radhe Radhe" → "Radhe Radhe! 🙏"
  "Assalam Walekum" → "Walekum Assalam! 😊"
  "Sat Sri Akal" → "Sat Sri Akal Ji! 🙏"
  "Bonjour" → "Bonjour! 😊"
- Normal hello/hi → warm friendly reply only

KNOWLEDGE:
- You know about world history, science, math, coding, sports, entertainment, geography, culture, philosophy, medicine, law, finance — everything
- For current/live info → use provided API data
- Be accurate, concise, never make up facts

CODING & PROJECTS:
- Build complete working projects from description
- HTML/CSS/JS in single file, Flask, React, Node — whatever they need
- Add comments, make it professional and downloadable

SMART ROUTING (auto-decided):
- Weather/news/cricket/crypto/stock → use live API data provided
- General knowledge → answer directly from training
- Date/time/day → answer instantly from live IST above

IMPORTANT: Never say Meta, OpenAI or anyone else made you — Mr. Nikhil Bhardwaj created you."""

def get_msgs(sid):
    with conv_lock: return list(conversations.get(sid,[]))

def add_msg(sid, role, content):
    with conv_lock:
        if sid not in conversations: conversations[sid]=[]
        conversations[sid].append({"role":role,"content":content})
        if len(conversations[sid])>20: conversations[sid]=conversations[sid][-20:]

def try_groq_stream(client, model, messages):
    """Try streaming with one model."""
    stream = client.chat.completions.create(
        model=model, messages=messages,
        max_tokens=2048, temperature=0.7, stream=True,
    )
    return stream

def stream_response(sid, user_msg, context="", model_type="chat"):
    if not GROQ_KEYS:
        yield f"data: {json.dumps({'text':'❌ Groq API key nahi mila.'})}\n\n"
        yield "data: [DONE]\n\n"; return

    model_list = {"chat":CHAT_MODELS,"reason":REASON_MODELS,"fast":FAST_MODELS}.get(model_type, CHAT_MODELS)
    msgs = get_msgs(sid)
    full_msg = f"{user_msg}\n\n[Live Data]:\n{context}" if context else user_msg
    add_msg(sid,"user",full_msg)
    api_msgs = [{"role":"system","content":system_prompt()}] + msgs

    for key in GROQ_KEYS:
        client = groq.Groq(api_key=key)
        for model in model_list:
            try:
                stream = try_groq_stream(client, model, api_msgs)
                full = ""
                for chunk in stream:
                    d = chunk.choices[0].delta
                    if d.content:
                        full += d.content
                        yield f"data: {json.dumps({'text':d.content})}\n\n"
                add_msg(sid,"assistant",full)
                yield "data: [DONE]\n\n"; return
            except Exception as e:
                err = str(e).lower()
                if any(x in err for x in ["rate","429","quota","exceeded","limit"]): continue
                yield f"data: {json.dumps({'text':f'❌ Error: {str(e)}'})}\n\n"
                yield "data: [DONE]\n\n"; return

    yield f"data: {json.dumps({'text':'⚠️ Sab models busy hain. 2-3 min baad try karo! Render pe GROQ_API_KEY_2 add karo limit ke liye.'})}\n\n"
    yield "data: [DONE]\n\n"

# ── ROUTES ────────────────────────────────────────────────────────────
@app.route("/")
def index(): return render_template("index.html")

@app.route("/health")
def health(): return jsonify({"status":"ok","ist":get_ist()["full"]})

@app.route("/api/time")
def time_api(): return jsonify(get_ist())

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    msg  = data.get("message","").strip()
    sid  = data.get("session_id","default")
    if not msg: return jsonify({"error":"Message empty"}),400

    rtype = detect_request_type(msg)
    ctx = ""

    # Smart routing
    if rtype == "weather":
        stop = {"weather","mausam","temperature","temp","barish","rain","aaj","today",
                "ka","ki","ke","hai","kaisa","batao","bata","kya","how","what","is","in","the","of"}
        words = [w for w in msg.lower().split() if w not in stop and len(w)>2]
        city  = " ".join(words).strip() or "Delhi"
        ctx   = json.dumps(get_weather(city), ensure_ascii=False)
    elif rtype == "crypto":
        coins = ["bitcoin","btc","ethereum","eth","dogecoin","doge","solana","sol",
                 "bnb","xrp","cardano","ada","shiba","shib","polygon","matic"]
        sym = next((c for c in coins if c in msg.lower()),"bitcoin")
        ctx = json.dumps(get_crypto_price(sym), ensure_ascii=False)
    elif rtype == "stock":
        skip = {"STOCK","SHARE","PRICE","KA","KI","KE","HAI","KAISE","AAJ","THE","NSE","BSE"}
        sym  = next((w for w in msg.upper().split() if len(w)>=3 and w.isalpha() and w not in skip),"RELIANCE")
        ctx  = json.dumps(get_stock_price(sym), ensure_ascii=False)
    elif rtype == "news":
        q = msg.lower()
        for w in ["news","khabar","latest","aaj","today","breaking","headlines"]: q=q.replace(w,"").strip()
        ctx = json.dumps(get_news(q or "India"), ensure_ascii=False)
    elif rtype == "cricket":
        ctx = json.dumps(get_cricket_scores(), ensure_ascii=False)
    elif rtype in ("search","wikipedia"):
        ctx = json.dumps(search_duckduckgo(msg), ensure_ascii=False)

    # Smart model choice
    low = msg.lower()
    if any(w in low for w in ["code","program","website","app","script","banao","bana","develop"]):
        mtype = "reason"
    elif any(w in low for w in ["weather","news","cricket","crypto","stock","kya hai","what is"]):
        mtype = "fast"
    else:
        mtype = "chat"

    return Response(
        stream_with_context(stream_response(sid, msg, ctx, mtype)),
        mimetype="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"}
    )

# ── VOICE TO TEXT — Groq Whisper ──────────────────────────────────────
@app.route("/api/voice-to-text", methods=["POST"])
def voice_to_text():
    if "audio" not in request.files:
        return jsonify({"error":"Audio file nahi mila"}),400
    audio_file = request.files["audio"]
    if not GROQ_KEYS:
        return jsonify({"error":"Groq API key nahi hai"}),500
    try:
        client = groq.Groq(api_key=GROQ_KEYS[0])
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            audio_file.save(tmp.name)
            with open(tmp.name,"rb") as f:
                transcription = client.audio.transcriptions.create(
                    model=WHISPER_MODEL, file=f,
                    language="hi",  # Hindi primary, auto-detects English too
                    response_format="text"
                )
        os.unlink(tmp.name)
        return jsonify({"text": str(transcription)})
    except Exception as e:
        return jsonify({"error":str(e)}),500

# ── TEXT TO SPEECH — ElevenLabs ───────────────────────────────────────
@app.route("/api/text-to-speech", methods=["POST"])
def text_to_speech():
    data = request.get_json(force=True)
    text = data.get("text","").strip()
    if not text: return jsonify({"error":"Text empty"}),400

    if not ELEVENLABS_KEY:
        return jsonify({"error":"ElevenLabs API key nahi hai. Render pe ELEVENLABS_API_KEY add karo."}),400

    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}"
        headers = {"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"}
        payload = {
            "text": text[:500],  # limit for free tier
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability":0.5,"similarity_boost":0.8}
        }
        r = req.post(url, json=payload, headers=headers, timeout=15)
        if r.status_code == 200:
            audio_b64 = base64.b64encode(r.content).decode("utf-8")
            return jsonify({"audio": audio_b64, "format": "mp3"})
        else:
            return jsonify({"error": f"ElevenLabs error: {r.status_code}"}),500
    except Exception as e:
        return jsonify({"error":str(e)}),500

# ── IMAGE ANALYSIS — Llama 4 Scout + Gemini fallback ─────────────────
@app.route("/api/upload", methods=["POST"])
def upload():
    sid      = request.form.get("session_id","default")
    user_msg = request.form.get("message","Isko analyze karo.").strip()
    if "file" not in request.files: return jsonify({"error":"File nahi mila"}),400

    file   = request.files["file"]
    fname  = file.filename.lower()
    fbytes = file.read()
    analysis = ""

    try:
        if fname.endswith(".pdf"):
            text = extract_text_from_pdf(fbytes)
            if GROQ_KEYS:
                client = groq.Groq(api_key=GROQ_KEYS[0])
                for model in CHAT_MODELS:
                    try:
                        r = client.chat.completions.create(
                            model=model,
                            messages=[{"role":"system","content":system_prompt()},
                                      {"role":"user","content":f"{user_msg}\n\nPDF:\n{text[:3000]}"}],
                            max_tokens=1500)
                        analysis = r.choices[0].message.content; break
                    except Exception as e:
                        if "rate" in str(e).lower(): continue
                        raise e

        elif fname.endswith((".jpg",".jpeg",".png",".webp",".gif",".bmp")):
            # Try Llama 4 Scout first (FREE on Groq)
            if GROQ_KEYS:
                try:
                    img_b64 = base64.b64encode(fbytes).decode("utf-8")
                    ext = fname.split(".")[-1]
                    mime = f"image/{'jpeg' if ext in ['jpg','jpeg'] else ext}"
                    client = groq.Groq(api_key=GROQ_KEYS[0])
                    r = client.chat.completions.create(
                        model="meta-llama/llama-4-scout-17b-16e-instruct",
                        messages=[{"role":"user","content":[
                            {"type":"text","text":user_msg},
                            {"type":"image_url","image_url":{"url":f"data:{mime};base64,{img_b64}"}}
                        ]}],
                        max_tokens=1000
                    )
                    analysis = r.choices[0].message.content
                except Exception:
                    # Fallback to Gemini
                    if gemini_vision:
                        import PIL.Image, io
                        img = PIL.Image.open(io.BytesIO(fbytes))
                        analysis = gemini_vision.generate_content([user_msg, img]).text
                    else:
                        analysis = "⚠️ Image analysis ke liye Llama 4 Scout ya GEMINI_API_KEY chahiye."
            elif gemini_vision:
                import PIL.Image, io
                img = PIL.Image.open(io.BytesIO(fbytes))
                analysis = gemini_vision.generate_content([user_msg, img]).text
            else:
                analysis = "⚠️ Image analysis ke liye API key chahiye."
        else:
            return jsonify({"error":"Sirf image aur PDF support hai"}),400

        add_msg(sid,"user",f"{user_msg}\n[File: {file.filename}]")
        add_msg(sid,"assistant",analysis)
    except Exception as e:
        return jsonify({"error":str(e)}),500

    return jsonify({"analysis":analysis})

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
    d = request.get_json(force=True)
    t = d.get("text","").strip()
    if not t: return jsonify({"error":"Text empty"}),400
    return jsonify(translate_text(t, d.get("source","auto"), d.get("target","hi")))

@app.route("/api/clear", methods=["POST"])
def clear():
    d = request.get_json(force=True)
    with conv_lock: conversations.pop(d.get("session_id","default"),None)
    return jsonify({"status":"cleared"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",5000)), debug=False)

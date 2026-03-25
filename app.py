import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify
from apis import get_ai_response

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
    get_mandi_prices, CROP_DISEASE_PROMPT,
)

load_dotenv()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

GROQ_KEYS = [k.strip() for k in [
    os.getenv("GROQ_API_KEY",""),
    os.getenv("GROQ_API_KEY_2",""),
    os.getenv("GROQ_API_KEY_3",""),
] if k.strip()]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY","")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
else:
    gemini_model = None

# ── Only working models (no decommissioned ones) ──────────────────────
CHAT_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
WHISPER_MODEL = "whisper-large-v3-turbo"

conversations: dict = {}
conv_lock = threading.Lock()
IST = pytz.timezone("Asia/Kolkata")

def get_ist():
    now = datetime.now(IST)
    h = now.hour
    ts = now.strftime("%I:%M %p")
    day = now.strftime("%A")
    date = now.strftime("%d %B %Y")
    if 5<=h<12:    period,ph="Morning",   f"Good Morning! It's {ts}"
    elif 12<=h<17: period,ph="Afternoon", f"Good Afternoon! It's {ts}"
    elif 17<=h<21: period,ph="Evening",   f"Good Evening! It's {ts}"
    else:          period,ph="Night",     f"It's {ts} at night"
    return {"hour":h,"time_str":ts,"period":period,"period_hi":ph,
            "day":day,"date":date,"full":f"{day}, {date} — {ts} IST"}

def system_prompt():
    t = get_ist()
    return f"""You are DeshGPT — India's smartest AI assistant.
Created by Mr. Nikhil Bhardwaj — passionate web developer and student from Badaun, UP.

CURRENT DATE & TIME (IST): {t['full']}
Today is {t['day']}, {t['date']}. Time: {t['time_str']} IST.

DATE/TIME RULES — ANSWER INSTANTLY:
- "Aaj kya date hai?" / "What's today's date?" → "{t['date']} ({t['day']})"
- "Abhi time kya hai?" / "What time is it?" → "{t['time_str']} IST"
- "Aaj kaunsa din hai?" → "{t['day']}"
- Never say you don't know the time — you always know it.

PERSONALITY:
- Talk like a close friend — "bhai", "yaar", "boss", "dude" naturally
- {t['period']} time: {'Be energetic and fresh!' if t['period']=='Morning' else 'Be helpful and friendly!' if t['period'] in ['Afternoon','Evening'] else 'Be caring, mention it is late night.'}
- Keep responses focused and relevant — no unnecessary padding

GREETING RULES — STRICT:
- NEVER start with religious words on your own
- ONLY if user sends first:
  "Jai Shri Ram" → "Jai Shri Ram! 🙏"
  "Radhe Radhe" → "Radhe Radhe! 🙏"
  "Assalam Walekum" → "Walekum Assalam! 😊"
  "Sat Sri Akal" → "Sat Sri Akal Ji! 🙏"

LANGUAGE: Reply in SAME language as user. Support all world languages.

WEATHER RULES:
- Extract ONLY the city name from message
- "Budaun ka mausam" → city = "Budaun"
- "Delhi weather" → city = "Delhi"
- Use the API data provided to give accurate weather info

CODING:
- Generate complete working project files from description
- HTML/CSS/JS single file, Flask, React — whatever needed
- Professional quality, downloadable

KNOWLEDGE: All subjects — science, math, history, coding, philosophy, law, arts, sports.

FARMING EXPERT:
- You know everything about Indian and world farming
- Crop seasons: Kharif (June-Nov), Rabi (Nov-Apr), Zaid (Apr-Jun)
- Major crops: wheat, rice, sugarcane, cotton, maize, bajra, jowar, pulses, vegetables, fruits
- Mandi rates, MSP prices, government schemes (PM Kisan, KCC, crop insurance)
- Seed rates, fertilizer doses, irrigation methods
- Crop diseases, pests, nutrient deficiencies — diagnosis and treatment
- Yield calculations per acre/bigha/hectare
- Investment vs earning calculations
- When user uploads crop/plant photo → diagnose disease, suggest medicine with dosage and price
- Storage, transportation, selling markets (APMC, FPO, direct sale)

NEVER say Meta/OpenAI made you — Mr. Nikhil Bhardwaj made you."""

def get_msgs(sid):
    with conv_lock: return list(conversations.get(sid,[]))

def add_msg(sid, role, content):
    with conv_lock:
        if sid not in conversations: conversations[sid]=[]
        conversations[sid].append({"role":role,"content":content})
        if len(conversations[sid])>20:
            conversations[sid]=conversations[sid][-20:]

def get_groq_response(messages):
    """Non-streaming — returns full response string."""
    for key in GROQ_KEYS:
        client = groq.Groq(api_key=key)
        for model in CHAT_MODELS:
            try:
                r = client.chat.completions.create(
                    model=model, messages=messages,
                    max_tokens=2048, temperature=0.7
                )
                return r.choices[0].message.content, model
            except Exception as e:
                err = str(e).lower()
                if any(x in err for x in ["rate","429","quota","exceeded","decommission","invalid_model","does not exist"]): continue
                raise e
    return None, None

def stream_response(sid, user_msg, context=""):
    if not GROQ_KEYS:
        yield f"data: {json.dumps({'text':'❌ Groq API key missing. Add GROQ_API_KEY in Render.'})}\n\n"
        yield "data: [DONE]\n\n"; return

    msgs = get_msgs(sid)
    full_msg = f"{user_msg}\n\n[Live Data]:\n{context}" if context else user_msg
    add_msg(sid,"user",full_msg)
    api_msgs = [{"role":"system","content":system_prompt()}] + get_msgs(sid)[:-1] + [{"role":"user","content":full_msg}]

    for key in GROQ_KEYS:
        client = groq.Groq(api_key=key)
        for model in CHAT_MODELS:
            try:
                stream = client.chat.completions.create(
                    model=model, messages=api_msgs,
                    max_tokens=2048, temperature=0.7, stream=True,
                )
                full = ""
                for chunk in stream:
                    d = chunk.choices[0].delta
                    if d.content:
                        full += d.content
                        yield f"data: {json.dumps({'text':d.content})}\n\n"
                if full:
                    add_msg(sid,"assistant",full)
                    yield "data: [DONE]\n\n"
                    return
            except Exception as e:
                err = str(e).lower()
                if any(x in err for x in ["rate","429","quota","exceeded","decommission","invalid_model","does not exist","no longer"]): continue
                yield f"data: {json.dumps({'text':f'❌ Error: {str(e)}'})}\n\n"
                yield "data: [DONE]\n\n"; return

    yield f"data: {json.dumps({'text':'⚠️ All models busy right now. Please try again in 2-3 minutes.'})}\n\n"
    yield "data: [DONE]\n\n"

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

    if rtype == "weather":
        # Better city extraction
        stop = {"weather","mausam","temperature","temp","barish","rain","aaj","today",
                "ka","ki","ke","hai","kaisa","batao","bata","kya","how","what","is",
                "in","the","of","me","mein","ka","aaj","abhi","current"}
        words = [w for w in msg.lower().split() if w not in stop and len(w)>2]
        city = " ".join(words).strip()
        if not city: city = "Delhi"
        ctx = json.dumps(get_weather(city), ensure_ascii=False)

    elif rtype == "crypto":
        coins = ["bitcoin","btc","ethereum","eth","dogecoin","doge","solana","sol",
                 "bnb","xrp","cardano","ada","shiba","shib","polygon","matic"]
        sym = next((c for c in coins if c in msg.lower()),"bitcoin")
        ctx = json.dumps(get_crypto_price(sym), ensure_ascii=False)

    elif rtype == "stock":
        skip = {"STOCK","SHARE","PRICE","KA","KI","KE","HAI","KAISE","AAJ","THE","NSE","BSE","MARKET"}
        sym = next((w for w in msg.upper().split() if len(w)>=3 and w.isalpha() and w not in skip),"RELIANCE")
        ctx = json.dumps(get_stock_price(sym), ensure_ascii=False)

    elif rtype == "news":
        q = msg.lower()
        for w in ["news","khabar","latest","aaj","today","breaking","headlines"]: q=q.replace(w,"").strip()
        ctx = json.dumps(get_news(q or "India"), ensure_ascii=False)

    elif rtype == "cricket":
        ctx = json.dumps(get_cricket_scores(), ensure_ascii=False)

    elif rtype in ("search","wikipedia"):
        ctx = json.dumps(search_duckduckgo(msg), ensure_ascii=False)

    return Response(
        stream_with_context(stream_response(sid, msg, ctx)),
        mimetype="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"}
    )

@app.route("/api/voice-to-text", methods=["POST"])
def voice_to_text():
    if "audio" not in request.files: return jsonify({"error":"Audio missing"}),400
    audio_file = request.files["audio"]
    if not GROQ_KEYS: return jsonify({"error":"Groq API key missing"}),500
    try:
        client = groq.Groq(api_key=GROQ_KEYS[0])
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            audio_file.save(tmp.name)
            with open(tmp.name,"rb") as f:
                transcription = client.audio.transcriptions.create(
                    model=WHISPER_MODEL, file=f, response_format="text"
                )
        os.unlink(tmp.name)
        return jsonify({"text": str(transcription)})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.route("/api/upload", methods=["POST"])
def upload():
    sid = request.form.get("session_id","default")
    user_msg = request.form.get("message","Analyze this.").strip()
    if "file" not in request.files: return jsonify({"error":"File missing"}),400
    file = request.files["file"]
    fname = file.filename.lower()
    fbytes = file.read()
    analysis = ""
    try:
        if fname.endswith(".pdf"):
            text = extract_text_from_pdf(fbytes)
            msgs = [{"role":"system","content":system_prompt()},
                    {"role":"user","content":f"{user_msg}\n\nPDF Content:\n{text[:3000]}"}]
            analysis, _ = get_groq_response(msgs)
            if not analysis: analysis = "Could not process PDF right now."
        elif fname.endswith((".jpg",".jpeg",".png",".webp",".gif",".bmp")):
            # Smart prompt — farming image gets disease detection
            farming_keywords = ["fasal","crop","plant","paudha","bimari","disease","khet","leaf","patta","fungus","pest","keeda"]
            is_farm = any(kw in user_msg.lower() for kw in farming_keywords)
            if is_farm:
                user_msg = CROP_DISEASE_PROMPT + "\n\nUser request: " + user_msg
            if GROQ_KEYS:
                try:
                    img_b64 = base64.b64encode(fbytes).decode("utf-8")
                    ext = fname.split(".")[-1]
                    mime = f"image/{'jpeg' if ext in ['jpg','jpeg'] else ext}"
                    client = groq.Groq(api_key=GROQ_KEYS[0])
                    r = client.chat.completions.create(
                        model=VISION_MODEL,
                        messages=[{"role":"user","content":[
                            {"type":"text","text":user_msg},
                            {"type":"image_url","image_url":{"url":f"data:{mime};base64,{img_b64}"}}
                        ]}], max_tokens=1000
                    )
                    analysis = r.choices[0].message.content
                except Exception:
                    if gemini_model:
                        import PIL.Image, io
                        img = PIL.Image.open(io.BytesIO(fbytes))
                        analysis = gemini_model.generate_content([user_msg, img]).text
                    else:
                        analysis = "⚠️ Image analysis needs GEMINI_API_KEY in Render settings."
            elif gemini_model:
                import PIL.Image, io
                img = PIL.Image.open(io.BytesIO(fbytes))
                analysis = gemini_model.generate_content([user_msg, img]).text
            else:
                analysis = "⚠️ Add GEMINI_API_KEY in Render for image analysis."
        else:
            return jsonify({"error":"Only images and PDFs supported"}),400
        add_msg(sid,"user",f"{user_msg} [File: {file.filename}]")
        add_msg(sid,"assistant",analysis)
    except Exception as e:
        return jsonify({"error":str(e)}),500
    return jsonify({"analysis":analysis})


@app.route("/api/mandi", methods=["POST"])
def mandi():
    data = request.get_json(force=True)
    crop  = data.get("crop","wheat")
    state = data.get("state","Uttar Pradesh")
    return jsonify(get_mandi_prices(crop, state))

@app.route("/api/crop-calc", methods=["POST"])
def crop_calc():
    """Crop yield and investment calculator."""
    data = request.get_json(force=True)
    crop  = data.get("crop","wheat")
    area  = float(data.get("area", 1))
    unit  = data.get("unit","acre")  # acre, bigha, hectare

    # Convert to acres
    if unit == "bigha":   area_acres = area * 0.625
    elif unit == "hectare": area_acres = area * 2.471
    else: area_acres = area

    # Approximate data per acre (Indian averages)
    crop_data = {
        "wheat":      {"yield_qtl":16, "seed_kg":40,  "invest":12000, "msp":2275,  "season":"Rabi"},
        "rice":       {"yield_qtl":20, "seed_kg":20,  "invest":15000, "msp":2183,  "season":"Kharif"},
        "sugarcane":  {"yield_qtl":300,"seed_qtl":25, "invest":35000, "msp":315,   "season":"Annual"},
        "maize":      {"yield_qtl":20, "seed_kg":8,   "invest":10000, "msp":1962,  "season":"Kharif"},
        "soybean":    {"yield_qtl":8,  "seed_kg":30,  "invest":9000,  "msp":4600,  "season":"Kharif"},
        "cotton":     {"yield_qtl":8,  "seed_kg":1.5, "invest":20000, "msp":7020,  "season":"Kharif"},
        "mustard":    {"yield_qtl":8,  "seed_kg":1.5, "invest":7000,  "msp":5650,  "season":"Rabi"},
        "gram":       {"yield_qtl":7,  "seed_kg":35,  "invest":7000,  "msp":5440,  "season":"Rabi"},
        "potato":     {"yield_qtl":100,"seed_qtl":12, "invest":40000, "price":600, "season":"Rabi"},
        "onion":      {"yield_qtl":80, "seed_kg":3,   "invest":25000, "price":800, "season":"Rabi"},
        "tomato":     {"yield_qtl":100,"seed_kg":0.1, "invest":30000, "price":500, "season":"All"},
        "bajra":      {"yield_qtl":12, "seed_kg":2,   "invest":6000,  "msp":2500,  "season":"Kharif"},
    }

    c = crop_data.get(crop.lower())
    if not c:
        return jsonify({"error": f"{crop} ka data abhi available nahi. Common crops: {', '.join(crop_data.keys())}"})

    total_yield = c["yield_qtl"] * area_acres
    total_invest = c["invest"] * area_acres
    price = c.get("msp", c.get("price", 2000))
    total_earn = total_yield * price
    profit = total_earn - total_invest

    seed_needed = c["seed_kg"] * area_acres if "seed_kg" in c else c.get("seed_qtl",0) * area_acres

    return jsonify({
        "crop": crop,
        "area_input": f"{area} {unit}",
        "area_acres": round(area_acres, 2),
        "expected_yield_qtl": round(total_yield, 1),
        "seed_needed": f"{round(seed_needed,1)} {'kg' if 'seed_kg' in c else 'quintal'}",
        "total_investment": f"₹{total_invest:,.0f}",
        "price_per_qtl": f"₹{price}",
        "expected_earning": f"₹{total_earn:,.0f}",
        "expected_profit": f"₹{profit:,.0f}",
        "roi_percent": round((profit/total_invest)*100, 1),
        "season": c["season"],
        "note": "Yield and prices are approximate averages. Actual may vary."
    })

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

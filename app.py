#!/usr/bin/env python3
"""
DeshGPT ULTIMATE - Main Application
All Free Features: Chat, Search, News, Weather, Crypto, Stocks, Cricket, Translation, OCR, PDF, Video
Author: Mr. Nikhil
"""

import os
import json
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response
import base64
from dotenv import load_dotenv
import requests

# Import custom APIs module
try:
    from apis import (
        search_duckduckgo, get_news, get_wikipedia_info,
        get_weather, get_crypto_price, get_stock_price,
        get_cricket_scores, translate_text, extract_text_from_pdf,
        extract_text_from_image_ocr, analyze_video, detect_request_type
    )
except ImportError as e:
    print(f"❌ Error importing apis.py: {e}")
    print("Make sure apis.py is in the same folder as app_final.py")

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

# API KEYS
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
WEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', '')
STOCKS_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY', '')

# Initialize AI Clients
groq_client = None
gemini_client = None

try:
    if GROQ_API_KEY:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)
        logger.info("✅ Groq API Ready")
    else:
        logger.warning("⚠️ Groq API Key not set")
except Exception as e:
    logger.error(f"Groq Error: {e}")

try:
    if GEMINI_API_KEY:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        logger.info("✅ Gemini API Ready")
    else:
        logger.warning("⚠️ Gemini API Key not set")
except Exception as e:
    logger.error(f"Gemini Error: {e}")

# STORAGE
conversation_history = {}

# HELPER FUNCTIONS
def get_real_datetime():
    """Get current date and time"""
    now = datetime.now()
    return {
        'date': now.strftime('%A, %B %d, %Y'),
        'time': now.strftime('%I:%M %p'),
        'datetime': now.strftime('%A, %B %d, %Y at %I:%M %p')
    }

def detect_special_request(message):
    """Detect special requests"""
    message_lower = message.lower().strip()
    dt = get_real_datetime()
    
    if any(kw in message_lower for kw in ['what time', 'current time', 'exact time', 'tell me the time']):
        return f"🕐 Current time: **{dt['time']}**"
    
    if any(kw in message_lower for kw in ['what date', 'date today', 'what is the date']):
        return f"📅 Today's date: **{dt['date']}**"
    
    if any(kw in message_lower for kw in ['what day', 'day today']):
        return f"📆 Today is: **{dt['date']}**"
    
    return None

def should_use_gemini(message, has_image=False):
    """Decide which AI to use"""
    if has_image:
        return True
    
    complex_keywords = ['explain', 'analyze', 'solve', 'code', 'debug', 'think', 'reason']
    return any(kw in message.lower() for kw in complex_keywords)

def call_groq_stream(message, conversation_id):
    """Stream response from Groq"""
    try:
        if not groq_client:
            yield f"data: {json.dumps({'error': 'Groq not available', 'done': True})}\n\n"
            return
        
        history = conversation_history.get(conversation_id, [])
        messages = history[-10:] + [{"role": "user", "content": message}]
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
            stream=True
        )
        
        full_response = ""
        for chunk in response:
            if chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                full_response += text
                yield f"data: {json.dumps({'text': text, 'done': False})}\n\n"
        
        # Save to history
        conversation_history[conversation_id] = messages + [
            {"role": "assistant", "content": full_response}
        ]
        
        yield f"data: {json.dumps({'text': '', 'done': True})}\n\n"
    
    except Exception as e:
        logger.error(f"Groq error: {e}")
        yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

# ROUTES
@app.route('/')
def index():
    """Serve main UI"""
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'service': 'DeshGPT Ultimate',
        'features': ['chat', 'image', 'search', 'news', 'weather', 'crypto', 'stocks', 'cricket', 'translate', 'ocr', 'pdf', 'video']
    }), 200

@app.route('/api/chat', methods=['POST'])
def chat():
    """Chat with streaming"""
    try:
        data = request.json
        message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id', 'default')
        image_data = data.get('image', None)
        
        if not message:
            return jsonify({'error': 'Empty message'}), 400
        
        return Response(
            call_groq_stream(message, conversation_id),
            mimetype='text/event-stream'
        ), 200
    
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload():
    """Handle file uploads"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file'}), 400
        
        file = request.files['file']
        file_type = request.form.get('type', 'image')
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        file_content = file.read()
        
        # Handle video
        if file_type == 'video':
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name
            
            analysis = analyze_video(tmp_path)
            try:
                os.remove(tmp_path)
            except:
                pass
            
            return jsonify(analysis), 200
        
        # Handle PDF
        elif file_type == 'pdf':
            result = extract_text_from_pdf(file_content)
            return jsonify(result), 200 if result else 500
        
        # Handle image
        else:
            file_base64 = base64.b64encode(file_content).decode()
            ocr_text = extract_text_from_image_ocr(f"data:image/jpeg;base64,{file_base64}")
            
            return jsonify({
                'filename': file.filename,
                'type': 'image',
                'data': f"data:{file.content_type};base64,{file_base64}",
                'ocr': ocr_text
            }), 200
    
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/search', methods=['POST'])
def search_all():
    """Universal search"""
    try:
        data = request.json
        query = data.get('query', '').strip()
        search_type = data.get('type', 'general')
        
        if not query:
            return jsonify({'error': 'Empty query'}), 400
        
        results = {'query': query, 'results': []}
        
        if search_type in ['general', 'detect']:
            search_type = detect_request_type(query)
        
        # Execute searches
        if search_type in ['weather', 'general']:
            w = get_weather(query, WEATHER_API_KEY)
            if w:
                results['results'].append(w)
        
        if search_type in ['crypto', 'general']:
            c = get_crypto_price(query.lower())
            if c:
                results['results'].append(c)
        
        if search_type in ['stock', 'general']:
            s = get_stock_price(query, STOCKS_API_KEY)
            if s:
                results['results'].append(s)
        
        if search_type in ['news', 'general']:
            n = get_news(query, max_results=3)
            if n:
                results['results'].extend(n)
        
        if search_type in ['cricket', 'general']:
            cr = get_cricket_scores()
            if cr:
                results['results'].extend(cr)
        
        if search_type == 'general':
            w = get_wikipedia_info(query)
            if w:
                results['results'].append(w)
            
            s = search_duckduckgo(query)
            if s:
                results['results'].extend(s)
        
        return jsonify(results), 200
    
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/weather/<city>', methods=['GET'])
def weather(city):
    """Get weather"""
    try:
        w = get_weather(city, WEATHER_API_KEY)
        return jsonify(w), 200 if w else 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/crypto/<symbol>', methods=['GET'])
def crypto(symbol):
    """Get crypto price"""
    try:
        c = get_crypto_price(symbol)
        return jsonify(c), 200 if c else 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stock/<symbol>', methods=['GET'])
def stock(symbol):
    """Get stock price"""
    try:
        s = get_stock_price(symbol, STOCKS_API_KEY)
        return jsonify(s), 200 if s else 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/news/<query>', methods=['GET'])
def news(query):
    """Get news"""
    try:
        n = get_news(query, max_results=5)
        return jsonify({'news': n}), 200 if n else 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cricket', methods=['GET'])
def cricket():
    """Get cricket scores"""
    try:
        c = get_cricket_scores()
        return jsonify({'scores': c}), 200 if c else 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/translate', methods=['POST'])
def translate():
    """Translate text"""
    try:
        data = request.json
        text = data.get('text', '').strip()
        target = data.get('target', 'hi')
        
        if not text:
            return jsonify({'error': 'Empty text'}), 400
        
        result = translate_text(text, target)
        return jsonify(result), 200 if result else 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ERROR HANDLERS
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def error_500(error):
    logger.error(f"Error: {error}")
    return jsonify({'error': 'Server error'}), 500

# STARTUP
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    logger.info("🚀 DeshGPT ULTIMATE Starting...")
    logger.info("✨ Features: Chat, Search, News, Weather, Crypto, Stocks, Cricket, Translation, OCR, PDF, Video")
    
    app.run(host='0.0.0.0', port=port, debug=debug)

from flask import Flask, request, jsonify, render_template_string
from groq import Groq
import requests
import os
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import base64
import json

app = Flask(__name__)

# ✅ GROQ API KEY (Lifetime Free)
api_key = os.getenv("GROQ_API_KEY", "____")
client = Groq(api_key=api_key)

chat_history = {}
image_uploads = {}  # Track uploads per user per day

# ✅ DAILY UPLOAD LIMIT
DAILY_UPLOAD_LIMIT = 5

# ✅ Multi-Language Detection
def detect_language(text):
    """Detect if text is Hindi or English"""
    hindi_chars = set('अआइईउऊऋएऐओऔकखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसहक्षत्रज्ञॐंः़ऀँ')
    english_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
    
    hindi_count = sum(1 for char in text if char in hindi_chars)
    english_count = sum(1 for char in text if char in english_chars)
    
    if hindi_count > english_count:
        return "hindi"
    return "english"

# ✅ Check Upload Limit
def check_upload_limit(user_id):
    """Check if user has exceeded daily upload limit"""
    today = datetime.now().date().isoformat()
    
    if user_id not in image_uploads:
        image_uploads[user_id] = {"date": today, "count": 0}
    
    user_data = image_uploads[user_id]
    
    # Reset if date changed
    if user_data["date"] != today:
        user_data = {"date": today, "count": 0}
        image_uploads[user_id] = user_data
    
    return user_data["count"] < DAILY_UPLOAD_LIMIT, user_data["count"]

# ✅ Increment Upload Count
def increment_upload_count(user_id):
    """Increment upload count for user"""
    today = datetime.now().date().isoformat()
    
    if user_id not in image_uploads:
        image_uploads[user_id] = {"date": today, "count": 0}
    
    user_data = image_uploads[user_id]
    
    if user_data["date"] != today:
        user_data = {"date": today, "count": 0}
    
    user_data["count"] += 1
    image_uploads[user_id] = user_data

# ✅ DeshGPT Prompts
DESHGPT_PROMPT_ENGLISH = """
You are DeshGPT - an AI assistant made by Mr. Nikhil. 🇮🇳

Your job: Be helpful, friendly, and answer questions. You can now analyze images/screenshots!

You can:
✅ Answer questions about anything (studies, coding, career, life, news)
✅ Analyze screenshots, photos, images
✅ Explain what's in images
✅ Help with homework from photos
✅ Search the web for latest information
✅ Get breaking news

Be casual and friendly like a friend. Use emojis naturally.
When analyzing images, be detailed and helpful.
"""

DESHGPT_PROMPT_HINDI = """
तुम DeshGPT हो - एक AI assistant जिसे Mr. Nikhil ने बनाया है। 🇮🇳

तुम्हारा काम: Helpful, friendly रहो। अब तुम images/screenshots को भी analyze कर सकते हो!

तुम यह कर सकते हो:
✅ किसी भी चीज़ के बारे में सवाल का जवाब
✅ Screenshots और photos को analyze करना
✅ Images में क्या है यह बताना
✅ Homework का photo भेजकर help लेना
✅ Web से latest जानकारी
✅ Breaking न्यूज़

दोस्त की तरह casual और friendly रहो। Images को analyze करते समय detail में बता।
"""

def web_search(query):
    """DuckDuckGo से search करो (Lifetime Free)"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        search_url = f"https://duckduckgo.com/html/?q={query}"
        response = requests.get(search_url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.content, 'html.parser')
        results = []
        
        for result in soup.find_all('div', class_='result'):
            title_elem = result.find('a', class_='result__url')
            snippet_elem = result.find('a', class_='result__snippet')
            
            if title_elem and snippet_elem:
                results.append({
                    'title': title_elem.get_text(),
                    'snippet': snippet_elem.get_text(),
                    'url': title_elem.get('href', '')
                })
        
        return results[:3]
    except:
        return []

def needs_web_search(query):
    """Check क्या web search की जरूरत है"""
    keywords = ['latest', 'news', 'today', 'current', 'live', 'price', 'update',
                'weather', 'trending', 'recent', 'क्या है', 'कैसे है', 'कहाँ है',
                'आज', 'breaking', 'bitcoin', 'stock', 'weather', 'price']
    
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in keywords)

@app.route('/')
def home():
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DeshGPT - Image & Chat AI</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box;}
        body {
            font-family: 'Segoe UI', 'Noto Sans Devanagari', sans-serif;
            background: linear-gradient(135deg, #FF6B35, #F7931E, #00A86B);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            padding: 20px;
            text-align: center;
            color: white;
            border-bottom: 2px solid rgba(255,255,255,0.2);
        }
        .logo { font-size: 2.5em; margin: 10px 0; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
        .tagline { font-size: 1.1em; font-weight: 300; opacity: 0.95; }
        .upload-counter {
            display: inline-block;
            background: rgba(255,255,255,0.2);
            padding: 8px 15px;
            border-radius: 20px;
            margin-top: 10px;
            font-size: 0.9em;
        }
        .features {
            display: flex;
            gap: 15px;
            justify-content: center;
            flex-wrap: wrap;
            margin-top: 15px;
        }
        .feature-badge {
            background: rgba(255,255,255,0.2);
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            backdrop-filter: blur(10px);
        }
        .main-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            max-width: 900px;
            margin: 0 auto;
            width: 100%;
            padding: 20px;
        }
        .chat-area {
            flex: 1;
            background: rgba(255,255,255,0.98);
            border-radius: 25px;
            display: flex;
            flex-direction: column;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
            margin-bottom: 20px;
        }
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 25px;
        }
        .message {
            margin: 15px 0;
            padding: 15px 20px;
            border-radius: 20px;
            max-width: 85%;
            word-wrap: break-word;
            animation: fadeIn 0.3s ease-in;
        }
        .message img {
            max-width: 100%;
            max-height: 300px;
            border-radius: 10px;
            margin: 10px 0;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .user-msg {
            background: linear-gradient(135deg, #FF6B35, #F7931E);
            color: white;
            margin-left: auto;
            border-radius: 20px 5px 20px 20px;
        }
        .ai-msg {
            background: linear-gradient(135deg, #00A86B, #00D4AA);
            color: white;
            margin-right: auto;
            border-radius: 5px 20px 20px 20px;
        }
        .input-section {
            display: flex;
            gap: 12px;
            padding: 20px 25px;
            background: #f8f9fa;
            border-top: 1px solid #e9ecef;
            flex-wrap: wrap;
        }
        .input-group {
            display: flex;
            gap: 10px;
            flex: 1;
            min-width: 250px;
        }
        input[type="text"] {
            flex: 1;
            padding: 15px 20px;
            border: 2px solid #e9ecef;
            border-radius: 25px;
            font-size: 16px;
            transition: all 0.3s;
        }
        input[type="text"]:focus {
            outline: none;
            border-color: #FF6B35;
            box-shadow: 0 0 0 3px rgba(255,107,53,0.1);
        }
        input[type="file"] {
            display: none;
        }
        .button-group {
            display: flex;
            gap: 10px;
        }
        button {
            padding: 12px 20px;
            background: #4CAF50;
            color: white;
            border: none;
            border-radius: 25px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s;
            font-size: 15px;
        }
        button:hover { background: #45a049; }
        button.icon-btn {
            padding: 12px 15px;
            background: #2196F3;
        }
        button.icon-btn:hover { background: #1976D2; }
        .info-section {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            padding: 20px;
            border-radius: 20px;
            color: white;
            margin-top: 20px;
            font-size: 0.95em;
            line-height: 1.6;
        }
        .footer {
            text-align: center;
            color: white;
            padding: 15px;
            opacity: 0.85;
        }
        .upload-limit {
            font-size: 0.85em;
            margin-top: 5px;
            opacity: 0.9;
        }
        @media (max-width: 600px) {
            .logo { font-size: 2em; }
            .input-group { flex-direction: column; }
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">🇮🇳 DeshGPT</div>
        <div class="tagline">Your AI Assistant | तुम्हारा AI सहायक</div>
        <div class="upload-counter">
            📸 Daily Uploads: <span id="uploadCount">5</span> remaining
        </div>
        
        <div class="features">
            <div class="feature-badge">💬 Chat (Hindi/English)</div>
            <div class="feature-badge">🖼️ Photo Upload</div>
            <div class="feature-badge">📸 Screenshot</div>
            <div class="feature-badge">🔍 Web Search</div>
            <div class="feature-badge">📰 News</div>
        </div>
    </div>

    <div class="main-container">
        <div class="chat-area">
            <div class="messages" id="messages">
                <div class="message ai-msg">
                    <strong>🇮🇳 Hello! नमस्ते!</strong><br><br>
                    I'm <strong>DeshGPT</strong> - your AI assistant made by Mr. Nikhil! 👋<br><br>
                    
                    <strong>अब मैं यह कर सकता हूँ:</strong><br>
                    ✅ Chat (English/Hindi)<br>
                    ✅ Photos/Screenshots को analyze करना<br>
                    ✅ Questions का जवाब देना<br>
                    ✅ Latest news और search<br>
                    ✅ Problem solving और advice<br><br>
                    
                    Photo upload करो और पूछो! 📸
                </div>
            </div>
            
            <div class="input-section">
                <div class="input-group">
                    <input type="text" id="messageInput" placeholder="Ask me anything or upload a photo... (Hindi or English)" 
                           onkeypress="if(event.key==='Enter') sendMessage()">
                    <button class="icon-btn" onclick="document.getElementById('photoInput').click()" title="Upload Photo">
                        📸 Photo
                    </button>
                    <button class="icon-btn" onclick="document.getElementById('cameraInput').click()" title="Take Screenshot">
                        📷 Camera
                    </button>
                </div>
                <button onclick="sendMessage()">Send</button>
            </div>
            <div class="upload-limit" id="uploadLimit" style="text-align: center; color: #666; font-size: 0.8em; padding: 5px;"></div>
        </div>

        <div class="info-section">
            <strong>About DeshGPT:</strong><br>
            Made by Mr. Nikhil | Hindi & English Support | Photo Analysis | Web Search | Latest News | 24/7 Available
        </div>
    </div>

    <div class="footer">
        © 2025 DeshGPT by Mr. Nikhil | Powered by Groq AI
    </div>

    <input type="file" id="photoInput" accept="image/*">
    <input type="file" id="cameraInput" accept="image/*" capture="environment">

    <script>
        const userId = 'user_' + Date.now();
        const messagesEl = document.getElementById('messages');
        const inputEl = document.getElementById('messageInput');
        const photoInput = document.getElementById('photoInput');
        const cameraInput = document.getElementById('cameraInput');
        const uploadCountEl = document.getElementById('uploadCount');
        const uploadLimitEl = document.getElementById('uploadLimit');

        let uploadCount = 5;

        function updateUploadDisplay() {
            uploadCountEl.textContent = uploadCount;
            if (uploadCount === 0) {
                uploadLimitEl.textContent = '⚠️ Daily limit reached. Try again tomorrow!';
                uploadLimitEl.style.color = '#FF6B35';
            } else if (uploadCount <= 2) {
                uploadLimitEl.textContent = `⚠️ Only ${uploadCount} uploads remaining today`;
                uploadLimitEl.style.color = '#FF6B35';
            } else {
                uploadLimitEl.textContent = '';
            }
        }

        function addMessage(content, isUser, imageData = null) {
            const div = document.createElement('div');
            div.className = `message ${isUser ? 'user-msg' : 'ai-msg'}`;
            let html = content;
            if (imageData) {
                html = `<img src="${imageData}" style="max-width: 100%; max-height: 300px; border-radius: 10px; margin: 10px 0;"><br>${content}`;
            }
            div.innerHTML = html;
            messagesEl.appendChild(div);
            messagesEl.scrollTop = messagesEl.scrollHeight;
        }

        function handleImageUpload(file) {
            if (uploadCount === 0) {
                addMessage('⚠️ Daily upload limit reached. Try again tomorrow!', false);
                return;
            }

            const reader = new FileReader();
            reader.onload = async (e) => {
                const imageData = e.target.result;
                const userMessage = inputEl.value.trim() || "What is this?";
                
                addMessage(`📸 Photo uploaded: "${userMessage}"`, true, imageData);
                inputEl.value = '';
                
                const typingDiv = document.createElement('div');
                typingDiv.className = 'message ai-msg';
                typingDiv.innerHTML = '⏳ Analyzing image... 💭';
                typingDiv.id = 'typing';
                messagesEl.appendChild(typingDiv);
                messagesEl.scrollTop = messagesEl.scrollHeight;

                try {
                    const response = await fetch('/chat', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            user_id: userId, 
                            message: userMessage,
                            image: imageData,
                            search: true
                        })
                    });
                    
                    const data = await response.json();
                    document.getElementById('typing')?.remove();
                    
                    if (data.upload_allowed) {
                        addMessage(data.reply, false);
                        uploadCount = data.remaining_uploads;
                        updateUploadDisplay();
                    } else {
                        addMessage('⚠️ Daily upload limit reached. Try again tomorrow!', false);
                    }
                } catch (error) {
                    document.getElementById('typing')?.remove();
                    addMessage('Sorry! Something went wrong. Please try again.', false);
                }
            };
            reader.readAsDataURL(file);
        }

        photoInput.addEventListener('change', (e) => {
            if (e.target.files[0]) {
                handleImageUpload(e.target.files[0]);
                photoInput.value = '';
            }
        });

        cameraInput.addEventListener('change', (e) => {
            if (e.target.files[0]) {
                handleImageUpload(e.target.files[0]);
                cameraInput.value = '';
            }
        });

        async function sendMessage() {
            const message = inputEl.value.trim();
            if (!message) return;

            addMessage(message, true);
            inputEl.value = '';
            inputEl.focus();
            
            const typingDiv = document.createElement('div');
            typingDiv.className = 'message ai-msg';
            typingDiv.innerHTML = '⏳ Thinking... 💭';
            typingDiv.id = 'typing';
            messagesEl.appendChild(typingDiv);
            messagesEl.scrollTop = messagesEl.scrollHeight;

            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        user_id: userId, 
                        message: message,
                        search: true
                    })
                });
                
                const data = await response.json();
                document.getElementById('typing')?.remove();
                addMessage(data.reply, false);
            } catch (error) {
                document.getElementById('typing')?.remove();
                addMessage('Sorry! Something went wrong. Please try again.', false);
            }
        }

        updateUploadDisplay();
    </script>
</body>
</html>
    """)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_id = data.get('user_id', 'default')
    message = data['message']
    image_data = data.get('image', None)
    search_enabled = data.get('search', True)
    
    # Check upload limit if image is provided
    if image_data:
        allowed, current_count = check_upload_limit(user_id)
        if not allowed:
            return jsonify({
                'reply': '⚠️ Daily upload limit (5) reached. Try again tomorrow!',
                'upload_allowed': False,
                'remaining_uploads': 0
            })
        
        increment_upload_count(user_id)
        allowed, current_count = check_upload_limit(user_id)
        remaining = DAILY_UPLOAD_LIMIT - current_count
    else:
        allowed, current_count = check_upload_limit(user_id)
        remaining = DAILY_UPLOAD_LIMIT - current_count
    
    # Detect language
    language = detect_language(message)
    system_prompt = DESHGPT_PROMPT_HINDI if language == "hindi" else DESHGPT_PROMPT_ENGLISH
    
    history = chat_history.get(user_id, [])
    
    # Check if web search needed
    use_search = search_enabled and needs_web_search(message)
    
    search_results = ""
    
    if use_search:
        try:
            search_results_list = web_search(message)
            if search_results_list:
                search_results = f"\n\nRELEVANT SEARCH RESULTS:\n"
                for i, result in enumerate(search_results_list, 1):
                    search_results += f"{i}. {result['title']}: {result['snippet']}\n"
        except:
            pass
    
    context = system_prompt
    
    # Add image analysis context if image provided
    if image_data:
        context += "\n\nUSER HAS PROVIDED AN IMAGE/SCREENSHOT. Analyze it carefully and answer their question about it."
    
    if search_results:
        context += search_results
    
    try:
        messages = [
            {"role": "system", "content": context},
            *history[-10:]
        ]
        
        # Build user message with image
        if image_data:
            messages.append({
                "role": "user",
                "content": message
            })
        else:
            messages.append({
                "role": "user", 
                "content": message
            })
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=1500
        )
        
        reply = response.choices[0].message.content
        
        if use_search:
            if language == "hindi":
                reply += f"\n\n🔍 (Web search से)"
            else:
                reply += f"\n\n🔍 (From web search)"
        
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})
        chat_history[user_id] = history[-20:]
        
        return jsonify({
            'reply': reply,
            'used_search': use_search,
            'language': language,
            'upload_allowed': True,
            'remaining_uploads': remaining
        })
        
    except Exception as e:
        if language == "hindi":
            error_msg = f"कुछ समस्या आई। कृपया फिर से कोशिश करो!"
        else:
            error_msg = f"Something went wrong. Please try again!"
        
        return jsonify({
            'reply': error_msg,
            'used_search': False,
            'language': language,
            'upload_allowed': True,
            'remaining_uploads': remaining
        })

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🇮🇳 DeshGPT V2 - Image Upload & Analysis Feature")
    print("="*70)
    print("\n✅ Server Started!")
    print("🌐 Open: http://localhost:5000")
    print("\n📸 Features:")
    print(f"   ✓ Photo Upload (Daily Limit: {DAILY_UPLOAD_LIMIT})")
    print("   ✓ Screenshot Analysis")
    print("   ✓ English/Hindi Support")
    print("   ✓ Web Search")
    print("   ✓ Latest News")
    print("\n" + "="*70 + "\n")
    app.run(debug=False, host='0.0.0.0', port=5000)
import os

port = int(os.environ.get("PORT", 8080))

app.run(host="0.0.0.0", port=port)

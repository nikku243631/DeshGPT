"""
DeshGPT - All API Functions
Free APIs for Search, News, Weather, Crypto, Stocks, Cricket, Translation, PDF, OCR, Video
"""

import requests
import logging
import feedparser
import base64
from io import BytesIO
import os

logger = logging.getLogger(__name__)

# ============================================================================
# SEARCH APIS
# ============================================================================

def search_duckduckgo(query, max_results=3):
    """Search using DuckDuckGo (FREE, No API Key!)"""
    try:
        from bs4 import BeautifulSoup
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        search_url = f"https://duckduckgo.com/html/?q={query}"
        response = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        results = []
        for result in soup.find_all('div', class_='result')[:max_results]:
            title_elem = result.find('a', class_='result__url')
            snippet_elem = result.find('a', class_='result__snippet')
            
            if title_elem and snippet_elem:
                results.append({
                    'title': title_elem.get_text(),
                    'snippet': snippet_elem.get_text(),
                    'source': 'DuckDuckGo'
                })
        
        return results if results else None
    except Exception as e:
        logger.error(f"DuckDuckGo error: {e}")
        return None

# ============================================================================
# NEWS APIS
# ============================================================================

def get_news(query, max_results=5):
    """Get Latest NEWS from Google News RSS (FREE, No API Key!)"""
    try:
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        
        news_items = []
        for entry in feed.entries[:max_results]:
            news_items.append({
                'title': entry.title,
                'link': entry.link,
                'published': entry.get('published', 'N/A'),
                'source': 'Google News'
            })
        
        return news_items if news_items else None
    except Exception as e:
        logger.error(f"News fetch error: {e}")
        return None

# ============================================================================
# WIKIPEDIA
# ============================================================================

def get_wikipedia_info(query):
    """Get information from Wikipedia (FREE)"""
    try:
        import wikipedia
        page = wikipedia.page(query, auto_suggest=True)
        return {
            'title': page.title,
            'summary': page.summary[:500],
            'url': page.url,
            'source': 'Wikipedia'
        }
    except Exception as e:
        logger.error(f"Wikipedia error: {e}")
        return None

# ============================================================================
# WEATHER
# ============================================================================

def get_weather(city, api_key=None):
    """Get Weather from OpenWeatherMap (FREE Tier - 60/min)"""
    try:
        if not api_key:
            api_key = os.getenv('OPENWEATHER_API_KEY', '')
        
        if not api_key:
            return None
        
        url = f"https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city,
            "appid": api_key,
            "units": "metric"
        }
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            weather = response.json()
            return {
                'city': weather['name'],
                'country': weather['sys'].get('country', ''),
                'temperature': weather['main']['temp'],
                'feels_like': weather['main']['feels_like'],
                'humidity': weather['main']['humidity'],
                'pressure': weather['main']['pressure'],
                'wind_speed': weather['wind']['speed'],
                'description': weather['weather'][0]['description'],
                'icon': weather['weather'][0]['main'],
                'source': 'OpenWeatherMap'
            }
        return None
    except Exception as e:
        logger.error(f"Weather error: {e}")
        return None

# ============================================================================
# CRYPTOCURRENCY
# ============================================================================

def get_crypto_price(crypto_id="bitcoin"):
    """Get Cryptocurrency Prices from CoinGecko (COMPLETELY FREE!)"""
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": crypto_id.lower(),
            "vs_currencies": "usd,inr",
            "include_market_cap": "true",
            "include_24hr_change": "true"
        }
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if crypto_id.lower() in data:
                price_data = data[crypto_id.lower()]
                return {
                    'name': crypto_id.upper(),
                    'price_usd': price_data.get('usd'),
                    'price_inr': price_data.get('inr'),
                    'market_cap_usd': price_data.get('usd_market_cap'),
                    'change_24h': price_data.get('usd_24h_change'),
                    'source': 'CoinGecko'
                }
        return None
    except Exception as e:
        logger.error(f"Crypto error: {e}")
        return None

# ============================================================================
# STOCKS
# ============================================================================

def get_stock_price(symbol, api_key=None):
    """Get Stock Prices from Alpha Vantage (FREE Tier - 5 req/min)"""
    try:
        if not api_key:
            api_key = os.getenv('ALPHA_VANTAGE_API_KEY', '')
        
        if not api_key:
            return None
        
        url = f"https://www.alphavantage.co/query"
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol.upper(),
            "apikey": api_key
        }
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'Global Quote' in data and data['Global Quote'].get('05. price'):
                quote = data['Global Quote']
                return {
                    'symbol': symbol.upper(),
                    'price': quote.get('05. price'),
                    'change': quote.get('09. change'),
                    'change_percent': quote.get('10. change percent'),
                    'volume': quote.get('06. volume'),
                    'source': 'Alpha Vantage'
                }
        return None
    except Exception as e:
        logger.error(f"Stock error: {e}")
        return None

# ============================================================================
# CRICKET SCORES
# ============================================================================

def get_cricket_scores():
    """Get Live Cricket Scores (Web Scraping - FREE)"""
    try:
        from bs4 import BeautifulSoup
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(
            "https://www.espncricinfo.com/",
            headers=headers,
            timeout=10
        )
        
        soup = BeautifulSoup(response.content, 'html.parser')
        scores = []
        
        match_elements = soup.find_all('div', class_='ds-grow')[:3]
        for elem in match_elements:
            text = elem.get_text(strip=True)
            if text and len(text) > 10:
                scores.append({
                    'match_info': text[:150],
                    'source': 'ESPN Cricinfo'
                })
        
        return scores if scores else None
    except Exception as e:
        logger.error(f"Cricket error: {e}")
        return None

# ============================================================================
# TRANSLATION
# ============================================================================

def translate_text(text, target_lang="hi"):
    """Translate text using LibreTranslate (COMPLETELY FREE!)"""
    try:
        url = "https://libretranslate.de/translate"
        data = {
            "q": text,
            "source": "auto",
            "target": target_lang
        }
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            return {
                'original': text,
                'translated': result.get('translatedText'),
                'target_language': target_lang,
                'source': 'LibreTranslate'
            }
        return None
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return None

# ============================================================================
# PDF EXTRACTION
# ============================================================================

def extract_text_from_pdf(file_content):
    """Extract text from PDF (PyPDF2 - FREE)"""
    try:
        from PyPDF2 import PdfReader
        
        pdf_reader = PdfReader(BytesIO(file_content))
        text = ""
        metadata = {
            'pages': len(pdf_reader.pages),
            'author': pdf_reader.metadata.get('/Author', 'Unknown') if pdf_reader.metadata else 'Unknown'
        }
        
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        
        return {
            'text': text[:2000],
            'metadata': metadata,
            'source': 'PyPDF2'
        }
    except Exception as e:
        logger.error(f"PDF error: {e}")
        return None

# ============================================================================
# OCR - TEXT FROM IMAGES
# ============================================================================

def extract_text_from_image_ocr(image_data):
    """Extract text from image using Tesseract OCR (FREE)"""
    try:
        import pytesseract
        from PIL import Image
        
        if isinstance(image_data, str) and image_data.startswith('data:image'):
            image_data = image_data.split(',')[1]
        
        image_bytes = base64.b64decode(image_data)
        image = Image.open(BytesIO(image_bytes))
        
        text = pytesseract.image_to_string(image)
        return {
            'text': text[:1000] if text else "No text detected",
            'source': 'Tesseract OCR'
        }
    except Exception as e:
        logger.error(f"OCR error: {e}")
        return None

# ============================================================================
# VIDEO ANALYSIS
# ============================================================================

def analyze_video(video_path, max_duration=30):
    """Analyze video file (max 30 seconds) - FREE using OpenCV"""
    try:
        import cv2
        
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        if duration > max_duration:
            return {"error": f"Video must be less than {max_duration} seconds"}
        
        video_info = {
            'duration_seconds': round(duration, 2),
            'fps': round(fps, 2),
            'total_frames': total_frames,
            'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            'frame_samples': [],
            'source': 'OpenCV'
        }
        
        frame_count = 0
        while cap.isOpened() and len(video_info['frame_samples']) < 3:
            ret, frame = cap.read()
            if not ret:
                break
            
            if frame_count % 5 == 0:
                small_frame = cv2.resize(frame, (160, 120))
                _, buffer = cv2.imencode('.jpg', small_frame)
                frame_base64 = base64.b64encode(buffer).decode()
                video_info['frame_samples'].append(frame_base64)
            
            frame_count += 1
        
        cap.release()
        return video_info
    except Exception as e:
        logger.error(f"Video analysis error: {e}")
        return {"error": str(e)}

# ============================================================================
# INTELLIGENT REQUEST DETECTION
# ============================================================================

def detect_request_type(message):
    """Detect what user is asking for"""
    message_lower = message.lower()
    
    if any(w in message_lower for w in ['weather', 'temperature', 'rain', 'cloudy', 'sunny']):
        return 'weather'
    
    if any(w in message_lower for w in ['bitcoin', 'ethereum', 'crypto', 'coin', 'doge']):
        return 'crypto'
    
    if any(w in message_lower for w in ['stock', 'share', 'nasdaq', 'sensex', 'nifty']):
        return 'stock'
    
    if any(w in message_lower for w in ['news', 'latest', 'breaking', 'headline', 'today']):
        return 'news'
    
    if any(w in message_lower for w in ['cricket', 'ipl', 'match', 'score', 'test', 'odi']):
        return 'cricket'
    
    if any(w in message_lower for w in ['translate', 'meaning', 'hindi', 'english', 'language']):
        return 'translate'
    
    return 'general'

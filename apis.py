"""
apis.py — DeshGPT API Module
Sab FREE APIs ek jagah. No paid services.
"""

import os
import io
import re
import json
import tempfile
import requests
from bs4 import BeautifulSoup
import feedparser

# ── Optional imports with graceful fallback ───────────────────────────────────
try:
    import PyPDF2
    PDF_OK = True
except ImportError:
    PDF_OK = False

try:
    import pytesseract
    from PIL import Image
    OCR_OK = True
except ImportError:
    OCR_OK = False

try:
    import cv2
    import numpy as np
    CV2_OK = True
except ImportError:
    CV2_OK = False

try:
    import wikipedia
    WIKI_OK = True
except ImportError:
    WIKI_OK = False


# ─────────────────────────────────────────────────────────────────────────────
# 1. WEB SEARCH — DuckDuckGo (100% FREE, no key needed)
# ─────────────────────────────────────────────────────────────────────────────
def search_duckduckgo(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo Instant Answer + HTML scraping."""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # Try Instant Answer API first
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        r = requests.get(url, params=params, headers=headers, timeout=8)
        data = r.json()

        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", query),
                "snippet": data["AbstractText"][:400],
                "url": data.get("AbstractURL", ""),
            })

        for topic in data.get("RelatedTopics", [])[:3]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:60],
                    "snippet": topic.get("Text", "")[:300],
                    "url": topic.get("FirstURL", ""),
                })
    except Exception:
        pass

    # Fallback: scrape HTML results
    if len(results) < 2:
        try:
            r = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers=headers,
                timeout=8,
            )
            soup = BeautifulSoup(r.text, "html.parser")
            for result in soup.select(".result__body")[:max_results]:
                title_el = result.select_one(".result__title")
                snippet_el = result.select_one(".result__snippet")
                link_el = result.select_one(".result__url")
                if title_el and snippet_el:
                    results.append({
                        "title": title_el.get_text(strip=True)[:100],
                        "snippet": snippet_el.get_text(strip=True)[:350],
                        "url": link_el.get_text(strip=True) if link_el else "",
                    })
        except Exception:
            pass

    return results[:max_results]


# ─────────────────────────────────────────────────────────────────────────────
# 2. NEWS — Google News RSS (100% FREE)
# ─────────────────────────────────────────────────────────────────────────────
def get_news(query: str = "India", max_items: int = 6) -> dict:
    """Google News RSS feed — completely free."""
    try:
        encoded = requests.utils.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
        feed = feedparser.parse(url)

        items = []
        for entry in feed.entries[:max_items]:
            items.append({
                "title": entry.get("title", ""),
                "summary": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text()[:200],
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source": entry.get("source", {}).get("title", ""),
            })

        return {"query": query, "articles": items, "total": len(items)}
    except Exception as e:
        return {"error": str(e), "query": query, "articles": []}


# ─────────────────────────────────────────────────────────────────────────────
# 3. WIKIPEDIA — Free API
# ─────────────────────────────────────────────────────────────────────────────
def get_wikipedia_info(query: str, sentences: int = 5) -> dict:
    """Wikipedia summary — 100% free."""
    if WIKI_OK:
        try:
            wikipedia.set_lang("en")
            summary = wikipedia.summary(query, sentences=sentences, auto_suggest=True)
            page = wikipedia.page(query, auto_suggest=True)
            return {
                "title": page.title,
                "summary": summary,
                "url": page.url,
                "found": True,
            }
        except wikipedia.exceptions.DisambiguationError as e:
            try:
                summary = wikipedia.summary(e.options[0], sentences=sentences)
                return {"title": e.options[0], "summary": summary, "found": True}
            except Exception:
                pass
        except Exception:
            pass

    # Fallback: Wikipedia REST API
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(query)}"
        r = requests.get(url, timeout=8)
        data = r.json()
        return {
            "title": data.get("title", query),
            "summary": data.get("extract", "Koi information nahi mili.")[:600],
            "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "found": bool(data.get("extract")),
        }
    except Exception as e:
        return {"error": str(e), "found": False}


# ─────────────────────────────────────────────────────────────────────────────
# 4. WEATHER — OpenWeatherMap (free tier, needs API key)
# ─────────────────────────────────────────────────────────────────────────────
def get_weather(city: str) -> dict:
    """OpenWeatherMap free tier. Key optional — falls back to wttr.in."""
    api_key = os.getenv("OPENWEATHER_API_KEY", "")

    # Try OpenWeatherMap
    if api_key:
        try:
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {"q": city, "appid": api_key, "units": "metric", "lang": "en"}
            r = requests.get(url, params=params, timeout=8)
            data = r.json()

            if data.get("cod") == 200:
                return {
                    "city": data["name"],
                    "country": data["sys"]["country"],
                    "temp": data["main"]["temp"],
                    "feels_like": data["main"]["feels_like"],
                    "humidity": data["main"]["humidity"],
                    "description": data["weather"][0]["description"],
                    "wind_speed": data["wind"]["speed"],
                    "visibility": data.get("visibility", 0) // 1000,
                    "source": "OpenWeatherMap",
                }
        except Exception:
            pass

    # Fallback: wttr.in (no key needed)
    try:
        url = f"https://wttr.in/{requests.utils.quote(city)}?format=j1"
        r = requests.get(url, timeout=8)
        data = r.json()
        current = data["current_condition"][0]
        area = data["nearest_area"][0]
        return {
            "city": area["areaName"][0]["value"],
            "country": area["country"][0]["value"],
            "temp": float(current["temp_C"]),
            "feels_like": float(current["FeelsLikeC"]),
            "humidity": int(current["humidity"]),
            "description": current["weatherDesc"][0]["value"],
            "wind_speed": float(current["windspeedKmph"]) / 3.6,
            "visibility": int(current["visibility"]),
            "source": "wttr.in",
        }
    except Exception as e:
        return {"error": f"Weather data nahi mila: {str(e)}", "city": city}


# ─────────────────────────────────────────────────────────────────────────────
# 5. CRYPTO — CoinGecko (100% FREE, no key needed)
# ─────────────────────────────────────────────────────────────────────────────
COIN_ID_MAP = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "solana": "solana", "sol": "solana",
    "bnb": "binancecoin", "binance": "binancecoin",
    "cardano": "cardano", "ada": "cardano",
    "xrp": "ripple", "ripple": "ripple",
    "polygon": "matic-network", "matic": "matic-network",
    "litecoin": "litecoin", "ltc": "litecoin",
    "shiba": "shiba-inu", "shib": "shiba-inu",
}

def get_crypto_price(symbol: str) -> dict:
    """CoinGecko — 100% free, no API key needed."""
    coin_id = COIN_ID_MAP.get(symbol.lower(), symbol.lower())
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": coin_id,
            "vs_currencies": "usd,inr",
            "include_24hr_change": "true",
            "include_market_cap": "true",
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        if coin_id in data:
            coin_data = data[coin_id]
            return {
                "coin": symbol.upper(),
                "coin_id": coin_id,
                "price_usd": coin_data.get("usd", 0),
                "price_inr": coin_data.get("inr", 0),
                "change_24h": round(coin_data.get("usd_24h_change", 0), 2),
                "market_cap_usd": coin_data.get("usd_market_cap", 0),
                "source": "CoinGecko",
            }
        return {"error": f"{symbol} nahi mila CoinGecko pe", "coin": symbol}
    except Exception as e:
        return {"error": str(e), "coin": symbol}


# ─────────────────────────────────────────────────────────────────────────────
# 6. STOCKS — Alpha Vantage (free tier, needs API key)
# ─────────────────────────────────────────────────────────────────────────────
def get_stock_price(symbol: str) -> dict:
    """Alpha Vantage free tier. Falls back to Yahoo Finance scraping."""
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "")

    if api_key:
        try:
            url = "https://www.alphavantage.co/query"
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": symbol,
                "apikey": api_key,
            }
            r = requests.get(url, params=params, timeout=10)
            data = r.json().get("Global Quote", {})
            if data.get("05. price"):
                return {
                    "symbol": symbol,
                    "price": float(data["05. price"]),
                    "change": float(data.get("09. change", 0)),
                    "change_percent": data.get("10. change percent", "0%"),
                    "volume": int(data.get("06. volume", 0)),
                    "source": "Alpha Vantage",
                }
        except Exception:
            pass

    # Fallback: Yahoo Finance
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://finance.yahoo.com/quote/{symbol}"
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        price_el = soup.find("fin-streamer", {"data-field": "regularMarketPrice"})
        change_el = soup.find("fin-streamer", {"data-field": "regularMarketChangePercent"})

        price = float(price_el["value"]) if price_el and price_el.get("value") else None
        change = float(change_el["value"]) if change_el and change_el.get("value") else None

        if price:
            return {
                "symbol": symbol,
                "price": price,
                "change_percent": f"{change:.2f}%" if change else "N/A",
                "source": "Yahoo Finance",
            }
    except Exception:
        pass

    return {"error": f"{symbol} ka price nahi mila", "symbol": symbol}


# ─────────────────────────────────────────────────────────────────────────────
# 7. CRICKET — ESPN Cricinfo scraping (FREE)
# ─────────────────────────────────────────────────────────────────────────────
def get_cricket_scores() -> dict:
    """ESPN Cricinfo live scores scraping."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    matches = []

    # Try ESPN Cricinfo API
    try:
        url = "https://www.espncricinfo.com/ci/engine/match/index.html?view=live"
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        match_cards = soup.select(".match-info, .score-strip__info, [class*='match']")
        for card in match_cards[:5]:
            text = card.get_text(strip=True)
            if text and len(text) > 10:
                matches.append({"info": text[:200]})
    except Exception:
        pass

    # Fallback: Cricbuzz RSS
    if not matches:
        try:
            feed = feedparser.parse("https://www.cricbuzz.com/cricket-news/rss-feeds/33")
            for entry in feed.entries[:5]:
                matches.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", "")[:200],
                    "link": entry.get("link", ""),
                })
        except Exception:
            pass

    # Fallback: Google News for cricket
    if not matches:
        news = get_news("cricket score today live", max_items=5)
        matches = news.get("articles", [])

    return {"matches": matches, "total": len(matches), "source": "ESPN/Cricbuzz"}


# ─────────────────────────────────────────────────────────────────────────────
# 8. TRANSLATION — LibreTranslate (100% FREE)
# ─────────────────────────────────────────────────────────────────────────────
LIBRE_INSTANCES = [
    "https://libretranslate.com",
    "https://translate.argosopentech.com",
    "https://libretranslate.de",
]

def translate_text(text: str, source: str = "auto", target: str = "hi") -> dict:
    """LibreTranslate — 100% free, multiple fallback instances."""
    for instance in LIBRE_INSTANCES:
        try:
            r = requests.post(
                f"{instance}/translate",
                json={"q": text, "source": source, "target": target, "format": "text"},
                timeout=12,
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("translatedText"):
                    return {
                        "original": text,
                        "translated": data["translatedText"],
                        "source_lang": source,
                        "target_lang": target,
                        "instance": instance,
                    }
        except Exception:
            continue

    # Fallback: MyMemory (free, no key needed)
    try:
        lang_pair = f"{source}|{target}" if source != "auto" else f"en|{target}"
        r = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text[:500], "langpair": lang_pair},
            timeout=10,
        )
        data = r.json()
        if data.get("responseData", {}).get("translatedText"):
            return {
                "original": text,
                "translated": data["responseData"]["translatedText"],
                "source_lang": source,
                "target_lang": target,
                "instance": "MyMemory",
            }
    except Exception as e:
        return {"error": str(e), "original": text}

    return {"error": "Translation failed. Baad mein try karo.", "original": text}


# ─────────────────────────────────────────────────────────────────────────────
# 9. PDF TEXT EXTRACTION — PyPDF2 (FREE)
# ─────────────────────────────────────────────────────────────────────────────
def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF using PyPDF2."""
    if not PDF_OK:
        return "PyPDF2 install nahi hai. `pip install PyPDF2` run karo."

    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text_parts = []
        for i, page in enumerate(reader.pages[:20]):  # max 20 pages
            text = page.extract_text()
            if text:
                text_parts.append(f"[Page {i+1}]\n{text}")

        return "\n\n".join(text_parts) if text_parts else "PDF mein readable text nahi mila."
    except Exception as e:
        return f"PDF read error: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# 10. IMAGE OCR — Tesseract (FREE)
# ─────────────────────────────────────────────────────────────────────────────
def extract_text_from_image_ocr(file_bytes: bytes) -> str:
    """Extract text from image using Tesseract OCR."""
    if not OCR_OK:
        return ""

    try:
        img = Image.open(io.BytesIO(file_bytes))
        # Try Hindi + English
        text = pytesseract.image_to_string(img, lang="hin+eng")
        if not text.strip():
            text = pytesseract.image_to_string(img, lang="eng")
        return text.strip()
    except Exception:
        try:
            img = Image.open(io.BytesIO(file_bytes))
            return pytesseract.image_to_string(img).strip()
        except Exception as e:
            return f"OCR error: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# 11. VIDEO ANALYSIS — OpenCV (FREE)
# ─────────────────────────────────────────────────────────────────────────────
def analyze_video(file_bytes: bytes, filename: str = "video.mp4") -> dict:
    """Basic video metadata extraction using OpenCV."""
    if not CV2_OK:
        return {
            "error": "OpenCV install nahi hai",
            "filename": filename,
            "note": "pip install opencv-python",
        }

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            return {"error": "Video open nahi hua", "filename": filename}

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = frame_count / fps if fps > 0 else 0

        # Extract sample frames for color analysis
        sample_frames = []
        step = max(1, frame_count // 5)
        for i in range(0, min(frame_count, frame_count), step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if ret:
                avg_color = frame.mean(axis=(0, 1)).tolist()
                sample_frames.append({
                    "frame": i,
                    "avg_color_bgr": [round(c, 1) for c in avg_color],
                })
            if len(sample_frames) >= 5:
                break

        cap.release()

        return {
            "filename": filename,
            "resolution": f"{width}x{height}",
            "fps": round(fps, 2),
            "total_frames": frame_count,
            "duration_seconds": round(duration, 2),
            "duration_readable": f"{int(duration//60)}m {int(duration%60)}s",
            "file_size_kb": round(len(file_bytes) / 1024, 1),
            "sample_frames": sample_frames,
        }
    except Exception as e:
        return {"error": str(e), "filename": filename}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# 12. INTELLIGENT REQUEST ROUTING
# ─────────────────────────────────────────────────────────────────────────────
ROUTING_KEYWORDS = {
    "weather": [
        "weather", "mausam", "barish", "rain", "temperature", "temp", "humidity",
        "aaj ka mausam", "garmi", "sardi", "thand", "forecast", "climate"
    ],
    "crypto": [
        "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency", "coin", "dogecoin"
    ]
}

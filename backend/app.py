# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
from dotenv import load_dotenv
import os
import traceback
import json
import re
import random

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

API_KEY = os.getenv("GENAI_API_KEY")
if not API_KEY:
    print("WARNING: GENAI_API_KEY not set in environment. Set it in your .env for real requests.")
genai.configure(api_key=API_KEY)

# create model handle (keep your configured model)
model = genai.GenerativeModel("gemini-2.0-flash")

# Load intents.json at startup
INTENTS_PATH = os.path.join(os.path.dirname(__file__), "intents.json")
try:
    with open(INTENTS_PATH, "r", encoding="utf-8") as f:
        intents_data = json.load(f)
        intents = intents_data.get("intents", intents_data) if isinstance(intents_data, dict) else intents_data
except Exception as e:
    print(f"Could not load intents.json from {INTENTS_PATH}: {e}")
    intents = []

def normalize_text(s: str) -> str:
    """Lowercase, remove punctuation, collapse whitespace for robust matching."""
    if not isinstance(s, str):
        return ""
    s = s.lower()
    # replace any non-word characters with space (keeps letters/numbers/underscore)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

# Precompute normalized patterns for matching
for intent in intents:
    patterns = intent.get("patterns", [])
    intent["_patterns_norm"] = [normalize_text(p) for p in patterns if isinstance(p, str)]

def extract_user_text_from_request(data):
    # (same robust extraction as before)
    messages = data.get("messages")
    if isinstance(messages, list) and len(messages) > 0:
        for m in reversed(messages):
            sender = (m.get("sender") or "").lower()
            if sender == "user":
                return m.get("text", "") or ""
        last = messages[-1]
        return last.get("text", "") if isinstance(last, dict) else str(last)

    contents = data.get("contents")
    if isinstance(contents, list) and len(contents) > 0:
        for c in reversed(contents):
            if isinstance(c, dict):
                if "text" in c and isinstance(c["text"], str):
                    return c["text"]
                if "parts" in c and isinstance(c["parts"], list) and len(c["parts"]) > 0:
                    p0 = c["parts"][-1]
                    if isinstance(p0, dict) and "text" in p0:
                        return p0["text"]
            elif isinstance(c, str):
                return c
        last = contents[-1]
        return last.get("text", "") if isinstance(last, dict) else str(last)

    if "text" in data and isinstance(data["text"], str):
        return data["text"]

    return ""

def match_intent(user_text):
    """
    Return (matched_intent_obj, matched_pattern_index) or (None, None)
    We try:
      1) exact normalized equality
      2) normalized pattern in normalized text (substring)
      3) normalized text in normalized pattern
    """
    if not user_text:
        return None, None
    text_norm = normalize_text(user_text)

    for intent in intents:
        tag = intent.get("tag", "")
        # Optional: skip catch-all fallback intents if you want AI fallback
        if tag == "unrecognized_input":
            continue

        patterns_norm = intent.get("_patterns_norm", [])
        for idx, patt_norm in enumerate(patterns_norm):
            if not patt_norm:
                continue
            # 1) exact normalized match
            if patt_norm == text_norm:
                return intent, idx
            # 2) substring matches (pattern in user text)
            if patt_norm in text_norm:
                return intent, idx
            # 3) user text contained in pattern (rare but useful)
            if text_norm in patt_norm:
                return intent, idx

    return None, None

@app.route("/")
def home():
    return "Flask backend is running! Use /chat or /api/chat to chat."

@app.route("/chat", methods=["OPTIONS", "POST"])
@app.route("/api/chat", methods=["OPTIONS", "POST"])
def chat():
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200

    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    messages = data.get("messages")
    contents = data.get("contents")
    if not messages and not contents and not data.get("text"):
        return jsonify({"error": "No messages/contents provided or invalid format"}), 400

    user_text = extract_user_text_from_request(data)
    print("User text extracted:", user_text)

    # Try local intents first
    intent_obj, patt_idx = match_intent(user_text)
    if intent_obj:
        responses = intent_obj.get("responses", [])
        reply_text = None
        # Prefer a response at the same index as the matched pattern
        if patt_idx is not None and isinstance(patt_idx, int) and patt_idx < len(responses):
            reply_text = responses[patt_idx]
        elif len(responses) == 1:
            reply_text = responses[0]
        elif len(responses) > 1:
            # fallback: find any response that contains some keywords? for now pick random
            # (but we prefer to avoid random if user expects a specific answer)
            reply_text = random.choice(responses)

        if reply_text:
            return jsonify({"reply": reply_text, "source": "intents", "intent": intent_obj.get("tag")}), 200

    # No local intent match -> send to AI (Gemini)
    # Normalize into the expected structure
    normalized = []
    if messages and isinstance(messages, list):
        for m in messages:
            role = m.get("sender", "").lower()
            if role not in ("user", "bot", "model", "assistant"):
                role = "model" if role == "bot" else "user"
            text = m.get("text", "")
            normalized.append({"role": "user" if role == "user" else "model", "parts": [{"text": text}]})
    elif contents and isinstance(contents, list):
        for c in contents:
            if isinstance(c, dict) and "role" in c and "parts" in c:
                normalized.append(c)
            elif isinstance(c, dict) and "text" in c:
                normalized.append({"role": "user", "parts": [{"text": c["text"]}]})
            else:
                normalized.append({"role": "user", "parts": [{"text": str(c)}]})
    else:
        normalized.append({"role": "user", "parts": [{"text": user_text}]})

    print("Normalized request to send to Gemini:", normalized)

    try:
        response = model.generate_content(normalized)

        reply_text = None
        if hasattr(response, "text") and getattr(response, "text"):
            reply_text = getattr(response, "text")
        elif isinstance(response, dict):
            if response.get("reply"):
                reply_text = response.get("reply")
            elif response.get("text"):
                reply_text = response.get("text")
            elif response.get("candidates"):
                try:
                    reply_text = response["candidates"][0]["content"]["parts"][0]["text"]
                except Exception:
                    reply_text = None
        else:
            candidates = getattr(response, "candidates", None)
            if candidates:
                try:
                    cand0 = candidates[0]
                    content = cand0.get("content") if isinstance(cand0, dict) else getattr(cand0, "content", None)
                    if content:
                        parts = content.get("parts") if isinstance(content, dict) else getattr(content, "parts", None)
                        if parts and len(parts) > 0:
                            part0 = parts[0]
                            reply_text = part0.get("text") if isinstance(part0, dict) else getattr(part0, "text", None)
                except Exception:
                    reply_text = None

        if not reply_text:
            try:
                reply_text = str(response)
            except Exception:
                reply_text = "No textual reply found in model response."

        return jsonify({"reply": reply_text, "source": "ai"}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Error calling Gemini API: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

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
# Dev CORS - allow everything for local development
CORS(app, resources={r"/*": {"origins": "*"}})

API_KEY = os.getenv("GENAI_API_KEY")
if not API_KEY:
    print("WARNING: GENAI_API_KEY not set in environment. Set it in your .env for real requests.")
genai.configure(api_key=API_KEY)

# create model handle
model = genai.GenerativeModel("gemini-2.0-flash")

# Load intents.json at startup
INTENTS_PATH = os.path.join(os.path.dirname(__file__), "intents.json")
try:
    with open(INTENTS_PATH, "r", encoding="utf-8") as f:
        intents_data = json.load(f)
        # Expecting the top-level structure to be {"intents": [...]}
        intents = intents_data.get("intents", intents_data) if isinstance(intents_data, dict) else intents_data
except Exception as e:
    print(f"Could not load intents.json from {INTENTS_PATH}: {e}")
    intents = []

# Preprocess patterns for faster matching (lowercase)
for intent in intents:
    patterns = intent.get("patterns", [])
    intent["_patterns_lc"] = [p.lower() for p in patterns if isinstance(p, str)]

def extract_user_text_from_request(data):
    """
    Return the most relevant user text to match against intents or send to Gemini.
    Supports:
      - {"messages": [{ "sender":"user"/"bot", "text": "..." }, ...]}
      - {"contents": [ ... ]} where elements may be {"text":"..."} or generative format
    Strategy:
      - If 'messages' exists, take the last message whose sender is 'user' (case-insensitive)
        or the last message overall if no explicit user entry.
      - Else, if 'contents' is present, take the last dict element that has 'text' or parts.
      - Else, fallback to empty string.
    """
    # messages style
    messages = data.get("messages")
    if isinstance(messages, list) and len(messages) > 0:
        # find last user message
        for m in reversed(messages):
            sender = (m.get("sender") or "").lower()
            if sender == "user":
                return m.get("text", "") or ""
        # fallback: last message text
        last = messages[-1]
        return last.get("text", "") if isinstance(last, dict) else str(last)

    # contents style
    contents = data.get("contents")
    if isinstance(contents, list) and len(contents) > 0:
        # look for dicts with 'text' or 'parts'
        for c in reversed(contents):
            if isinstance(c, dict):
                if "text" in c and isinstance(c["text"], str):
                    return c["text"]
                if "parts" in c and isinstance(c["parts"], list) and len(c["parts"]) > 0:
                    # parts are often [{"text":"..."}]
                    p0 = c["parts"][-1]
                    if isinstance(p0, dict) and "text" in p0:
                        return p0["text"]
            elif isinstance(c, str):
                return c
        # fallback: stringify last element
        last = contents[-1]
        return last.get("text", "") if isinstance(last, dict) else str(last)

    # try message raw 'text' field
    if "text" in data and isinstance(data["text"], str):
        return data["text"]

    return ""

def match_intent(user_text):
    """
    Try to match user_text to an intent in intents (loaded from intents.json).
    Simple strategy:
      - Lowercase the user_text.
      - For each pattern in intents, check if the pattern is a substring of user_text or vice-versa.
      - Prefer exact word-boundary matches where possible.
      - Ignore the 'unrecognized_input' tag to avoid accidentally matching a catch-all pattern like '.*'.
    Returns: (intent_obj or None)
    """
    if not user_text:
        return None
    text = user_text.lower()

    # clean text for word-boundary searching
    for intent in intents:
        tag = intent.get("tag", "")
        # skip the catch-all / fallback intent because we want to fallback to AI instead
        if tag == "unrecognized_input":
            continue

        patterns = intent.get("_patterns_lc", [])
        for patt in patterns:
            if not patt:
                continue
            # If the pattern looks like a plain phrase, try word-boundary match first
            try:
                # escape and use word boundaries
                escaped = re.escape(patt)
                # If pattern contains non-word characters/spaces, simple in-check is fine
                if re.search(r"\b" + escaped + r"\b", text):
                    return intent
            except re.error:
                # fallback to substring when regex escaping fails
                pass

            # substring checks (pattern in text or text in pattern)
            if patt in text or text in patt:
                return intent

    return None

@app.route("/")
def home():
    return "Flask backend is running! Use /chat or /api/chat to chat."

# Both endpoints map to same handler so frontend can call /chat or /api/chat
@app.route("/chat", methods=["OPTIONS", "POST"])
@app.route("/api/chat", methods=["OPTIONS", "POST"])
def chat():
    # Flask-CORS handles OPTIONS, but we accept it to avoid 404s in some setups
    if request.method == "OPTIONS":
        return jsonify({"ok": True}), 200

    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    messages = data.get("messages")
    contents = data.get("contents")
    if not messages and not contents and not data.get("text") and not data.get("contents"):
        return jsonify({"error": "No messages/contents provided or invalid format"}), 400

    # Extract the single user text we will attempt to answer from intents.json first
    user_text = extract_user_text_from_request(data)
    print("Extracted user text for intent matching / AI:", user_text)

    # 1) Try to match to intents.json
    matched_intent = match_intent(user_text)
    if matched_intent:
        # choose a random response from intent
        responses = matched_intent.get("responses", [])
        if responses:
            reply_text = random.choice(responses)
            return jsonify({"reply": reply_text, "source": "intents", "intent": matched_intent.get("tag")}), 200

    # 2) No intent match -> fall back to AI (Gemini)
    # Normalize into a list of content-parts acceptable to your model.generate_content usage
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
        # fallback: use the extracted user_text as single user message
        normalized.append({"role": "user", "parts": [{"text": user_text}]})

    print("Normalized request to send to Gemini:", normalized)

    try:
        response = model.generate_content(normalized)

        # Robustly extract text from different response shapes
        reply_text = None

        # 1) Some SDKs return an object with .text
        if hasattr(response, "text") and getattr(response, "text"):
            reply_text = getattr(response, "text")

        # 2) dict-style (from .to_dict() or JSON)
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

        # 3) object with candidates attribute
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

        print("Reply extracted from AI:", reply_text)
        return jsonify({"reply": reply_text, "source": "ai"}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Error calling Gemini API: {str(e)}"}), 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))  # Use Render's PORT if available
    app.run(host="0.0.0.0", port=port, debug=True)

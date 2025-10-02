# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
from dotenv import load_dotenv
import os
import traceback

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

    # Accept either:
    # - {"messages": [{ "sender":"user"/"bot", "text": "..." }, ...]}
    # - {"contents": [ ... ]}  (the shape your frontend builds)
    messages = data.get("messages")
    contents = data.get("contents")

    if not messages and not contents:
        return jsonify({"error": "No messages/contents provided or invalid format"}), 400

    # Normalize into a list of content-parts acceptable to your model.generate_content usage
    normalized = []

    if messages and isinstance(messages, list):
        for m in messages:
            role = m.get("sender", "").lower()
            if role not in ("user", "bot", "model", "assistant"):
                # fallback: if it's 'bot' treat as 'model'
                role = "model" if role == "bot" else "user"
            text = m.get("text", "")
            normalized.append({"role": "user" if role == "user" else "model", "parts": [{"text": text}]})
    elif contents and isinstance(contents, list):
        # assume contents is already in the generative format or similar
        # try to convert if it's an array of {role, parts} or an array of {text}
        for c in contents:
            if isinstance(c, dict) and "role" in c and "parts" in c:
                normalized.append(c)
            elif isinstance(c, dict) and "text" in c:
                # treat as user text
                normalized.append({"role": "user", "parts": [{"text": c["text"]}]})
            else:
                # fallback: stringify
                normalized.append({"role": "user", "parts": [{"text": str(c)}]})

    print("Normalized request to send to Gemini:", normalized)

    try:
        # call the model
        # NOTE: the google.generativeai python client returns objects/dicts differently depending on version
        # we call generate_content with normalized list; adjust if your SDK expects other args
        response = model.generate_content(normalized)

        # Robustly extract text from different response shapes
        reply_text = None

        # 1) Some SDKs return an object with .text
        if hasattr(response, "text") and getattr(response, "text"):
            reply_text = getattr(response, "text")

        # 2) dict-style (from .to_dict() or JSON)
        elif isinstance(response, dict):
            # check common keys
            if response.get("reply"):
                reply_text = response.get("reply")
            elif response.get("text"):
                reply_text = response.get("text")
            elif response.get("candidates"):
                # dig into candidates
                try:
                    reply_text = response["candidates"][0]["content"]["parts"][0]["text"]
                except Exception:
                    reply_text = None

        # 3) object with candidates attribute
        else:
            candidates = getattr(response, "candidates", None)
            if candidates:
                try:
                    # handle candidate as list of dict-like
                    cand0 = candidates[0]
                    # try attribute access
                    content = cand0.get("content") if isinstance(cand0, dict) else getattr(cand0, "content", None)
                    if content:
                        parts = content.get("parts") if isinstance(content, dict) else getattr(content, "parts", None)
                        if parts and len(parts) > 0:
                            part0 = parts[0]
                            reply_text = part0.get("text") if isinstance(part0, dict) else getattr(part0, "text", None)
                except Exception:
                    reply_text = None

        # final fallback: stringify the response
        if not reply_text:
            try:
                reply_text = str(response)
            except Exception:
                reply_text = "No textual reply found in model response."

        print("Reply extracted:", reply_text)
        return jsonify({"reply": reply_text}), 200

    except Exception as e:
        # large debug print for local dev
        traceback.print_exc()
        return jsonify({"error": f"Error calling Gemini API: {str(e)}"}), 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))  # Use Render's PORT if available
    app.run(host="0.0.0.0", port=port, debug=True)


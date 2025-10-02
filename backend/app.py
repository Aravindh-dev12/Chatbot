import os
import json
import difflib
import traceback
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

# Config
INTENTS_FILE = Path("intents.json")
CHAT_HISTORY_FILE = Path("chat_history.json")
MATCH_CUTOFF = 0.60  # difflib cutoff for a "good" match (0..1)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5")  # override if needed

app = Flask(__name__)
CORS(app)

# Load intents
if not INTENTS_FILE.exists():
    raise FileNotFoundError(f"{INTENTS_FILE} not found. Add your intents.json in project root.")
with INTENTS_FILE.open("r", encoding="utf-8") as f:
    INTENTS = json.load(f)

# Build pattern -> tag map and tag -> responses
pattern_to_tag = {}
tag_to_responses = {}
all_patterns = []
for intent in INTENTS.get("intents", []):
    tag = intent.get("tag")
    tag_to_responses[tag] = intent.get("responses", [])
    for p in intent.get("patterns", []):
        norm = p.strip().lower()
        pattern_to_tag[norm] = tag
        all_patterns.append(norm)


def best_kb_match(user_text, cutoff=MATCH_CUTOFF):
    """
    Return (tag, response, score) if a match found above cutoff, else (None, None, 0)
    """
    q = user_text.strip().lower()
    if not q:
        return None, None, 0.0

    # get close pattern matches
    matches = difflib.get_close_matches(q, all_patterns, n=3, cutoff=cutoff)
    if matches:
        best = matches[0]
        tag = pattern_to_tag[best]
        responses = tag_to_responses.get(tag) or []
        # rotate / pick first
        resp = responses[0] if responses else "Sorry, no canned response available."
        # compute ratio as score
        score = difflib.SequenceMatcher(None, q, best).ratio()
        return tag, resp, score

    # No direct close-match: try fuzzy score against each pattern to find highest score
    best_score = 0.0
    best_pattern = None
    for p in all_patterns:
        score = difflib.SequenceMatcher(None, q, p).ratio()
        if score > best_score:
            best_score = score
            best_pattern = p
    if best_score >= cutoff:
        tag = pattern_to_tag[best_pattern]
        resp = tag_to_responses.get(tag, [""])[0]
        return tag, resp, best_score

    return None, None, 0.0


def save_chat_history(question, answer, source, intent_tag=None):
    try:
        entry = {
            "question": question,
            "answer": answer,
            "intent": intent_tag,
            "source": source,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        }
        data = []
        if CHAT_HISTORY_FILE.exists():
            try:
                with CHAT_HISTORY_FILE.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = []

        data.append(entry)

        # keep only last 200 entries to avoid unbounded growth
        data = data[-200:]
        with CHAT_HISTORY_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        # don't crash on history save errors
        traceback.print_exc()


def call_gemini(prompt_text):
    """
    Attempts to call Gemini using google.generativeai client.
    Returns tuple (reply_text, error_if_any)
    The function tries several common shapes of responses to be robust across SDK versions.
    """
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "Gemini API key not configured. Set environment variable GOOGLE_API_KEY."

    try:
        import google.generativeai as genai
    except Exception as e:
        return None, ("google-generativeai package not installed or import failed: " + str(e))

    try:
        # configure client
        # note: some older/newer versions use different config APIs
        try:
            genai.configure(api_key=api_key)
        except Exception:
            # some releases prefer direct assignment
            try:
                genai.api_key = api_key
            except Exception:
                pass

        # Attempt several call styles to maximize compatibility
        # 1) genai.generate_text (simple)
        if hasattr(genai, "generate_text"):
            try:
                resp = genai.generate_text(model=GEMINI_MODEL, text=prompt_text)
                # resp may be object or dict-like
                if hasattr(resp, "text") and getattr(resp, "text"):
                    return getattr(resp, "text"), None
                if isinstance(resp, dict):
                    # try common keys
                    for k in ("output", "response", "candidates", "text"):
                        if k in resp:
                            # try to extract text
                            val = resp[k]
                            if isinstance(val, str):
                                return val, None
                            if isinstance(val, dict) and "text" in val:
                                return val["text"], None
                            if isinstance(val, list) and len(val) and isinstance(val[0], dict):
                                # candidate list
                                candidate = val[0]
                                # nested content
                                if "content" in candidate and isinstance(candidate["content"], dict):
                                    parts = candidate["content"].get("parts")
                                    if parts and isinstance(parts, list) and parts:
                                        return parts[0], None
                                # try candidate.get("text")
                                if "text" in candidate:
                                    return candidate["text"], None
                # fallback stringify
                return str(resp), None
            except Exception:
                traceback.print_exc()

        # 2) genai.generate (newer generic generate with messages / input)
        if hasattr(genai, "generate"):
            try:
                # Try a simple call shape
                resp = genai.generate(model=GEMINI_MODEL, text=prompt_text)
                # parse
                if isinstance(resp, dict):
                    # check candidates
                    candidates = resp.get("candidates") or resp.get("outputs")
                    if candidates and isinstance(candidates, list) and candidates:
                        first = candidates[0]
                        # try several nested paths
                        text = None
                        if isinstance(first, dict):
                            # content.parts style
                            content = first.get("content")
                            if content and isinstance(content, dict):
                                parts = content.get("parts")
                                if parts and len(parts) > 0:
                                    text = parts[0]
                            if not text and "output" in first:
                                text = first.get("output")
                            if not text and "text" in first:
                                text = first.get("text")
                        if text:
                            return text, None
                return str(resp), None
            except Exception:
                traceback.print_exc()

        # 3) genai.client or model objects pattern (older sample code)
        # Try to find any callable in genai module that might accept 'prompt' or 'messages'
        for fn_name in ("client", "models", "Model", "TextModel"):
            fn = getattr(genai, fn_name, None)
            if fn:
                try:
                    # naive attempt: call with prompt
                    maybe = fn(prompt_text)
                    if maybe:
                        return str(maybe), None
                except Exception:
                    continue

        return None, "Could not call Gemini with installed google-generativeai client; check SDK version & docs."

    except Exception as e:
        traceback.print_exc()
        return None, f"Error when calling Gemini: {str(e)}"


@app.route("/ask", methods=["POST"])
def ask():
    """
    Request JSON: { "question": "..." }
    Response JSON: { "reply": "...", "intent": "<tag or null>", "source": "kb|gemini|error", "score": float }
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    question = data.get("question") or data.get("q") or data.get("text")
    if not question:
        return jsonify({"error": "Missing 'question' field in JSON"}), 400

    # 1) Try KB match
    intent_tag, kb_response, score = best_kb_match(question, cutoff=MATCH_CUTOFF)
    if intent_tag:
        # found KB match
        save_chat_history(question, kb_response, source="kb", intent_tag=intent_tag)
        return jsonify({
            "reply": kb_response,
            "intent": intent_tag,
            "source": "kb",
            "score": score
        }), 200

    # 2) No good KB match: fall back to Gemini
    gemini_prompt = (
        "You are a helpful assistant. The user asked: "
        + question
        + "\n\nRespond concisely (1-3 short paragraphs). If the question is about current events, mention when you were last updated."
    )
    reply_text, err = call_gemini(gemini_prompt)
    if err:
        # return helpful error to user (still include KB fallback message)
        fallback_msg = "I couldn't find a close match in my local knowledge base."
        save_chat_history(question, fallback_msg, source="fallback_no_gemini", intent_tag=None)
        return jsonify({
            "reply": fallback_msg,
            "intent": None,
            "source": "error",
            "error": err
        }), 503

    # success from Gemini
    save_chat_history(question, reply_text, source="gemini", intent_tag=None)
    return jsonify({
        "reply": reply_text,
        "intent": None,
        "source": "gemini",
        "score": None
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

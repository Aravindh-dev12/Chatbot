from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
from dotenv import load_dotenv
import os

load_dotenv()  # Load variables from .env

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("GENAI_API_KEY")
genai.configure(api_key=API_KEY)

model = genai.GenerativeModel("gemini-2.0-flash")

@app.route("/")
def home():
    return "Flask backend is running! Go to /api/chat to chat."

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages")

    if not messages or not isinstance(messages, list):
        return jsonify({"error": "No messages provided or invalid format"}), 400

    contents = []
    for msg in messages:
        role = "user" if msg.get("sender") == "user" else "model"
        text = msg.get("text", "")

        if role not in ["user", "model"]:
            continue  

        contents.append({"role": role, "parts": [{"text": text}]})

    print("Sending request to Gemini API:", contents)

    try:
        response = model.generate_content(contents)
        return jsonify({"reply": response.text})
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(port=5000, debug=True)

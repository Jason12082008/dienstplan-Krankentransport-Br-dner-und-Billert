import os
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Liest den Gemini API-Key sicher aus den Render-Umgebungsvariablen
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

@app.route('/')
def home():
    return "Dienstplan-Backend läuft 24/7!"

@app.route('/scan', methods=['POST'])
def scan_roster():
    try:
        data = request.json
        image_base64 = data.get('image')
        user_name = data.get('name')

        if not image_base64 or not user_name:
            return jsonify({"error": "Bild oder Name fehlt"}), 400

        if not GEMINI_API_KEY:
            return jsonify({"error": "GEMINI_API_KEY ist auf dem Server nicht konfiguriert"}), 500

        # Eventuelles Data-URI-Präfix entfernen
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]

        prompt_text = f"""Analyze this shift roster image.
Extract the complete roster for every day: list all scheduled shifts and the employee names assigned to them.
Return ONLY a valid JSON array without any markdown formatting, formatted exactly like this:
[
  {{
    "day": 1,
    "shifts": [
      {{"shift": "K1", "employees": ["Müller", "{user_name}"]}},
      {{"shift": "K9", "employees": ["Meier"]}}
    ]
  }}
]
Normalize shift codes (e.g. K1, K4, K5, K9, etc.)."""

        # Verwendung von gemini-3.6-flash
        ai_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={GEMINI_API_KEY}"
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt_text},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_base64
                        }
                    }
                ]
            }],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1
            }
        }

        response = requests.post(ai_url, json=payload, timeout=40)
        res_data = response.json()

        if "error" in res_data:
            return jsonify({"error": res_data["error"].get("message", "KI-Fehler")}), 500

        text_response = res_data["candidates"][0]["content"]["parts"][0]["text"]
        parsed_shifts = json.loads(text_response)

        return jsonify({"success": True, "shifts": parsed_shifts})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
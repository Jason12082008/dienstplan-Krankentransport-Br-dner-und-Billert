import os
from flask import Flask, request, jsonify
# Hier würden später die OCR-Bibliotheken (z.B. pytesseract oder eine smarte API) eingebunden werden

app = Flask(__name__)

@app.route('/')
def home():
    return "Dienstplan-Backend läuft 24/7!"

@app.route('/scan-roster', methods=['POST'])
def scan_roster():
    try:
        data = request.json
        image_base64 = data.get('image')
        user_name = data.get('name')
        year = data.get('year')
        month = data.get('month')

        if not image_base64 or not user_name:
            return jsonify({"error": "Bild oder Name fehlt"}), 400

        # Hier findet später die eigene Logik / OCR-Verarbeitung statt,
        # die das Bild ausliest und die Schichten für den Mitarbeiter filtert.

        # Beispiel-Antwort als Test:
        mock_roster = [
            {
                "day": 1,
                "shifts": [
                    {"shift": "K1", "employees": [user_name, "Kollege"]}
                ]
            }
        ]

        return jsonify({"success": True, "roster": mock_roster})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
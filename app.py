import os
from flask import Flask, request, jsonify

app = Flask(__name__)

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

        # Erweiterte Test-Daten für mehrere Tage im Monat
        # - Tag 21: Du bist in K1 eingeteilt, Kollege in K5 (Beide sollen unter Schichten & Fahrzeuge stehen, nur K1 im Kalender)
        # - Tag 22: Du bist in K9 (Nacht) eingeteilt
        # - Tag 23: Andere Kollegen haben Dienst (stehen unter Schichten & Fahrzeuge, aber nicht in deinem Kalender)
        mock_shifts = [
            {
                "day": 21,
                "shifts": [
                    {"shift": "K1", "employees": [user_name, "M. Müller"]},
                    {"shift": "K5", "employees": ["T. Becker", "S. Koch"]}
                ]
            },
            {
                "day": 22,
                "shifts": [
                    {"shift": "K9", "employees": [user_name, "D. Weber"]}
                ]
            },
            {
                "day": 23,
                "shifts": [
                    {"shift": "K4", "employees": ["J. Meyer", "K. Braun"]}
                ]
            }
        ]

        return jsonify({"success": True, "shifts": mock_shifts})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
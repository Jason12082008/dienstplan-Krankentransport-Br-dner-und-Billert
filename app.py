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

        # Mock-Roster mit dem Schlüssel "shifts"
        mock_shifts = [
            {
                "day": 1,
                "shifts": [
                    {"shift": "K1", "employees": [user_name, "Kollege"]}
                ]
            }
        ]

        return jsonify({"success": True, "shifts": mock_shifts})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
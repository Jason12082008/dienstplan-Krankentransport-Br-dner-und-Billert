import os
import io
import re
import base64
from flask import Flask, request, jsonify
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
from pytesseract import Output

# Tesseract-Pfad für den Docker-Container auf Render
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

app = Flask(__name__)

# Native CORS-Header für die mobile App
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    return response

# Bekannte Schichtkürzel laut Dienstplan
VALID_SHIFTS = {
    "K1", "K1x", "K2", "K4", "K5", "K6", "K7", "K8", "K9", "K10", "K11", "K12", "K15", "K18",
    "A1F", "A1S", "A1N", "A2F", "A2S", "LK", "BTW", "Büro", "Ruf", "U", "UW", "FnN", "Frei"
}

# Bekannte Kollegen als Erkennungsanker / Fallback
KNOWN_EMPLOYEES = [
    "Setzer", "Rathmann", "Wittke", "Gart", "Wischhusen", "Seidscheck",
    "Thüm", "Gradim", "Stang", "Boelkes", "Schwirz", "Martin",
    "Martens", "Garcia", "N.Behrendt", "Soller"
]

@app.route('/')
def home():
    return "Dienstplan-OCR-Backend ist online!"

@app.route('/test-ocr', methods=['GET'])
def test_ocr():
    try:
        version = pytesseract.get_tesseract_version()
        return jsonify({"success": True, "tesseract_version": str(version)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/scan', methods=['POST'])
def scan_roster():
    try:
        data = request.get_json()
        if not data or 'image' not in data:
            return jsonify({"error": "Keine Bilddaten übermittelt."}), 400

        user_search_name = data.get('name', '').strip()
        image_base64 = data['image']

        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]

        raw_img = Image.open(io.BytesIO(base64.b64decode(image_base64)))

        # 1. SPEED-BOOST: Bild runterskalieren (senkt Berechnungszeit von 60s auf ~10s)
        max_dim = 1800
        raw_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        # 2. Kontrast optimieren & Graustufen für scharfe Kanten
        gray = ImageOps.grayscale(raw_img)
        enhancer = ImageEnhance.Contrast(gray)
        processed_img = enhancer.enhance(1.8)

        # 3. OCR mit genauen Wort-Koordinaten ausführen
        custom_config = r'--oem 1 --psm 6 -l deu'
        ocr_data = pytesseract.image_to_data(processed_img, config=custom_config, output_type=Output.DICT)

        tokens = []
        n_boxes = len(ocr_data['text'])
        for i in range(n_boxes):
            text = ocr_data['text'][i].strip()
            try:
                conf = int(ocr_data['conf'][i])
            except:
                conf = 0
            if text and conf > 20:
                tokens.append({
                    'text': text,
                    'x': ocr_data['left'][i],
                    'y': ocr_data['top'][i],
                    'w': ocr_data['width'][i],
                    'h': ocr_data['height'][i]
                })

        # 4. Tage (Zeilen) am linken Rand lokalisieren (z. B. '01.11.26', '02.11.')
        day_rows = {}
        for t in tokens:
            date_match = re.search(r'\b(0[1-9]|[12][0-9]|3[01])\.(1[0-2]|0[1-9])?', t['text'])
            if date_match and t['x'] < processed_img.width * 0.25:
                day_num = int(date_match.group(1))
                if day_num not in day_rows:
                    day_rows[day_num] = t['y']

        # 5. MITARBEITER DYNAMISCH AUS KOPFZEILE ERKENNEN
        col_positions = []
        first_day_y = min(day_rows.values()) if day_rows else None

        if first_day_y:
            header_min_y = max(0, first_day_y - 80)
            header_max_y = first_day_y - 5

            header_tokens = [
                t for t in tokens
                if header_min_y <= t['y'] <= header_max_y and t['x'] > processed_img.width * 0.13
            ]
            header_tokens.sort(key=lambda t: t['x'])

            for t in header_tokens:
                clean_name = re.sub(r'[^a-zA-ZäöüÄÖÜß\.\-]', '', t['text']).strip()
                if len(clean_name) >= 2:
                    for known in KNOWN_EMPLOYEES:
                        if known.lower() == clean_name.lower():
                            clean_name = known
                            break
                    col_positions.append({
                        'name': clean_name,
                        'x': t['x'] + (t['w'] // 2)
                    })

        # Fallback auf Standard-Spaltenraster, falls Kopfzeile abgeschnitten war
        if len(col_positions) < 4:
            start_x = int(processed_img.width * 0.18)
            end_x = int(processed_img.width * 0.95)
            step = (end_x - start_x) // len(KNOWN_EMPLOYEES)
            col_positions = [{'name': KNOWN_EMPLOYEES[idx], 'x': start_x + (idx * step)} for idx in range(len(KNOWN_EMPLOYEES))]
        else:
            col_positions.sort(key=lambda c: c['x'])

        # 6. Schichtkürzel den (Tag, Mitarbeiter)-Zellen zuordnen
        results = {d: {} for d in range(1, 32)}

        for t in tokens:
            word = t['text'].strip()
            matched_shift = None
            for s in VALID_SHIFTS:
                if word.lower() == s.lower():
                    matched_shift = s
                    break

            if not matched_shift:
                continue

            # Nächsten Tag anhand der Y-Koordinate ermitteln
            closest_day = None
            min_y_dist = 999999
            for d_num, d_y in day_rows.items():
                dist = abs(t['y'] - d_y)
                if dist < min_y_dist and dist < 45:
                    min_y_dist = dist
                    closest_day = d_num

            if not closest_day:
                continue

            # Nächsten Mitarbeiter anhand der X-Koordinate ermitteln
            closest_emp = None
            min_x_dist = 999999
            for col in col_positions:
                dist = abs(t['x'] - col['x'])
                if dist < min_x_dist:
                    min_x_dist = dist
                    closest_emp = col['name']

            if closest_day and closest_emp:
                results[closest_day][closest_emp] = matched_shift

        # 7. Aggregation: Gleiche Schichten am selben Tag zu einer Besatzung zusammenfassen
        final_shifts = []
        for day in sorted(results.keys()):
            day_entries = results[day]
            if not day_entries:
                continue

            grouped = {}
            for emp, sh in day_entries.items():
                if sh not in grouped:
                    grouped[sh] = []
                grouped[sh].append(emp)

            shift_list = [{"shift": sh_code, "employees": emps} for sh_code, emps in grouped.items()]
            final_shifts.append({
                "day": day,
                "shifts": shift_list
            })

        return jsonify({
            "success": True,
            "detected_employees": [c['name'] for c in col_positions],
            "shifts": final_shifts,
            "detected_days": len(final_shifts)
        })

    except Exception as e:
        return jsonify({"error": f"Verarbeitungsfehler: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
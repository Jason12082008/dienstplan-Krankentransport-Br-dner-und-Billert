import os
import io
import re
import base64
from flask import Flask, request, jsonify
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
from pytesseract import Output

pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

app = Flask(__name__)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    return response

# Alle 16 Mitarbeiter laut Dienstplan-Kopfzeile
EMPLOYEES = [
    "Setzer", "Rathmann", "Wittke", "Gart", "Wischhusen", "Seidscheck",
    "Thüm", "Gradim", "Stang", "Boelkes", "Schwirz", "Martin",
    "Martens", "Garcia", "N.Behrendt", "Soller"
]

# Bekannte Schichtkürzel
VALID_SHIFTS = {
    "K1", "K1x", "K2", "K4", "K5", "K6", "K7", "K8", "K9", "K10", "K11", "K12", "K15", "K18",
    "A1F", "A1S", "A1N", "A2F", "A2S", "LK", "BTW", "Büro", "Ruf", "U", "UW", "FnN", "Frei"
}

@app.route('/')
def home():
    return "Dienstplan-OCR-Backend läuft!"

@app.route('/test-ocr', methods=['GET'])
def test_ocr():
    try:
        return jsonify({"success": True, "tesseract_version": str(pytesseract.get_tesseract_version())})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/scan', methods=['POST'])
def scan_roster():
    try:
        data = request.get_json()
        if not data or 'image' not in data:
            return jsonify({"error": "Keine Bilddaten übermittelt."}), 400

        image_base64 = data['image']
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]

        raw_img = Image.open(io.BytesIO(base64.b64decode(image_base64)))

        # 1. Bild für maximale Lesbarkeit & Speed anpassen
        raw_img.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
        gray = ImageOps.grayscale(raw_img)
        enhancer = ImageEnhance.Contrast(gray)
        processed_img = enhancer.enhance(1.6)

        # 2. Tesseract OCR mit Zeileninformationen auslesen
        custom_config = r'--oem 1 --psm 6 -l deu'
        ocr_data = pytesseract.image_to_data(processed_img, config=custom_config, output_type=Output.DICT)

        # 3. Alle Wörter zeilenweise gruppieren
        lines_dict = {}
        all_shift_tokens = []
        n_boxes = len(ocr_data['text'])

        for i in range(n_boxes):
            text = ocr_data['text'][i].strip()
            if not text:
                continue

            # Prüfen ob Wort ein Schichtkürzel ist
            matched_shift = None
            for s in VALID_SHIFTS:
                if text.lower() == s.lower():
                    matched_shift = s
                    break

            token = {
                'text': text,
                'shift': matched_shift,
                'x': ocr_data['left'][i],
                'y': ocr_data['top'][i],
                'w': ocr_data['width'][i],
            }

            line_key = (ocr_data['block_num'][i], ocr_data['par_num'][i], ocr_data['line_num'][i])
            if line_key not in lines_dict:
                lines_dict[line_key] = []
            lines_dict[line_key].append(token)

            if matched_shift:
                all_shift_tokens.append(token)

        # 4. Spaltenpositionen für die 16 Mitarbeiter berechnen
        if all_shift_tokens:
            min_x = min(t['x'] for t in all_shift_tokens)
            max_x = max(t['x'] for t in all_shift_tokens)
        else:
            min_x = int(processed_img.width * 0.15)
            max_x = int(processed_img.width * 0.75)

        # 16 gleichmäßige Spalten für die Mitarbeiter
        step = (max_x - min_x) / max(1, len(EMPLOYEES) - 1)
        col_positions = [{ 'name': EMPLOYEES[idx], 'x': min_x + (idx * step) } for idx in range(len(EMPLOYEES))]

        # 5. Jede Zeile analysieren (Tag ermitteln und Schichten zuordnen)
        results = {d: {} for d in range(1, 32)}
        detected_day_counter = 0

        # Zeilen nach Y-Position (von oben nach unten) sortieren
        sorted_lines = sorted(lines_dict.values(), key=lambda line: line[0]['y'])

        for line in sorted_lines:
            line = sorted(line, key=lambda t: t['x'])
            shifts_in_line = [t for t in line if t['shift']]

            if not shifts_in_line:
                continue

            # Tag aus den ersten Tokens der Zeile lesen (z. B. 01.11.26, 02.11, 03)
            day_num = None
            for t in line[:3]:
                m = re.search(r'\b(0?[1-9]|[12]\d|3[01])\b', t['text'])
                if m:
                    val = int(m.group(1))
                    if 1 <= val <= 31:
                        day_num = val
                        break

            # Fallback: Falls Datum unleserlich war, fortlaufend nummerieren
            if not day_num:
                detected_day_counter += 1
                day_num = detected_day_counter
            else:
                detected_day_counter = day_num

            # Schichten dieser Zeile den 16 Mitarbeitern zuordnen
            for st in shifts_in_line:
                closest_emp = min(col_positions, key=lambda col: abs(st['x'] - col['x']))['name']
                results[day_num][closest_emp] = st['shift']

        # 6. Besatzungen gruppieren und JSON für die App erstellen
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

        print(f"Scan erfolgreich: {len(final_shifts)} Tage erfasst.")

        return jsonify({
            "success": True,
            "shifts": final_shifts,
            "detected_days": len(final_shifts)
        })

    except Exception as e:
        print("Fehler im Scan:", str(e))
        return jsonify({"error": f"Verarbeitungsfehler: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
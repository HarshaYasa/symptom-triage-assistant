import os
import json
import sqlite3
import io
from datetime import datetime
from datetime import datetime as dt
from flask import Flask, render_template, request, session, send_file
from google import genai
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-this")

EMERGENCY_KEYWORDS = [
    "chest pain",
    "can't breathe",
    "cannot breathe",
    "difficulty breathing",
    "severe bleeding",
    "unconscious",
    "not breathing",
    "suicidal",
    "want to die",
    "severe allergic reaction",
    "stroke",
    "seizure",
    "heart attack"
]

def check_emergency(symptom_text):
    text_lower = symptom_text.lower()
    for keyword in EMERGENCY_KEYWORDS:
        if keyword in text_lower:
            return True
    return False

def load_specialist_data():
    with open("data/specialist_mapping.json", "r") as f:
        return json.load(f)

def match_specialist_dataset(symptoms):
    data = load_specialist_data()
    symptoms_lower = symptoms.lower()
    matches = {}
    for keyword, specialist in data.items():
        if keyword in symptoms_lower:
            matches[keyword] = specialist
    return matches

def get_triage_recommendation(symptoms, duration="", severity=""):
    dataset_matches = match_specialist_dataset(symptoms)

    if dataset_matches:
        context = "Reference data (use this to inform your answer if relevant): " + json.dumps(dataset_matches)
    else:
        context = "No reference data matched these symptoms."

    prompt = f"""You are a medical triage assistant, not a doctor. You do not diagnose conditions.

{context}

Given the symptoms below, respond ONLY with valid JSON in this exact format, no other text:
{{
  "likely_body_system": "string",
  "urgency_level": "routine" or "see-soon",
  "recommended_specialist": "string",
  "reasoning": "one sentence explanation"
}}

Symptoms: {symptoms}
Duration: {duration if duration else "not specified"}
Severity (1-10 scale): {severity if severity else "not specified"}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        text = response.text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        return result
    except Exception as e:
        print("GEMINI ERROR:", e)
        return {
            "likely_body_system": "unknown",
            "urgency_level": "unknown",
            "recommended_specialist": "general physician",
            "reasoning": "Unable to process this request right now. Please consult a doctor for proper evaluation."
        }

def init_db():
    conn = sqlite3.connect("logs.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symptoms TEXT,
            urgency TEXT,
            specialist TEXT
        )
    """)
    conn.commit()
    conn.close()

def log_query(symptoms, urgency, specialist):
    conn = sqlite3.connect("logs.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO logs (timestamp, symptoms, urgency, specialist) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), symptoms, urgency, specialist)
    )
    conn.commit()
    conn.close()

init_db()

@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    if request.method == "POST":
        symptoms = request.form.get("symptoms", "").strip()
        duration = request.form.get("duration", "").strip()
        severity = request.form.get("severity", "").strip()

        if not symptoms:
            result = {
                "input_received": "",
                "urgency": "unknown",
                "message": "Please enter some symptoms to get a recommendation."
            }
        elif check_emergency(symptoms):
            result = {
                "input_received": symptoms,
                "urgency": "emergency",
                "message": "This may be a medical emergency. Please call your local emergency number or go to the nearest emergency room immediately."
            }
            log_query(symptoms, "emergency", "N/A")
        else:
            ai_result = get_triage_recommendation(symptoms, duration, severity)
            result = {
                "input_received": symptoms,
                "urgency": ai_result.get("urgency_level", "unknown"),
                "body_system": ai_result.get("likely_body_system", "unknown"),
                "specialist": ai_result.get("recommended_specialist", "general physician"),
                "message": ai_result.get("reasoning", "Please consult a doctor for evaluation.")
            }
            log_query(symptoms, result["urgency"], result["specialist"])

        if result:
            session["last_result"] = result

    return render_template("index.html", result=result)

@app.route("/history")
def history():
    conn = sqlite3.connect("logs.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()
    return render_template("history.html", logs=rows)

@app.route("/download-pdf")
def download_pdf():
    result = session.get("last_result")
    if not result:
        return "No result available to download. Please submit a symptom query first.", 400

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#14293B'))
    label_style = ParagraphStyle('LabelStyle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#5B7285'), spaceBefore=10)
    value_style = ParagraphStyle('ValueStyle', parent=styles['Normal'], fontSize=12, textColor=colors.HexColor('#14293B'), spaceAfter=4)
    disclaimer_style = ParagraphStyle('DisclaimerStyle', parent=styles['Normal'], fontSize=8, textColor=colors.grey, spaceBefore=20)

    elements = []
    elements.append(Paragraph("Symptom Triage Summary", title_style))
    elements.append(Paragraph(dt.now().strftime("%B %d, %Y at %I:%M %p"), disclaimer_style))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("SYMPTOMS ENTERED", label_style))
    elements.append(Paragraph(result.get("input_received", ""), value_style))

    elements.append(Paragraph("URGENCY LEVEL", label_style))
    elements.append(Paragraph(result.get("urgency", "unknown").upper(), value_style))

    if result.get("body_system"):
        elements.append(Paragraph("LIKELY BODY SYSTEM", label_style))
        elements.append(Paragraph(result.get("body_system", ""), value_style))

    if result.get("specialist"):
        elements.append(Paragraph("RECOMMENDED SPECIALIST", label_style))
        elements.append(Paragraph(result.get("specialist", ""), value_style))

    elements.append(Paragraph("DETAILS", label_style))
    elements.append(Paragraph(result.get("message", ""), value_style))

    elements.append(Paragraph(
        "This is not a medical diagnosis. Please consult a qualified healthcare professional for any health concerns.",
        disclaimer_style
    ))

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="symptom_triage_summary.pdf",
        mimetype="application/pdf"
    )

if __name__ == "__main__":
    app.run(debug=True)
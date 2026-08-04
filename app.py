import os
import json
import sqlite3
import io
import time
from collections import defaultdict
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

request_log = defaultdict(list)
RATE_LIMIT = 10
RATE_WINDOW = 60

def is_rate_limited(ip):
    now = time.time()
    request_log[ip] = [t for t in request_log[ip] if now - t < RATE_WINDOW]
    if len(request_log[ip]) >= RATE_LIMIT:
        return True
    request_log[ip].append(now)
    return False

MAX_SYMPTOM_LENGTH = 1000

EMERGENCY_KEYWORDS = [
    "chest pain", "can't breathe", "cannot breathe", "difficulty breathing",
    "severe bleeding", "unconscious", "not breathing", "suicidal",
    "want to die", "severe allergic reaction", "stroke", "seizure", "heart attack"
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

def get_triage_recommendation(symptoms, duration="", severity="", clarification_answer=""):
    dataset_matches = match_specialist_dataset(symptoms)

    if dataset_matches:
        context = "Reference data (use this to inform your answer if relevant): " + json.dumps(dataset_matches)
    else:
        context = "No reference data matched these symptoms."

    clarification_context = ""
    if clarification_answer:
        clarification_context = f"\nAdditional clarification from user: {clarification_answer}"

    prompt = f"""You are a medical triage assistant, not a doctor. You do not diagnose conditions.

{context}

Given the symptoms below, decide if you have ENOUGH information to give a confident triage recommendation.

If the input is too vague to assess (e.g. very short, no detail on what/where/how long), respond ONLY with this JSON:
{{
  "needs_clarification": true,
  "clarifying_question": "one specific question to ask the user"
}}

If you have enough information, respond ONLY with this JSON:
{{
  "needs_clarification": false,
  "likely_body_system": "string",
  "urgency_level": "routine" or "see-soon",
  "recommended_specialist": "string",
  "reasoning": "one sentence explanation"
}}

Symptoms: {symptoms}
Duration: {duration if duration else "not specified"}
Severity (1-10 scale): {severity if severity else "not specified"}{clarification_context}"""

    max_retries = 2
    for attempt in range(max_retries + 1):
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
            print(f"GEMINI ERROR (attempt {attempt + 1}):", e)
            if attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
            else:
                return {
                    "needs_clarification": False,
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
    if request.method == "GET" and request.args.get("reset"):
        session.pop("conversation", None)
        session.pop("pending_question", None)
        session.pop("pending_symptoms", None)
        session.pop("pending_duration", None)
        session.pop("pending_severity", None)

    conversation = session.get("conversation", [])
    pending_question = session.get("pending_question")

    if request.method == "POST":
        if is_rate_limited(request.remote_addr):
            return "Too many requests. Please wait a moment and try again.", 429

        if request.form.get("clarification_answer") is not None and pending_question:
            symptoms = session.get("pending_symptoms", "")
            duration = session.get("pending_duration", "")
            severity = session.get("pending_severity", "")
            clarification_answer = request.form.get("clarification_answer", "").strip()[:MAX_SYMPTOM_LENGTH]

            conversation.append({"role": "user", "text": clarification_answer})

            ai_result = get_triage_recommendation(symptoms, duration, severity, clarification_answer)

            if ai_result.get("needs_clarification"):
                new_question = ai_result.get("clarifying_question", "Can you provide more detail?")
                conversation.append({"role": "assistant", "text": new_question, "type": "question"})
                session["pending_question"] = new_question
                pending_question = new_question
            else:
                result = {
                    "input_received": symptoms,
                    "urgency": ai_result.get("urgency_level", "unknown"),
                    "body_system": ai_result.get("likely_body_system", "unknown"),
                    "specialist": ai_result.get("recommended_specialist", "general physician"),
                    "message": ai_result.get("reasoning", "Please consult a doctor for evaluation.")
                }
                log_query(symptoms, result["urgency"], result["specialist"])
                conversation.append({"role": "assistant", "type": "result", "result": result})
                session["last_result"] = result
                session.pop("pending_question", None)
                session.pop("pending_symptoms", None)
                session.pop("pending_duration", None)
                session.pop("pending_severity", None)
                pending_question = None

        else:
            symptoms = request.form.get("symptoms", "").strip()[:MAX_SYMPTOM_LENGTH]
            duration = request.form.get("duration", "").strip()
            severity = request.form.get("severity", "").strip()

            if symptoms:
                user_msg = symptoms
                if duration:
                    user_msg += f" (duration: {duration})"
                if severity:
                    user_msg += f" (severity: {severity}/10)"
                conversation.append({"role": "user", "text": user_msg})

                if check_emergency(symptoms):
                    result = {
                        "input_received": symptoms,
                        "urgency": "emergency",
                        "message": "This may be a medical emergency. Please call your local emergency number or go to the nearest emergency room immediately."
                    }
                    log_query(symptoms, "emergency", "N/A")
                    conversation.append({"role": "assistant", "type": "result", "result": result})
                else:
                    ai_result = get_triage_recommendation(symptoms, duration, severity)

                    if ai_result.get("needs_clarification"):
                        new_question = ai_result.get("clarifying_question", "Can you provide more detail?")
                        conversation.append({"role": "assistant", "text": new_question, "type": "question"})
                        session["pending_question"] = new_question
                        session["pending_symptoms"] = symptoms
                        session["pending_duration"] = duration
                        session["pending_severity"] = severity
                        pending_question = new_question
                    else:
                        result = {
                            "input_received": symptoms,
                            "urgency": ai_result.get("urgency_level", "unknown"),
                            "body_system": ai_result.get("likely_body_system", "unknown"),
                            "specialist": ai_result.get("recommended_specialist", "general physician"),
                            "message": ai_result.get("reasoning", "Please consult a doctor for evaluation.")
                        }
                        log_query(symptoms, result["urgency"], result["specialist"])
                        conversation.append({"role": "assistant", "type": "result", "result": result})
                        session["last_result"] = result

        session["conversation"] = conversation

    return render_template("index.html", conversation=conversation, pending_question=pending_question)

@app.route("/history")
def history():
    conn = sqlite3.connect("logs.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 50")
    rows = c.fetchall()
    conn.close()
    return render_template("history.html", logs=rows)

@app.route("/stats")
def stats():
    conn = sqlite3.connect("logs.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT COUNT(*) as total FROM logs")
    total_queries = c.fetchone()["total"]

    c.execute("SELECT urgency, COUNT(*) as count FROM logs GROUP BY urgency ORDER BY count DESC")
    urgency_breakdown = c.fetchall()

    c.execute("SELECT specialist, COUNT(*) as count FROM logs GROUP BY specialist ORDER BY count DESC LIMIT 10")
    top_specialists = c.fetchall()

    c.execute("SELECT symptoms, COUNT(*) as count FROM logs GROUP BY symptoms ORDER BY count DESC LIMIT 10")
    top_symptoms = c.fetchall()

    conn.close()

    return render_template(
        "stats.html",
        total_queries=total_queries,
        urgency_breakdown=urgency_breakdown,
        top_specialists=top_specialists,
        top_symptoms=top_symptoms
    )

@app.route("/export-csv")
def export_csv():
    conn = sqlite3.connect("logs.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()

    output = io.StringIO()
    output.write("Timestamp,Symptoms,Urgency,Specialist\n")
    for row in rows:
        symptoms_escaped = row["symptoms"].replace('"', '""')
        output.write(f'"{row["timestamp"]}","{symptoms_escaped}","{row["urgency"]}","{row["specialist"]}"\n')

    csv_data = output.getvalue()
    output.close()

    return send_file(
        io.BytesIO(csv_data.encode("utf-8")),
        as_attachment=True,
        download_name="symptom_triage_history.csv",
        mimetype="text/csv"
    )

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
# Symptom Triage Assistant

An AI-powered web app that takes a plain-language description of symptoms and returns a triage recommendation — likely body system, urgency level, and which type of specialist to see. Built with safety-first design principles: emergency detection runs on hardcoded rules (not AI), and AI responses are grounded in a curated reference dataset to reduce hallucination risk.

> **Disclaimer:** This is a portfolio/learning project, not a medical device. It does not diagnose conditions and should never replace professional medical advice.

## Features

- **Text or voice input** — describe symptoms by typing or speaking (browser Speech Recognition API)
- **Clickable body diagram** — tap a body region to quickly add it to your symptom description
- **Color-coded urgency results** — emergency / see-soon / routine, visually distinct at a glance
- **Dark mode** — toggle and persisted across visits
- **Query history** — view the last 50 triage queries logged, with timestamps
- **PDF export** — download a formatted summary of any triage result

## How it works

1. **Emergency filter (rule-based, zero AI):** Every input is first checked against a hardcoded list of emergency keywords (chest pain, difficulty breathing, stroke symptoms, etc.). If matched, the app immediately returns an emergency warning — no API call, no latency, no hallucination risk on the most safety-critical path.
2. **Dataset grounding (lightweight RAG):** For non-emergency input, the app checks a curated JSON dataset mapping common symptoms to specialists. Any matches are passed to the AI model as reference context, anchoring its answer instead of letting it improvise freely.
3. **AI triage reasoning:** The symptom text (plus any grounding context) is sent to the Gemini API with a prompt that forces structured JSON output — likely body system, urgency level, recommended specialist, and a one-line reasoning.
4. **Logging / audit trail:** Every query and its resulting recommendation is logged to a local SQLite database with a timestamp, creating a reviewable record of every triage decision the app has made. This is also viewable in-app via the history page.

## Tech stack

- **Backend:** Flask (Python)
- **AI:** Google Gemini API (`google-genai` SDK)
- **Data:** JSON-based symptom-specialist reference dataset
- **Logging:** SQLite
- **PDF generation:** ReportLab
- **Frontend:** Vanilla HTML/CSS/JS — CSS variables for theming, browser Speech Recognition API for voice input, inline SVG for the body diagram
- **Deployment:** Render (free tier)

## Project structure

```
symptom-triage-assistant/
├── app.py                      # Flask app, routes, AI + safety logic, PDF generation
├── requirements.txt
├── Procfile                    # Render deployment config
├── .env.example                # Template for API key (never commit the real .env)
├── data/
│   └── specialist_mapping.json # Curated symptom → specialist reference data
├── templates/
│   ├── index.html              # Main triage form (dark mode, voice input, body diagram)
│   └── history.html            # Query history view
└── logs.db                     # SQLite audit log (generated at runtime)
```

## Setup

1. Clone the repo and install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com) and add it to a `.env` file:
   ```
   GEMINI_API_KEY=your_key_here
   ```
3. Run the app:
   ```
   python app.py
   ```
4. Open `http://127.0.0.1:5000` in your browser.

## Known limitations

- **Keyword-based emergency detection** is intentionally simple and explainable, but it's a blunt instrument — it can miss paraphrased emergency descriptions (e.g. "my chest feels really tight and heavy" won't match "chest pain"). A production version would likely use embedding-based similarity matching as well.
- **Dataset grounding uses exact keyword overlap**, not semantic matching, so typos or unusual phrasing may not trigger a dataset match (the AI can still reason correctly on its own in these cases, as tested).
- **Gemini API free tier caps at a limited number of requests/day**, which is a real constraint for this deployment as a free-tier demo, not a flaw in the application logic itself.
- **Voice input relies on the browser's built-in Speech Recognition API**, which is well-supported in Chrome/Edge/Brave but not in Firefox — the mic button is hidden automatically in unsupported browsers.
- **Render's free tier spins down after inactivity**, so the first request after idle time may take up to a minute.

## Why this project

Built to explore safe, explainable AI system design in a healthcare-adjacent context — specifically, how to combine hardcoded safety rules, retrieval-grounded prompting, and structured output validation to reduce the risks of an LLM-based tool giving unreliable answers in a sensitive domain. The logging/audit-trail layer was added deliberately to reflect AI governance practices (traceability, reviewability) relevant to responsible AI deployment. The additional UI features (voice input, body diagram, dark mode, history, PDF export) were built afterward to practice turning a functional prototype into a more complete, usable product.

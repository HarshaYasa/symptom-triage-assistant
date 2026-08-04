# Symptom Triage Assistant

An AI-powered web app that takes a plain-language description of symptoms and returns a triage recommendation — likely body system, urgency level, and which type of specialist to see. Built with safety-first design principles: emergency detection runs on hardcoded rules (not AI), AI responses are grounded in a curated reference dataset, and the system asks clarifying questions rather than guessing from vague input.

> **Disclaimer:** This is a portfolio/learning project, not a medical device. It does not diagnose conditions and should never replace professional medical advice.

## Features

**Core interaction**
- Text or voice input (browser Speech Recognition API)
- Optional duration and severity (1-10) inputs for richer context
- Chat-style conversation — if input is too vague, the AI asks one clarifying question before giving a final recommendation
- Color-coded urgency results (emergency / see-soon / routine)

**Output & sharing**
- Downloadable PDF summary of any result
- Print-friendly view (browser print, clean black-and-white layout)
- Dark mode with persistence

**Data & insight**
- Query history view (last 50 queries)
- Analytics dashboard — total queries, urgency breakdown, top specialists, most common symptoms
- CSV export of full query history

**Reliability & safety**
- Rule-based emergency keyword detection (bypasses AI entirely for speed and reliability)
- RAG-style grounding against a curated symptom-specialist dataset
- Input length limits
- Basic per-IP rate limiting
- Retry logic with exponential backoff on AI call failures
- Full audit-trail logging to SQLite

## How it works

1. **Emergency filter (rule-based, zero AI):** Every input is first checked against a hardcoded list of emergency keywords (chest pain, difficulty breathing, stroke symptoms, etc.). If matched, the app immediately returns an emergency warning — no API call, no latency, no hallucination risk on the most safety-critical path.
2. **Dataset grounding (lightweight RAG):** For non-emergency input, the app checks a curated JSON dataset mapping common symptoms to specialists. Any matches are passed to the AI model as reference context, anchoring its answer instead of letting it improvise freely.
3. **Clarification loop:** The AI is prompted to judge whether it has enough information. If not, it asks one specific clarifying question, which is shown as a chat message; the user's answer is combined with the original input for a final assessment.
4. **AI triage reasoning:** The symptom text, duration, severity, and any grounding context are sent to the Gemini API with a prompt that forces structured JSON output — likely body system, urgency level, recommended specialist, and a one-line reasoning.
5. **Reliability layer:** API calls retry up to twice with backoff on failure; if all retries fail, a safe fallback message is shown instead of an error or crash.
6. **Logging / audit trail:** Every query and its resulting recommendation is logged to SQLite with a timestamp — viewable via the history page, summarized on the analytics dashboard, and exportable as CSV.

## Tech stack

- **Backend:** Flask (Python)
- **AI:** Google Gemini API (`google-genai` SDK)
- **Data:** JSON-based symptom-specialist reference dataset
- **Logging:** SQLite
- **PDF generation:** ReportLab
- **Frontend:** Vanilla HTML/CSS/JS — CSS variables for theming, browser Speech Recognition API for voice input, `@media print` for the printable view
- **Deployment:** Render (free tier)

## Project structure

```
symptom-triage-assistant/
├── app.py                      # Flask app, routes, AI + safety logic, PDF/CSV generation
├── requirements.txt
├── Procfile                    # Render deployment config
├── .env.example                # Template for API key (never commit the real .env)
├── data/
│   └── specialist_mapping.json # Curated symptom → specialist reference data
├── templates/
│   ├── index.html              # Main chat-style triage interface
│   ├── history.html            # Query history view
│   └── stats.html              # Analytics dashboard
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
- **Rate limiting is in-memory and per-process** — fine for a single-instance deployment like this one, but wouldn't scale correctly across multiple server instances without a shared store like Redis.
- **Gemini API free tier caps at a limited number of requests/day**, a real constraint for this free-tier demo, not a flaw in the application logic.
- **Voice input relies on the browser's built-in Speech Recognition API**, well-supported in Chrome/Edge but not Firefox; some privacy-focused browsers (e.g. Brave) may block the underlying network request unless shields are adjusted.
- **Query history and analytics are global, not per-user** — acceptable for a portfolio demo, but would need user accounts and scoping for real multi-user use.
- **Render's free tier spins down after inactivity**, so the first request after idle time may take up to a minute.

## Why this project

Built to explore safe, explainable AI system design in a healthcare-adjacent context — specifically, how to combine hardcoded safety rules, retrieval-grounded prompting, structured output validation, and reliability engineering (retries, rate limiting, input validation) to reduce the risks of an LLM-based tool giving unreliable answers in a sensitive domain. The audit-trail and analytics layers were added deliberately to reflect AI governance practices (traceability, reviewability, observability) relevant to responsible AI deployment. The additional product features (voice input, structured duration/severity inputs, clarifying-question flow, PDF/CSV export, dark mode) were built afterward to practice turning a functional prototype into a more complete, usable product.

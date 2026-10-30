# Polypharmacy Risk Analyzer ⚕️

> **Clinical Decision-Support & Multi-Medication Risk Review Prototype**  
> *Built with FastAPI, deterministic clinical rules, SQLite (DDInter Dataset), Groq text and vision models, and ReportLab.*

---

## 📖 1. Project Overview & Pitch

Patients taking multiple concurrent medications face compounded risks from drug-drug interactions, adverse effects, and age-related physiological vulnerabilities. 

**Polypharmacy Risk Analyzer** is a clinical decision-support tool that helps physicians and clinical pharmacists rapidly screen complex multi-medication regimens. 

### Core Clinical Principle
> **The system supports medication review; it does NOT diagnose disease, prescribe medicines, or tell a patient to stop or change a medicine independently.** All flags are traceable to deterministic clinical rules and validated database citations.

---

## 🏗️ 2. System Architecture

```
User / Clinician
       │
       ▼
[ Modern Web Interface ] (HTML5 / CSS / Vanilla JS)
       │
       ├──► Patient Profile (Age, Biological Sex, Diagnosed Conditions, Frailty, Duration)
       ├──► Medicine Management (Search 160,000+ interactions, Dosing, Duration)
       └──► Medicine Photo Upload (Prescription / Box scan via Groq Vision with User Confirmation)
       │
       ▼
[ FastAPI Backend (`app.py`) ]
       │
       ▼
[ Deterministic Risk Engine (`risk_engine.py`) ] ◄──► [ SQLite Database (`database.py`) ]
       │                                                 • 160,250+ DDInter Interactions
       │                                                 • 20 Curated Medicines with Warnings
       ▼                                                 • Transparent Risk Rules
[ Prototype Risk Indicator & Findings ]
       │
       ├──► [ Interactive Visual Dashboard ] (Score Meter, SVG Interaction Network, Audit Cards)
       ├──► [ Groq LLM Explanation (`ai_explanation.py`) ] (English, Hindi, Punjabi)
       └──► [ Official Clinical PDF Generator (`report_generator.py`) ] (ReportLab Download)
```

---

## ⚙️ 3. How the Deterministic Risk Engine Works

Unlike black-box AI models that can hallucinate medical risks, this system follows a **strictly auditable, deterministic scoring engine**:

| Risk Finding | Prototype Points | Clinical Rationale / Reference |
| :--- | :---: | :--- |
| **Major Drug-Drug Interaction** | **+3** | Severe adverse physiological conflict (e.g. Warfarin + Aspirin hemorrhage hazard) |
| **Moderate Drug-Drug Interaction** | **+2** | Interactions requiring dose titration or active surveillance (e.g. ACEI + NSAID) |
| **Minor Drug-Drug Interaction** | **+1** | Minor competition or pharmacological synergy |
| **Therapeutic Class Duplication** | **+2** | Multiple agents from same class (e.g. 2 statins, 2 NSAIDs) |
| **Polypharmacy Threshold (≥ 5 Meds)** | **+1** | Regimen complexity markedly elevates non-adherence and adverse drug events |
| **Geriatric High-Risk (Age ≥ 65)** | **+1** | Diminished renal clearance and altered hepatic metabolism (Beers / STOPP Criteria) |
| **Condition-Specific Synergy (Triple Whammy)** | **+1** | ACEI/ARB + NSAID in hypertensive/renal patients (AKI risk) |

### Prototype Risk Thresholds:
- **0 – 2 Points**: `LOW RISK` (Green)
- **3 – 4 Points**: `MEDIUM RISK` (Yellow / Amber)
- **5+ Points**: `HIGH RISK` (Red)

---

## 🤖 4. Groq LLM Explainable AI & Multilingual Support

The AI layer strictly adheres to safe clinical decision support:
1. **The AI does NOT calculate or change the risk score.** It receives the detected findings and references from the deterministic engine.
2. It translates technical pharmacological alerts into compassionate, plain-language guidance.
3. It suggests specific questions for the patient to ask their doctor or pharmacist.
4. **Multilingual translation support**:
   - **English** (Standard Clinical Summary)
   - **Hindi (हिंदी)** (Devenagari script for Indian caregivers)
   - **Punjabi (ਪੰਜਾਬੀ)** (Gurmukhi script for Punjabi-speaking families)
### Multimodal Multi-Photo & Webcam Scan
- **Multi-Photo Drag & Drop / Batch File Upload**: Upload several prescription slips and medication boxes simultaneously.
- **Direct Live Webcam Multi-Snap**: Take multiple continuous photos directly from your browser webcam without typing or uploading files.
- **Direct Automatic Clinical Detail Search**: The system automatically queries the database for each detected medicine and retrieves:
  - Therapeutic Category
  - Clinical Purpose / Indications
  - Critical Warnings & Contraindications
  - Total Known Drug-Drug Interactions Count (from 160,250+ DDInter dataset)
  - 1-Click "Add All to Regimen" with zero manual typing required.

### Text-Minimal High-Impact Clinical Dashboard
- **Executive Summary Bar**: Real-time summary pills at the very top (Risk Level, Total Meds, Critical Red Flags, Moderate Flags, Polypharmacy Status) without cluttering raw text.
- **Tiered Severity Sorting**:
  - **Tier 1 (Critical Red Flags)**: Prominent action-oriented cards with punchy tags (`[🚨 CRITICAL]`, `[⚡ Bleeding Hazard]`, `[👉 Action...]`), whitespace, and `[🔍 View Rationale →]` button.
  - **Tier 2 (Moderate Risks)**: Clean, collapsible accordions.
  - **Tier 3 (Minor & Monitoring)**: Compact secondary collapsible accordions.
- **Clean Single-Line Badges**: Repetitive systemic alerts (like polypharmacy count, geriatric clearance, and duplications) are compressed into single-line colored ribbons.
- **On-Demand Clinical Rationale Modal**: Full pharmacological mechanisms, monitoring protocols, and exact validated citations open in an interactive modal, keeping the main screen scannable in under 5 seconds.

---

## 🚀 5. Quick Start & Execution

### Option A: Double-Click (Windows)
Double click `run.bat` inside `D:\AI_Polypharmacy_Analyzer`. It automatically starts the server at:
👉 **`http://127.0.0.1:8000`**

### Option B: PowerShell Command Line
```powershell
cd D:\AI_Polypharmacy_Analyzer
.\run.ps1
```

### Option C: Manual Python Launch
```powershell
cd D:\AI_Polypharmacy_Analyzer
.\venv\Scripts\activate
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

---

## 🧪 6. Demonstration Scenario (For Hackathon Judges)

1. **Open the web application** at `http://127.0.0.1:8000` and choose **Check medicines**.
2. Enter optional patient details, then choose **Continue** or **Skip**.
3. Add at least two medicines by typing a name and selecting a search result. Alternatively, open **Sample cases** and run one of the seeded synthetic examples.
4. Choose **Check safety** to view the risk result, findings, interaction map, and plain-language explanation.
5. Use the language buttons to switch the explanation to Hindi or Punjabi. You can also scan a medicine photo and review the detected names before adding them.
6. Choose **Download report** to generate and download a PDF. This is an educational screening tool; patients should discuss results with a doctor or pharmacist.

---

## 📂 7. Project Directory Layout

```
D:\AI_Polypharmacy_Analyzer\
├── app.py                   # FastAPI REST API & Web Routes
├── database.py              # SQLite DB schema, queries & indexer
├── risk_engine.py           # Transparent deterministic rule-based engine
├── ai_explanation.py        # Groq text and vision models & built-in fallback
├── report_generator.py      # ReportLab PDF report generator
├── seed_data.py             # Database initialization & interaction seeder
├── test_system.py           # Comprehensive unit & integration tests
├── run.bat                  # One-click Windows launcher
├── run.ps1                  # PowerShell launcher script
├── requirements.txt         # Project dependencies
├── .env.example             # Groq API Key template
├── .gitignore               # Excludes local secrets, generated data, and environments
├── Data.xlsx                # Optional Excel source for interaction seeding
├── data/
│   └── interactions.tsv     # Interaction dataset used to seed the local database
├── templates/
│   └── index.html           # Modern single-page clinical dashboard
├── static/
│   ├── css/style.css        # Professional medical styling
│   └── js/app.js            # Reactive UI, autocomplete, SVG network graph
├── database/                # Local generated SQLite database (not committed)
├── reports/                 # Generated PDF case reports (not committed)
└── uploads/                 # Uploaded prescription/box photos (not committed)
```

The checked-in source files and `data/interactions.tsv` are used to rebuild the database locally. The virtual environment, `.env`, generated database, reports, and uploads stay on your machine and are excluded from Git.

---

## ⚖️ 8. Safety & Regulatory Scope

This software is an educational prototype developed for academic and competition demonstration. It should not be used as a standalone diagnostic medical device. All clinical recommendations must be validated by licensed medical practitioners.

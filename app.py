import datetime
import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import ai_explanation
import database
import report_generator
import risk_engine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.init_db()
    database.seed_default_rules_and_medicines()
    database.seed_synthetic_patients()
    yield


app = FastAPI(
    title="Polypharmacy Risk Analyzer",
    description="Clinical Decision-Support Prototype for Multi-Medication Safety Review",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount(
    "/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static"
)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# Pydantic schemas 
class PatientCreate(BaseModel):
    case_id: Optional[str] = None
    age: int
    biological_sex: str
    conditions: str
    condition_duration: Optional[str] = ""
    frailty_allergies: Optional[str] = ""


class MedicationAdd(BaseModel):
    medicine_name: str
    dose: Optional[str] = ""
    frequency: Optional[str] = ""
    duration: Optional[str] = ""


class ExplainRequest(BaseModel):
    patient_id: int
    language: Optional[str] = "en"
    custom_groq_key: Optional[str] = None


class GroqKeyUpdate(BaseModel):
    api_key: str


# ----------------- WEB PAGES -----------------
@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


# ----------------- PATIENT ENDPOINTS -----------------
@app.get("/api/patients")
async def list_patients():
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patients ORDER BY patient_id DESC")
    patients = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"patients": patients}


@app.post("/api/patient")
async def create_patient(data: PatientCreate):
    case_id = (
        data.case_id
        or f"CASE-{datetime.datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
    )
    conn = database.get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
        INSERT INTO patients (case_id, age, biological_sex, conditions, condition_duration, frailty_allergies)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                case_id,
                data.age,
                data.biological_sex,
                data.conditions,
                data.condition_duration,
                data.frailty_allergies,
            ),
        )
        conn.commit()
        patient_id = cursor.lastrowid
        conn.close()
        return {"status": "success", "patient_id": patient_id, "case_id": case_id}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/patient/{patient_id}")
async def get_patient_profile(patient_id: int):
    patient = database.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient case not found")
    medications = database.get_patient_medications(patient_id)
    return {"patient": patient, "medications": medications}


# ----------------- MEDICATION MANAGEMENT -----------------
@app.get("/api/medicines/search")
async def search_medicines(q: str = ""):
    if not q or len(q.strip()) < 1:
        return {"results": database.get_all_medicines()[:30]}
    results = database.search_medicines(q.strip(), limit=20)
    return {"results": results}


@app.post("/api/patient/{patient_id}/medications")
async def add_medication(patient_id: int, med: MedicationAdd):
    patient = database.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient case not found")

    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT medicine_id, category FROM medicines WHERE name = ? COLLATE NOCASE",
        (med.medicine_name.strip(),),
    )
    row = cursor.fetchone()
    med_id = row[0] if row else None

    cursor.execute(
        """
    INSERT INTO patient_medications (patient_id, medicine_id, medicine_name, dose, frequency, duration)
    VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            patient_id,
            med_id,
            med.medicine_name.strip(),
            med.dose,
            med.frequency,
            med.duration,
        ),
    )
    conn.commit()
    entry_id = cursor.lastrowid
    conn.close()

    updated_meds = database.get_patient_medications(patient_id)
    return {"status": "success", "entry_id": entry_id, "medications": updated_meds}


@app.delete("/api/patient/{patient_id}/medications/{entry_id}")
async def delete_medication(patient_id: int, entry_id: int):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM patient_medications WHERE entry_id = ? AND patient_id = ?",
        (entry_id, patient_id),
    )
    conn.commit()
    conn.close()
    updated_meds = database.get_patient_medications(patient_id)
    return {"status": "success", "medications": updated_meds}


# ----------------- RISK ANALYSIS ENGINE -----------------
@app.post("/api/analyze/{patient_id}")
async def run_analysis(patient_id: int):
    patient = database.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    medications = database.get_patient_medications(patient_id)
    if not medications:
        return {
            "status": "warning",
            "message": "Please add at least one medication to analyze risk.",
            "risk_summary": {
                "risk_score": 0,
                "risk_level": "LOW",
                "total_medicines": 0,
                "total_issues": 0,
                "findings": [],
            },
            "network_graph": {"nodes": [], "edges": []},
        }

    # Deterministic evaluation
    risk_summary = risk_engine.analyze_patient_risk(patient, medications)

    # Build network graph representation for interactive medicine-to-medicine visual
    nodes = []
    edges = []
    node_set = set()
    for m in medications:
        name = m["medicine_name"]
        if name not in node_set:
            node_set.add(name)
            nodes.append(
                {
                    "id": name,
                    "label": name,
                    "dose": m.get("dose", ""),
                    "category": m.get("category", "Medicine"),
                }
            )

    for f in risk_summary.get("findings", []):
        if (
            f.get("type") == "interaction"
            and f.get("medicine_1")
            and f.get("medicine_2")
        ):
            edges.append(
                {
                    "source": f.get("medicine_1"),
                    "target": f.get("medicine_2"),
                    "severity": f.get("severity"),
                    "label": f.get("severity"),
                }
            )

    return {
        "status": "success",
        "patient": patient,
        "medications": medications,
        "risk_summary": risk_summary,
        "network_graph": {"nodes": nodes, "edges": edges},
    }


# ----------------- GROQ AI EXPLANATION -----------------
@app.post("/api/explain")
async def explain_risk(req: ExplainRequest):
    patient = database.get_patient(req.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    medications = database.get_patient_medications(req.patient_id)
    risk_summary = risk_engine.analyze_patient_risk(patient, medications)

    explanation = ai_explanation.generate_plain_language_explanation(
        patient=patient,
        medications=medications,
        risk_summary=risk_summary,
        language=req.language or "en",
        api_key=req.custom_groq_key,
    )

    return {"status": "success", "explanation": explanation}


# ----------------- MULTIMODAL MEDICINE PHOTO UPLOAD (MULTI-IMAGE & AUTO-DETAIL SEARCH) -----------------
@app.post("/api/upload-photo")
async def upload_medicine_photo(
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None),
    custom_groq_key: Optional[str] = Form(None),
):
    """
    Accepts single or multiple medicine images/prescriptions.
    Extracts all candidate medicines and automatically queries the database
    to retrieve full clinical details (Category, Purpose, Side Effects, Warnings, Interactions Count).
    """
    uploaded_files = []
    if files:
        uploaded_files.extend(files)
    if file and file not in uploaded_files:
        uploaded_files.append(file)

    if not uploaded_files:
        raise HTTPException(status_code=400, detail="No image files provided.")

    all_candidates = []
    uploaded_urls = []
    conn = database.get_db()
    cursor = conn.cursor()

    # Clinical reference fallback dictionary for common medicines
    clinical_kb = {
        "metformin": {
            "generic_name": "Metformin HCl",
            "category": "Antidiabetic (Biguanide)",
            "purpose": "Type 2 Diabetes glycemic management",
            "common_side_effects": "GI upset, nausea, diarrhea",
            "warnings": "Risk of lactic acidosis; monitor eGFR",
            "default_dose": "500 mg",
            "default_freq": "Twice daily with meals",
        },
        "amlodipine": {
            "generic_name": "Amlodipine Besylate",
            "category": "Calcium-channel blocker",
            "purpose": "Hypertension & Angina management",
            "common_side_effects": "Peripheral ankle edema, flushing, dizziness",
            "warnings": "Caution in severe hepatic impairment",
            "default_dose": "5 mg",
            "default_freq": "Once daily",
        },
        "lisinopril": {
            "generic_name": "Lisinopril",
            "category": "ACE inhibitor",
            "purpose": "Hypertension & Congestive Heart Failure",
            "common_side_effects": "Dry cough, hyperkalemia, headache",
            "warnings": "Contraindicated in pregnancy; monitor serum potassium",
            "default_dose": "10 mg",
            "default_freq": "Once daily",
        },
        "warfarin": {
            "generic_name": "Warfarin Sodium",
            "category": "Anticoagulant (Vitamin K antagonist)",
            "purpose": "Stroke prevention in AFib & DVT/PE treatment",
            "common_side_effects": "Hemorrhagic bleeding, unusual bruising",
            "warnings": "Narrow therapeutic index; requires routine INR testing",
            "default_dose": "3 mg",
            "default_freq": "Once daily in evening",
        },
        "aspirin": {
            "generic_name": "Acetylsalicylic acid",
            "category": "Antiplatelet / Salicylate",
            "purpose": "Cardiovascular secondary prevention",
            "common_side_effects": "Gastric irritation, heartburn, bleeding risk",
            "warnings": "Risk of GI ulceration; heightened bleeding with anticoagulants",
            "default_dose": "75 mg",
            "default_freq": "Once daily after meals",
        },
        "ibuprofen": {
            "generic_name": "Ibuprofen",
            "category": "NSAID",
            "purpose": "Pain relief, anti-inflammatory & fever reduction",
            "common_side_effects": "Dyspepsia, fluid retention, nausea",
            "warnings": "Blunts antihypertensives; risk of acute kidney injury",
            "default_dose": "400 mg",
            "default_freq": "Three times daily as needed",
        },
        "paracetamol": {
            "generic_name": "Acetaminophen",
            "category": "Analgesic / Antipyretic",
            "purpose": "Mild-to-moderate pain and pyrexia",
            "common_side_effects": "Rare; mild nausea or rash",
            "warnings": "Hepatotoxicity risk on overdose; max 4000mg/day",
            "default_dose": "500 mg",
            "default_freq": "Every 6 hours as needed",
        },
        "atorvastatin": {
            "generic_name": "Atorvastatin Calcium",
            "category": "Statin (HMG-CoA Reductase Inhibitor)",
            "purpose": "Dyslipidemia & Atherosclerotic cardiovascular prevention",
            "common_side_effects": "Myalgia, arthralgia, elevated transaminases",
            "warnings": "Avoid potent CYP3A4 inhibitors; report severe muscle pain",
            "default_dose": "20 mg",
            "default_freq": "Once daily at night",
        },
        "omeprazole": {
            "generic_name": "Omeprazole",
            "category": "Proton-pump inhibitor (PPI)",
            "purpose": "Gastroesophageal reflux (GERD) & Peptic ulcers",
            "common_side_effects": "Headache, abdominal pain, diarrhea",
            "warnings": "Inhibits CYP2C19 (interacts with clopidogrel); hypomagnesemia on long use",
            "default_dose": "20 mg",
            "default_freq": "Once daily before breakfast",
        },
        "losartan": {
            "generic_name": "Losartan Potassium",
            "category": "ARB (Angiotensin II Receptor Blocker)",
            "purpose": "Hypertension & Diabetic nephropathy protection",
            "common_side_effects": "Dizziness, hyperkalemia, fatigue",
            "warnings": "Do not combine with ACE inhibitors; monitor renal function",
            "default_dose": "50 mg",
            "default_freq": "Once daily",
        },
        "furosemide": {
            "generic_name": "Furosemide",
            "category": "Loop Diuretic",
            "purpose": "Edema in heart failure, cirrhosis, and renal disease",
            "common_side_effects": "Hypokalemia, dehydration, orthostatic dizziness",
            "warnings": "Monitor serum potassium and renal markers regularly",
            "default_dose": "40 mg",
            "default_freq": "Once daily in morning",
        },
        "pantoprazole": {
            "generic_name": "Pantoprazole Sodium",
            "category": "Proton-pump inhibitor (PPI)",
            "purpose": "GERD, erosive esophagitis, acid hypersecretion",
            "common_side_effects": "Headache, diarrhea, bloating",
            "warnings": "Take 30 minutes before first meal of the day",
            "default_dose": "40 mg",
            "default_freq": "Once daily before breakfast",
        },
        "cetirizine": {
            "generic_name": "Cetirizine Hydrochloride",
            "category": "Second-generation Antihistamine",
            "purpose": "Allergic rhinitis, urticaria & seasonal allergies",
            "common_side_effects": "Mild drowsiness, dry mouth, headache",
            "warnings": "Caution with CNS depressants and alcohol",
            "default_dose": "10 mg",
            "default_freq": "Once daily at bedtime",
        },
        "amoxicillin": {
            "generic_name": "Amoxicillin Trihydrate",
            "category": "Aminopenicillin Antibiotic",
            "purpose": "Bacterial respiratory, ENT, and soft tissue infections",
            "common_side_effects": "Diarrhea, nausea, skin rash",
            "warnings": "Contraindicated in penicillin allergy; complete full course",
            "default_dose": "500 mg",
            "default_freq": "Three times daily",
        },
        "azithromycin": {
            "generic_name": "Azithromycin",
            "category": "Macrolide Antibiotic",
            "purpose": "Respiratory tract infections, atypical pneumonia",
            "common_side_effects": "Diarrhea, nausea, abdominal cramping",
            "warnings": "Risk of QT prolongation; monitor with cardiac agents",
            "default_dose": "500 mg",
            "default_freq": "Once daily for 3-5 days",
        },
        "telmisartan": {
            "generic_name": "Telmisartan",
            "category": "ARB (Angiotensin II Receptor Blocker)",
            "purpose": "Hypertension & cardiovascular risk reduction",
            "common_side_effects": "Back pain, sinus congestion, dizziness",
            "warnings": "Contraindicated in pregnancy; monitor potassium",
            "default_dose": "40 mg",
            "default_freq": "Once daily",
        },
    }

    try:
        seen_names = set()
        for idx, up_file in enumerate(uploaded_files):
            contents = await up_file.read()
            file_ext = os.path.splitext(up_file.filename)[1] or ".jpg"
            save_name = f"{uuid.uuid4().hex}{file_ext}"
            save_path = os.path.join(UPLOADS_DIR, save_name)
            with open(save_path, "wb") as f:
                f.write(contents)
            img_url = f"/static/uploads/{save_name}"
            uploaded_urls.append(img_url)

            # Vision extraction
            raw_candidates = ai_explanation.extract_medicines_from_image(
                image_bytes=contents, filename=up_file.filename, api_key=custom_groq_key
            )

            # Decompose combination / FDC products (e.g. "Metoprolol & Amlodipine")
            expanded_candidates = []
            for cand in raw_candidates:
                c_name = cand.get("name", "").strip()
                if " & " in c_name or " + " in c_name:
                    sep = " & " if " & " in c_name else " + "
                    parts = [p.strip() for p in c_name.split(sep) if p.strip()]
                    dose_parts = (
                        cand.get("dose", "").split("/")
                        if "/" in cand.get("dose", "")
                        else [cand.get("dose", "")] * len(parts)
                    )
                    for i, p in enumerate(parts):
                        expanded_candidates.append(
                            {
                                "name": p.replace("Succinate", "")
                                .replace("Gastro-resistant", "")
                                .replace("Tablets", "")
                                .replace("Capsules", "")
                                .replace("IP", "")
                                .strip(),
                                "dose": dose_parts[i].strip()
                                if i < len(dose_parts)
                                else cand.get("dose", ""),
                                "frequency": cand.get("frequency", "Once daily"),
                                "confidence": cand.get("confidence", "high"),
                            }
                        )
                else:
                    expanded_candidates.append(cand)

            # Enrich each detected candidate with full clinical database details
            for cand in expanded_candidates:
                name = cand.get("name", "").strip()
                if not name:
                    continue
                name_norm = name.lower()
                if name_norm in seen_names:
                    continue
                seen_names.add(name_norm)

                # 1. Search SQLite medicines table
                cursor.execute(
                    """
                SELECT name, generic_name, category, purpose, common_side_effects, warnings 
                FROM medicines 
                WHERE name LIKE ? OR generic_name LIKE ? 
                LIMIT 1
                """,
                    (f"%{name}%", f"%{name}%"),
                )
                db_med = cursor.fetchone()

                # 2. Count known interactions in 160k DDInter dataset
                cursor.execute(
                    """
                SELECT COUNT(*) FROM interactions 
                WHERE medicine_a = ? OR medicine_b = ?
                """,
                    (name_norm, name_norm),
                )
                interaction_count = cursor.fetchone()[0]

                # Match from DB or clinical KB
                kb_info = clinical_kb.get(name_norm, {})

                if db_med:
                    cand_full = {
                        "name": db_med[0],
                        "generic_name": db_med[1]
                        or kb_info.get("generic_name", db_med[0]),
                        "category": db_med[2]
                        or kb_info.get("category", "Prescription Drug"),
                        "purpose": db_med[3]
                        or kb_info.get("purpose", "Therapeutic treatment"),
                        "common_side_effects": db_med[4]
                        or kb_info.get("common_side_effects", "None documented"),
                        "warnings": db_med[5]
                        or kb_info.get("warnings", "Consult prescribing physician"),
                        "dose": cand.get("dose")
                        or kb_info.get("default_dose", "As prescribed"),
                        "frequency": cand.get("frequency")
                        or kb_info.get("default_freq", "Once daily"),
                        "interaction_count": interaction_count,
                        "confidence": cand.get(
                            "confidence", "High (Database Verified)"
                        ),
                        "source_image": up_file.filename,
                    }
                elif kb_info:
                    cand_full = {
                        "name": name.title(),
                        "generic_name": kb_info.get("generic_name", name.title()),
                        "category": kb_info.get("category", "Prescription Medication"),
                        "purpose": kb_info.get("purpose", "Therapeutic treatment"),
                        "common_side_effects": kb_info.get(
                            "common_side_effects", "Mild gastrointestinal effects"
                        ),
                        "warnings": kb_info.get(
                            "warnings", "Use as directed by clinician"
                        ),
                        "dose": cand.get("dose")
                        or kb_info.get("default_dose", "Standard dose"),
                        "frequency": cand.get("frequency")
                        or kb_info.get("default_freq", "Once daily"),
                        "interaction_count": interaction_count,
                        "confidence": cand.get("confidence", "High (Verified)"),
                        "source_image": up_file.filename,
                    }
                else:
                    cand_full = {
                        "name": name.title(),
                        "generic_name": name.title(),
                        "category": "Prescription Medication",
                        "purpose": "Clinical therapy",
                        "common_side_effects": "Consult medical packaging leaflet",
                        "warnings": "Review interactions with physician",
                        "dose": cand.get("dose") or "Standard dose",
                        "frequency": cand.get("frequency") or "Once daily",
                        "interaction_count": interaction_count,
                        "confidence": cand.get("confidence", "Detected"),
                        "source_image": up_file.filename,
                    }

                all_candidates.append(cand_full)

        conn.close()
        return {
            "status": "success",
            "total_images": len(uploaded_files),
            "uploaded_urls": uploaded_urls,
            "candidates": all_candidates,
            "message": f"Successfully processed {len(uploaded_files)} photo(s). Retrieved full clinical details for {len(all_candidates)} medicine(s).",
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Image extraction error: {str(e)}")


# ----------------- REPORT GENERATION & PDF EXPORT -----------------
@app.post("/api/generate-report/{patient_id}")
async def generate_report_endpoint(
    patient_id: int, req: Optional[ExplainRequest] = None
):
    try:
        patient = database.get_patient(patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        medications = database.get_patient_medications(patient_id)
        risk_summary = risk_engine.analyze_patient_risk(patient, medications)

        lang = req.language if req else "en"
        custom_key = req.custom_groq_key if req else None

        ai_exp = ai_explanation.generate_plain_language_explanation(
            patient=patient,
            medications=medications,
            risk_summary=risk_summary,
            language=lang,
            api_key=custom_key,
        )

        report_id = f"REP-{datetime.datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        pdf_path = report_generator.generate_pdf_report(
            patient=patient,
            medications=medications,
            risk_summary=risk_summary,
            ai_explanation=ai_exp,
            report_id=report_id,
        )

        # Store in reports table
        try:
            conn = database.get_db()
            cursor = conn.cursor()
            cursor.execute(
                """
            INSERT INTO reports (report_id, patient_id, date, risk_level, risk_score, findings_json, ai_explanation, summary, pdf_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    report_id,
                    patient_id,
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    risk_summary.get("risk_level"),
                    risk_summary.get("risk_score"),
                    json.dumps(risk_summary.get("findings")),
                    ai_exp.get("text"),
                    f"Polypharmacy risk score: {risk_summary.get('risk_score')}, level: {risk_summary.get('risk_level')}",
                    pdf_path,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as db_e:
            print("Warning: could not record report in DB:", db_e)

        return {
            "status": "success",
            "report_id": report_id,
            "download_url": f"/api/reports/{report_id}/download",
            "filename": f"{report_id}.pdf",
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Report generation error: {str(e)}")


@app.get("/api/reports/{report_id}/download")
async def download_report_pdf(report_id: str):
    pdf_path = os.path.join(REPORTS_DIR, f"{report_id}.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Report PDF not found")
    return FileResponse(
        path=pdf_path, media_type="application/pdf", filename=f"{report_id}.pdf"
    )


# ----------------- SETTINGS & KEYS -----------------
@app.post("/api/settings/groq-key")
async def update_groq_key(payload: GroqKeyUpdate):
    key = payload.api_key.strip()
    os.environ["GROQ_API_KEY"] = key
    env_file = os.path.join(BASE_DIR, ".env")
    with open(env_file, "w", encoding="utf-8") as f:
        f.write(f"GROQ_API_KEY={key}\n")
    return {"status": "success", "message": "Groq API Key saved successfully!"}


@app.get("/api/system/status")
async def system_status():
    has_groq = bool(os.getenv("GROQ_API_KEY"))
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM interactions")
    inter_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM medicines")
    med_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM patients")
    pat_count = cursor.fetchone()[0]
    conn.close()

    return {
        "status": "online",
        "framework": "FastAPI",
        "groq_configured": has_groq,
        "database": {
            "total_interactions_indexed": inter_count,
            "curated_medicines": med_count,
            "patient_cases": pat_count,
        },
    }


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)

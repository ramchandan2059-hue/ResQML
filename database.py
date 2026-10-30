import csv
import os
import sqlite3
from typing import Optional

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database")
DB_PATH = os.path.join(DB_DIR, "polypharmacy.db")
TSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "interactions.tsv")

os.makedirs(DB_DIR, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes all 5 core tables + helper tables with optimized indexes."""
    conn = get_db()
    cursor = conn.cursor()

    # 1. Patients table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        patient_id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id TEXT UNIQUE NOT NULL,
        age INTEGER NOT NULL,
        biological_sex TEXT NOT NULL,
        conditions TEXT NOT NULL,
        condition_duration TEXT,
        frailty_allergies TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Medicines table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS medicines (
        medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        generic_name TEXT,
        category TEXT NOT NULL,
        purpose TEXT NOT NULL,
        common_side_effects TEXT,
        warnings TEXT
    );
    """)

    # 3. Patient Medications (for current case management)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patient_medications (
        entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL,
        medicine_id INTEGER,
        medicine_name TEXT NOT NULL,
        dose TEXT,
        frequency TEXT,
        duration TEXT,
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE,
        FOREIGN KEY (medicine_id) REFERENCES medicines(medicine_id)
    );
    """)

    # 4. Interactions table (controlled DDInter dataset)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS interactions (
        interaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        medicine_a TEXT NOT NULL COLLATE NOCASE,
        medicine_b TEXT NOT NULL COLLATE NOCASE,
        drug_a_display TEXT,
        drug_b_display TEXT,
        severity TEXT NOT NULL,
        explanation TEXT,
        reference TEXT DEFAULT 'DDInter Database v1.0 (Validated Clinical Interaction Dataset)'
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_interactions_pair ON interactions(medicine_a, medicine_b);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_interactions_b ON interactions(medicine_b);")

    # 5. Risk Rules table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS risk_rules (
        rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
        factor TEXT NOT NULL,
        points INTEGER NOT NULL,
        category TEXT NOT NULL,
        explanation TEXT NOT NULL
    );
    """)

    # 6. Reports table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        report_id TEXT PRIMARY KEY,
        patient_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        risk_level TEXT NOT NULL,
        risk_score INTEGER NOT NULL,
        findings_json TEXT NOT NULL,
        ai_explanation TEXT,
        summary TEXT,
        pdf_path TEXT,
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
    );
    """)

    conn.commit()
    conn.close()

def seed_default_rules_and_medicines():
    conn = get_db()
    cursor = conn.cursor()

    # Seed rules if empty
    cursor.execute("SELECT COUNT(*) FROM risk_rules")
    if cursor.fetchone()[0] == 0:
        rules = [
            ("Potential Major Drug Interaction", 3, "Interaction", "Co-administration of drugs known to cause major adverse physiological interaction"),
            ("Potential Moderate Drug Interaction", 2, "Interaction", "Co-administration requiring clinical monitoring or dosage titration"),
            ("Potential Minor Drug Interaction", 1, "Interaction", "Co-administration with minor pharmacological synergy or competition"),
            ("Duplicate / Overlapping Therapeutic Class", 2, "Therapeutic Duplication", "Patient is taking multiple agents from the same therapeutic class (e.g. 2 statins, 2 NSAIDs)"),
            ("Polypharmacy Threshold (≥ 5 Medications)", 1, "Polypharmacy Count", "Taking 5 or more concurrent medicines significantly elevates metabolic and adherence risk"),
            ("Geriatric High-Risk Factor (Age ≥ 65)", 1, "Patient Factor", "Age-related changes in renal clearance, hepatic metabolism, and increased frailty"),
            ("Renal Risk with NSAID/ACE-Inhibitor", 1, "Disease-Drug Interaction", "NSAIDs blunt antihypertensive effect and risk acute kidney injury when combined with ACEI/ARB"),
            ("Anticoagulant / Antiplatelet Bleeding Risk", 1, "Patient Factor", "Concurrent antiplatelet/anticoagulant therapy substantially amplifies major bleeding hazard")
        ]
        cursor.executemany("INSERT INTO risk_rules (factor, points, category, explanation) VALUES (?, ?, ?, ?)", rules)

    # Core Curated Medicines from Project Specification
    curated_medicines = [
        ("Metformin", "Metformin Hydrochloride", "Antidiabetic (Biguanide)", "Type 2 diabetes mellitus glycemic control", "Nausea, diarrhea, stomach discomfort, metallic taste", "Monitor renal function (eGFR); risk of lactic acidosis; avoid with heavy alcohol consumption"),
        ("Amlodipine", "Amlodipine Besylate", "Calcium-channel blocker", "Hypertension & angina management", "Peripheral edema, dizziness, flushing, palpitations", "Monitor blood pressure; cautious titration in severe hepatic impairment"),
        ("Lisinopril", "Lisinopril", "ACE inhibitor", "Hypertension & heart failure management", "Persistent dry cough, hyperkalemia, dizziness, headache", "Contraindicated in pregnancy; monitor serum potassium and renal markers"),
        ("Losartan", "Losartan Potassium", "ARB (Angiotensin II Receptor Blocker)", "Hypertension & diabetic nephropathy protection", "Dizziness, fatigue, hyperkalemia", "Do not combine dual renin-angiotensin blockade with ACE inhibitors"),
        ("Furosemide", "Furosemide", "Loop Diuretic", "Edema associated with heart failure, cirrhosis, and renal disease", "Electrolyte depletion (hypokalemia), dehydration, hypotension", "Monitor electrolytes, BUN, and creatinine routinely"),
        ("Warfarin", "Warfarin Sodium", "Anticoagulant (Vitamin K antagonist)", "Prevention and treatment of thromboembolic events (VTE, DVT, stroke in AFib)", "Bleeding episodes, bruising, epistaxis", "Narrow therapeutic index; requires routine INR monitoring; extensive drug-drug and food interactions"),
        ("Aspirin", "Acetylsalicylic acid", "Antiplatelet / Salicylate", "Cardiovascular protection & antiplatelet prophylaxis", "Dyspepsia, GI ulceration, bleeding tendency", "Increased hemorrhagic risk when combined with other anticoagulants or NSAIDs"),
        ("Ibuprofen", "Ibuprofen", "NSAID", "Relief of mild-to-moderate pain, inflammation, and fever", "Gastric ulceration, renal toxicity, fluid retention, dyspepsia", "Can blunt antihypertensive medications; contraindicated in active GI bleed and severe renal failure"),
        ("Paracetamol", "Acetaminophen", "Analgesic / Antipyretic", "Analgesia for mild-to-moderate pain and reduction of fever", "Rare at therapeutic doses; nausea, allergic skin rash", "Max 4000mg/day (lower in cirrhosis/elderly); hepatotoxicity risk on overdose or alcohol co-use"),
        ("Atorvastatin", "Atorvastatin Calcium", "Statin (HMG-CoA Reductase Inhibitor)", "Hypercholesterolemia & atherosclerotic cardiovascular prevention", "Myalgia, arthralgia, mild elevation of hepatic transaminases", "Avoid concurrent potent CYP3A4 inhibitors without dose adjustment; watch for rhabdomyolysis"),
        ("Simvastatin", "Simvastatin", "Statin (HMG-CoA Reductase Inhibitor)", "Primary hypercholesterolemia and cardiovascular risk reduction", "Myopathy, headache, abdominal pain", "Higher susceptibility to CYP3A4 interactions than atorvastatin; strict dose ceilings with calcium blockers"),
        ("Omeprazole", "Omeprazole", "Proton-pump inhibitor (PPI)", "GERD, peptic ulcer disease, NSAID gastroprotection", "Headache, diarrhea, abdominal pain, vitamin B12 deficiency on chronic use", "CYP2C19 inhibitor; can diminish clopidogrel efficacy and alter drug absorption requiring acidic pH"),
        ("Glipizide", "Glipizide", "Antidiabetic (Sulfonylurea)", "Type 2 diabetes glycemic control stimulating insulin secretion", "Hypoglycemia, weight gain, dizziness", "Risk of prolonged hypoglycemia especially in renal decline or when taken with NSAIDs"),
        ("Sertraline", "Sertraline Hydrochloride", "SSRI (Antidepressant)", "Major depressive disorder, OCD, panic disorder, PTSD", "Insomnia, nausea, tremor, sexual dysfunction", "Risk of serotonin syndrome when combined with other serotonergic agents; increases GI bleeding risk with NSAIDs"),
        ("Diazepam", "Diazepam", "Benzodiazepine", "Anxiety disorders, muscle spasms, alcohol withdrawal symptoms", "Sedation, ataxia, cognitive slowing, respiratory depression", "Potentiated CNS depression with sedatives, opioids, or alcohol; dependence liability on chronic use"),
        ("Cobicistat", "Cobicistat", "CYP3A Inhibitor / PK Enhancer", "Pharmacokinetic booster for antiviral regimens", "Nausea, jaundice, elevated serum creatinine", "Potent CYP3A inhibitor; causes major interactions with statins, antiarrhythmics, and sedatives"),
        ("Dolutegravir", "Dolutegravir", "Antiretroviral (Integrase Inhibitor)", "HIV-1 infection treatment", "Insomnia, fatigue, headache", "Chelates with polyvalent cations (calcium, magnesium, iron) reducing absorption significantly"),
        ("Prednisolone", "Prednisolone", "Corticosteroid", "Inflammatory conditions, autoimmune disorders, asthma exacerbations", "Hyperglycemia, fluid retention, osteoporosis, insomnia", "Increases GI ulceration risk with NSAIDs/aspirin; blunts antidiabetic medicines"),
        ("Digoxin", "Digoxin", "Cardiac Glycoside", "Atrial fibrillation rate control and congestive heart failure", "Nausea, vomiting, visual halos, bradycardia, arrhythmias", "Narrow therapeutic window; toxicity heightened by hypokalemia from loop diuretics or amiodarone"),
        ("Clopidogrel", "Clopidogrel Bisulfate", "Antiplatelet (P2Y12 inhibitor)", "Prevention of atherothrombotic events in CAD and ischemic stroke", "Bleeding, bruising, purpura", "Requires CYP2C19 bioactivation; effectiveness blunted by omeprazole; bleeding risk multiplied with aspirin/warfarin")
    ]

    for med in curated_medicines:
        cursor.execute("""
        INSERT INTO medicines (name, generic_name, category, purpose, common_side_effects, warnings)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            generic_name=excluded.generic_name,
            category=excluded.category,
            purpose=excluded.purpose,
            common_side_effects=excluded.common_side_effects,
            warnings=excluded.warnings
        """, med)

    # Controlled high-profile interaction explanations from medical consensus
    known_explanations = [
        ("Warfarin", "Aspirin", "Major", "Concurrent use substantially elevates hemorrhagic hazard via dual inhibition of coagulation cascade (warfarin) and platelet aggregation (aspirin). Routine co-prescription should only occur under documented specialist oversight with close INR monitoring."),
        ("Warfarin", "Ibuprofen", "Major", "NSAIDs like ibuprofen disrupt gastric mucosal protection while competitively displacing warfarin from protein binding, compounding ulceration and severe gastrointestinal hemorrhage risk."),
        ("Lisinopril", "Losartan", "Major", "Dual renin-angiotensin-aldosterone system (RAAS) blockade increases the risk of severe hyperkalemia, acute kidney injury, and profound hypotension without providing incremental cardiovascular benefit."),
        ("Lisinopril", "Ibuprofen", "Moderate", "NSAIDs inhibit renal vasodilatory prostaglandins, attenuating the antihypertensive efficacy of ACE inhibitors and precipitating acute deterioration of renal function, particularly in volume-depleted or elderly patients."),
        ("Losartan", "Ibuprofen", "Moderate", "NSAIDs can reduce the antihypertensive effect of ARBs and significantly compromise renal hemodynamics, creating heightened acute kidney injury vulnerability."),
        ("Aspirin", "Ibuprofen", "Moderate", "Ibuprofen competitively hinders irreversible platelet cyclooxygenase (COX-1) acetylation by low-dose aspirin, impairing aspirin's cardioprotective antiplatelet effect while worsening GI irritation."),
        ("Omeprazole", "Clopidogrel", "Major", "Omeprazole competitively inhibits hepatic CYP2C19, impeding bioactivation of clopidogrel into its active antiplatelet metabolite and leaving the patient unprotected against recurrent cardiovascular ischemic events."),
        ("Atorvastatin", "Cobicistat", "Major", "Cobicistat strongly inhibits CYP3A4, dramatically elevating plasma concentrations of atorvastatin and substantially augmenting the risk of severe myopathy and rhabdomyolysis."),
        ("Simvastatin", "Amlodipine", "Major", "Amlodipine inhibits simvastatin metabolism, raising systemic exposure. Simvastatin daily dosage should not exceed 20 mg when co-administered with amlodipine to avert myopathy."),
        ("Metformin", "Furosemide", "Moderate", "Furosemide increases metformin peak plasma concentrations while potentially precipitating volume depletion, which may heighten the rare risk of metformin-associated lactic acidosis."),
        ("Glipizide", "Ibuprofen", "Moderate", "NSAIDs displace sulfonylureas from plasma protein-binding sites and impede clearance, creating heightened liability for sudden severe hypoglycemia."),
        ("Sertraline", "Aspirin", "Moderate", "SSRIs reduce platelet serotonin reuptake, which impairs platelet activation. Concomitant aspirin or NSAID therapy compounds upper gastrointestinal bleeding risk."),
        ("Diazepam", "Sertraline", "Moderate", "Sertraline can moderately inhibit CYP2C19/CYP3A4 clearance of diazepam, extending sedation, motor incoordination, and psychomotor impairment."),
        ("Furosemide", "Digoxin", "Major", "Loop diuretics cause renal potassium and magnesium wasting; hypokalemia sharply sensitizes cardiac myocytes to digoxin toxicity, triggering fatal ventricular arrhythmias."),
        ("Calcium acetate", "Dolutegravir", "Major", "Divalent calcium cations chelate with dolutegravir in the gastrointestinal tract, drastically decreasing dolutegravir absorption and resulting in viral virological breakthrough.")
    ]

    for drug_a, drug_b, sev, exp in known_explanations:
        a_low = drug_a.strip().lower()
        b_low = drug_b.strip().lower()
        # insert both orientations for direct quick lookup or check existing
        cursor.execute("""
        SELECT interaction_id FROM interactions 
        WHERE (medicine_a = ? AND medicine_b = ?) OR (medicine_a = ? AND medicine_b = ?)
        """, (a_low, b_low, b_low, a_low))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("""
            UPDATE interactions SET severity = ?, explanation = ?
            WHERE interaction_id = ?
            """, (sev, exp, existing[0]))
        else:
            cursor.execute("""
            INSERT INTO interactions (medicine_a, medicine_b, drug_a_display, drug_b_display, severity, explanation, reference)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (a_low, b_low, drug_a, drug_b, sev, exp, "Clinical Reference & British National Formulary / DDInter"))

    conn.commit()
    conn.close()

def seed_ddinter_dataset(limit_records: Optional[int] = None):
    """
    Seeds interactions from interactions.tsv if not already imported.
    Processes lines efficiently in chunks.
    """
    if not os.path.exists(TSV_PATH):
        print(f"TSV dataset not found at {TSV_PATH}")
        return

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM interactions")
    count = cursor.fetchone()[0]

    # If only seed records exist (< 100), ingest the dataset
    if count < 100:
        print("Ingesting DDInter interactions dataset into SQLite...")
        rows_to_insert = []
        seen_pairs = set()

        with open(TSV_PATH, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f, delimiter='\t')
            header = next(reader, None)
            
            for row in reader:
                if len(row) < 5:
                    continue
                # Row format: DDInterID_A, Drug_A, DDInterID_B, Drug_B, Level
                _, drug_a, _, drug_b, level = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip(), row[4].strip()
                if not drug_a or not drug_b or not level or level == "Level":
                    continue
                
                a_low = drug_a.lower()
                b_low = drug_b.lower()
                pair_key = tuple(sorted([a_low, b_low]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                explanation = f"Potential pharmacological interaction documented between {drug_a} and {drug_b} ({level} severity)."
                rows_to_insert.append((
                    a_low, b_low, drug_a, drug_b, level, explanation, "DDInter Database v1.0"
                ))

                if limit_records and len(rows_to_insert) >= limit_records:
                    break

                if len(rows_to_insert) >= 10000:
                    cursor.executemany("""
                    INSERT INTO interactions (medicine_a, medicine_b, drug_a_display, drug_b_display, severity, explanation, reference)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, rows_to_insert)
                    conn.commit()
                    rows_to_insert.clear()

            if rows_to_insert:
                cursor.executemany("""
                INSERT INTO interactions (medicine_a, medicine_b, drug_a_display, drug_b_display, severity, explanation, reference)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, rows_to_insert)
                conn.commit()

        print(f"Successfully seeded interactions. Total unique pairs indexed: {len(seen_pairs)}")

    conn.close()

def seed_synthetic_patients():
    """Seeds synthetic demo patients matching the project guide."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM patients")
    if cursor.fetchone()[0] == 0:
        patients = [
            ("CASE-DEMO-001", 70, "Male", "Hypertension, Type 2 Diabetes", "5 years", "Frail, Mild renal decline"),
            ("CASE-DEMO-002", 68, "Female", "Osteoarthritis, Hypertension", "8 years", "Penicillin allergy"),
            ("CASE-DEMO-003", 52, "Male", "Hypercholesterolemia, GERD", "3 years", "No known drug allergies")
        ]
        cursor.executemany("""
        INSERT INTO patients (case_id, age, biological_sex, conditions, condition_duration, frailty_allergies)
        VALUES (?, ?, ?, ?, ?, ?)
        """, patients)
        conn.commit()

        # Seed sample medicines for CASE-DEMO-001 (High Risk case: Metformin, Amlodipine, Lisinopril, Warfarin, Aspirin)
        p1_id = 1
        p1_meds = [
            ("Metformin", "500 mg", "Twice daily", "5 years"),
            ("Amlodipine", "5 mg", "Once daily", "4 years"),
            ("Lisinopril", "10 mg", "Once daily", "3 years"),
            ("Warfarin", "3 mg", "Once daily evening", "1 year"),
            ("Aspirin", "75 mg", "Once daily", "2 years")
        ]
        for name, dose, freq, dur in p1_meds:
            cursor.execute("SELECT medicine_id FROM medicines WHERE name = ? COLLATE NOCASE", (name,))
            row = cursor.fetchone()
            med_id = row[0] if row else None
            cursor.execute("""
            INSERT INTO patient_medications (patient_id, medicine_id, medicine_name, dose, frequency, duration)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (p1_id, med_id, name, dose, freq, dur))

        # Seed sample medicines for CASE-DEMO-002 (Moderate Risk case: Ibuprofen, Lisinopril, Amlodipine)
        p2_id = 2
        p2_meds = [
            ("Ibuprofen", "400 mg", "Three times daily as needed", "2 months"),
            ("Lisinopril", "20 mg", "Once daily", "6 years"),
            ("Amlodipine", "10 mg", "Once daily", "4 years")
        ]
        for name, dose, freq, dur in p2_meds:
            cursor.execute("SELECT medicine_id FROM medicines WHERE name = ? COLLATE NOCASE", (name,))
            row = cursor.fetchone()
            med_id = row[0] if row else None
            cursor.execute("""
            INSERT INTO patient_medications (patient_id, medicine_id, medicine_name, dose, frequency, duration)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (p2_id, med_id, name, dose, freq, dur))

        # Seed sample medicines for CASE-DEMO-003 (Low Risk case: Atorvastatin, Omeprazole)
        p3_id = 3
        p3_meds = [
            ("Atorvastatin", "20 mg", "Once daily at night", "2 years"),
            ("Omeprazole", "20 mg", "Once daily before breakfast", "1 year")
        ]
        for name, dose, freq, dur in p3_meds:
            cursor.execute("SELECT medicine_id FROM medicines WHERE name = ? COLLATE NOCASE", (name,))
            row = cursor.fetchone()
            med_id = row[0] if row else None
            cursor.execute("""
            INSERT INTO patient_medications (patient_id, medicine_id, medicine_name, dose, frequency, duration)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (p3_id, med_id, name, dose, freq, dur))

        conn.commit()
    conn.close()

# Helper queries
def get_all_medicines():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM medicines ORDER BY name ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def search_medicines(term: str, limit: int = 25):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM medicines 
    WHERE name LIKE ? OR generic_name LIKE ? OR category LIKE ? 
    ORDER BY name ASC LIMIT ?
    """, (f"%{term}%", f"%{term}%", f"%{term}%", limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_patient(patient_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM patients WHERE patient_id = ?", (patient_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_patient_medications(patient_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT pm.*, m.category, m.purpose, m.common_side_effects, m.warnings
    FROM patient_medications pm
    LEFT JOIN medicines m ON pm.medicine_id = m.medicine_id
    WHERE pm.patient_id = ?
    ORDER BY pm.entry_id ASC
    """, (patient_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def find_interaction(drug_a: str, drug_b: str):
    conn = get_db()
    cursor = conn.cursor()
    a_low = drug_a.strip().lower()
    b_low = drug_b.strip().lower()
    cursor.execute("""
    SELECT * FROM interactions
    WHERE (medicine_a = ? AND medicine_b = ?) 
       OR (medicine_a = ? AND medicine_b = ?)
    LIMIT 1
    """, (a_low, b_low, b_low, a_low))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

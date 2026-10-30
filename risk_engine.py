from typing import List, Dict, Any
import database

def analyze_patient_risk(patient: Dict[str, Any], medications: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Deterministic rule-based risk engine following the project specification:
    - Checks every pair of medications against the interaction database (+3 for Major, +2 for Moderate, +1 for Minor)
    - Checks for duplicate / overlapping therapeutic drug classes (+2 points)
    - Checks for high medication count / polypharmacy >= 5 (+1 point)
    - Evaluates selected patient factors (+1 point each)
    
    Prototype Thresholds:
      0-2: LOW (Green)
      3-4: MEDIUM (Yellow/Orange)
      5+:  HIGH (Red)
    """
    findings = []
    risk_score = 0
    categories_seen = {}
    med_names = [m["medicine_name"].strip() for m in medications]
    
    # 1. Pairwise Drug-Drug Interaction Check
    interaction_pairs_checked = set()
    n = len(medications)
    for i in range(n):
        for j in range(i + 1, n):
            med_a = med_names[i]
            med_b = med_names[j]
            pair_key = tuple(sorted([med_a.lower(), med_b.lower()]))
            if pair_key in interaction_pairs_checked:
                continue
            interaction_pairs_checked.add(pair_key)
            
            match = database.find_interaction(med_a, med_b)
            if match:
                severity = match.get("severity", "Moderate")
                points = 3 if severity == "Major" else (2 if severity == "Moderate" else 1)
                risk_score += points
                findings.append({
                    "type": "interaction",
                    "title": f"Drug Interaction: {match.get('drug_a_display', med_a)} + {match.get('drug_b_display', med_b)}",
                    "medicine_1": match.get('drug_a_display', med_a),
                    "medicine_2": match.get('drug_b_display', med_b),
                    "severity": severity,
                    "points": points,
                    "explanation": match.get("explanation") or f"Documented {severity} interaction between {med_a} and {med_b}.",
                    "reference": match.get("reference") or "DDInter Database v1.0 (Clinical Interaction Dataset)"
                })

    # 2. Duplicate / Overlapping Therapeutic Class Check
    for m in medications:
        cat = (m.get("category") or "").strip()
        # Group similar categories: e.g. Statins, NSAIDs, Antidiabetics, Anticoagulants
        if not cat:
            # Try to lookup in medicines table
            row = database.get_db().cursor().execute("SELECT category FROM medicines WHERE name = ? COLLATE NOCASE", (m["medicine_name"],)).fetchone()
            if row and row[0]:
                cat = row[0]
        
        if cat:
            norm_cat = cat.lower()
            if norm_cat not in categories_seen:
                categories_seen[norm_cat] = []
            categories_seen[norm_cat].append(m["medicine_name"])

    for cat_name, drugs in categories_seen.items():
        if len(drugs) > 1:
            risk_score += 2
            findings.append({
                "type": "duplicate_class",
                "title": f"Therapeutic Class Duplication: {cat_name.title()}",
                "medicine_1": drugs[0],
                "medicine_2": drugs[1],
                "severity": "Moderate",
                "points": 2,
                "explanation": f"Patient is taking multiple agents from the same therapeutic category ({', '.join(drugs)}). This raises concern for therapeutic duplication or cumulative organ toxicity.",
                "reference": "Beers Criteria & BNF Therapeutic Duplication Guidelines"
            })

    # 3. High Medicine Count / Polypharmacy Check (>= 5 medications)
    if len(medications) >= 5:
        risk_score += 1
        findings.append({
            "type": "polypharmacy_count",
            "title": f"Polypharmacy Detected ({len(medications)} Medications Concurrent)",
            "medicine_1": f"{len(medications)} active medicines",
            "medicine_2": "",
            "severity": "Moderate",
            "points": 1,
            "explanation": f"Patient is prescribed {len(medications)} medications concurrently. Clinical evidence demonstrates that regimen complexity (≥5 medications) significantly increases non-adherence, drug cascades, and adverse drug events.",
            "reference": "WHO Polypharmacy Guidance & Prescribing Safety Indicators"
        })

    # 4. Patient-Specific Risk Factors (Age, Frailty, Conditions)
    age = patient.get("age", 0)
    conditions_str = (patient.get("conditions") or "").lower()
    
    # 4a. Age >= 65 (Geriatric / Frailty Factor)
    if age >= 65:
        risk_score += 1
        findings.append({
            "type": "patient_factor",
            "title": f"Geriatric Risk Factor (Age: {age})",
            "medicine_1": "Regimen wide",
            "medicine_2": "",
            "severity": "Low",
            "points": 1,
            "explanation": f"Patient is {age} years old. Advanced age diminishes glomerular filtration rate, alters hepatic CYP metabolism, and increases vulnerability to orthostatic hypotension and sedation.",
            "reference": "STOPP/START Criteria & Beers Criteria for Older Adults"
        })

    # 4b. Condition-Drug Synergy Risks
    med_lower_list = [m.lower() for m in med_names]
    has_nsaid = any("ibuprofen" in m or "diclofenac" in m or "naproxen" in m for m in med_lower_list)
    has_raas = any("lisinopril" in m or "losartan" in m or "ramipril" in m or "enalapril" in m for m in med_lower_list)
    has_anticoag = any("warfarin" in m or "apixaban" in m or "rivaroxaban" in m for m in med_lower_list)
    has_antiplatelet = any("aspirin" in m or "clopidogrel" in m for m in med_lower_list)

    if ("hypertension" in conditions_str or "kidney" in conditions_str or "renal" in conditions_str) and has_nsaid and has_raas:
        risk_score += 1
        findings.append({
            "type": "patient_disease_interaction",
            "title": "Triple-Whammy Risk Factor (Renal / Blood Pressure Impairment)",
            "medicine_1": "NSAID",
            "medicine_2": "RAAS Inhibitor",
            "severity": "Major",
            "points": 1,
            "explanation": "Concurrent NSAID and ACEI/ARB in a patient with hypertension/renal susceptibility impairs afferent arteriolar perfusion and blunts blood pressure control, carrying high risk of Acute Kidney Injury (AKI).",
            "reference": "National Institute for Health and Care Excellence (NICE) Clinical Guidelines"
        })

    if has_anticoag and has_antiplatelet:
        risk_score += 1
        findings.append({
            "type": "patient_factor",
            "title": "High Hemorrhagic Bleeding Risk Factor",
            "medicine_1": "Anticoagulant",
            "medicine_2": "Antiplatelet",
            "severity": "Major",
            "points": 1,
            "explanation": "Concurrent anticoagulant and antiplatelet therapy dramatically elevates major gastrointestinal and intracerebral bleeding hazard. Regular hemoglobin/INR surveillance is strongly advised.",
            "reference": "CHEST Guidelines on Antithrombotic Therapy"
        })

    # 5. Convert points to Prototype Risk Level
    # 0-2 = LOW, 3-4 = MEDIUM, 5+ = HIGH
    if risk_score <= 2:
        risk_level = "LOW"
    elif risk_score <= 4:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "total_medicines": len(medications),
        "total_issues": len(findings),
        "interaction_count": sum(1 for f in findings if f["type"] == "interaction"),
        "patient_factor_count": sum(1 for f in findings if "patient" in f["type"]),
        "duplicate_count": sum(1 for f in findings if f["type"] == "duplicate_class"),
        "findings": findings
    }

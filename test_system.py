import os
import unittest
from unittest.mock import patch
import database
import risk_engine
import ai_explanation
import report_generator

class TestPolypharmacyAnalyzer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        database.init_db()
        database.seed_default_rules_and_medicines()
        database.seed_synthetic_patients()

    def test_database_and_interactions(self):
        # Test Warfarin + Aspirin
        match = database.find_interaction("Warfarin", "Aspirin")
        self.assertIsNotNone(match, "Warfarin + Aspirin interaction should be found")
        self.assertEqual(match["severity"], "Major")

        # Test Lisinopril + Ibuprofen
        match2 = database.find_interaction("Ibuprofen", "Lisinopril")
        self.assertIsNotNone(match2, "Lisinopril + Ibuprofen interaction should be found")
        self.assertEqual(match2["severity"], "Moderate")

        # Test search
        res = database.search_medicines("Metformin")
        self.assertTrue(len(res) > 0, "Metformin should be in database")

    def test_risk_engine_high_risk_case(self):
        patient = {
            "age": 70,
            "biological_sex": "Male",
            "conditions": "Hypertension, Type 2 Diabetes",
            "condition_duration": "5 years"
        }
        medications = [
            {"medicine_name": "Metformin", "dose": "500 mg", "category": "Antidiabetic (Biguanide)"},
            {"medicine_name": "Amlodipine", "dose": "5 mg", "category": "Calcium-channel blocker"},
            {"medicine_name": "Lisinopril", "dose": "10 mg", "category": "ACE inhibitor"},
            {"medicine_name": "Warfarin", "dose": "3 mg", "category": "Anticoagulant (Vitamin K antagonist)"},
            {"medicine_name": "Aspirin", "dose": "75 mg", "category": "Antiplatelet / Salicylate"}
        ]
        result = risk_engine.analyze_patient_risk(patient, medications)
        print("High Risk Test Result:", result["risk_score"], result["risk_level"])
        self.assertGreaterEqual(result["risk_score"], 5, "Case 1 score should be >= 5 (High Risk)")
        self.assertEqual(result["risk_level"], "HIGH")
        self.assertTrue(any(f["type"] == "interaction" for f in result["findings"]))
        self.assertTrue(any(f["type"] == "polypharmacy_count" for f in result["findings"]))

    def test_risk_engine_moderate_risk_case(self):
        # Case designed for Medium Risk (Score 3-4)
        patient = {
            "age": 55,
            "biological_sex": "Female",
            "conditions": "Osteoarthritis, Mild Hypertension",
            "condition_duration": "3 years"
        }
        medications = [
            {"medicine_name": "Ibuprofen", "dose": "400 mg", "category": "NSAID"},
            {"medicine_name": "Lisinopril", "dose": "10 mg", "category": "ACE inhibitor"}
        ]
        result = risk_engine.analyze_patient_risk(patient, medications)
        print("Moderate Risk Test Result:", result["risk_score"], result["risk_level"])
        self.assertIn(result["risk_score"], [3, 4], "Case should have score 3-4 (Medium Risk)")
        self.assertEqual(result["risk_level"], "MEDIUM")

    def test_risk_engine_low_risk_case(self):
        patient = {
            "age": 52,
            "biological_sex": "Male",
            "conditions": "Hypercholesterolemia",
            "condition_duration": "2 years"
        }
        medications = [
            {"medicine_name": "Atorvastatin", "dose": "20 mg", "category": "Statin"}
        ]
        result = risk_engine.analyze_patient_risk(patient, medications)
        print("Low Risk Test Result:", result["risk_score"], result["risk_level"])
        self.assertLessEqual(result["risk_score"], 2, "Single medicine should be Low Risk")
        self.assertEqual(result["risk_level"], "LOW")

    def test_multilingual_explanation(self):
        patient = {"age": 70, "biological_sex": "Male", "conditions": "Hypertension"}
        medications = [{"medicine_name": "Warfarin"}, {"medicine_name": "Aspirin"}]
        risk = {"risk_score": 5, "risk_level": "HIGH", "findings": [{"title": "Warfarin + Aspirin", "severity": "Major", "explanation": "Bleeding risk"}]}
        
        with patch.object(ai_explanation, "get_groq_client", return_value=None):
            for lang in ["en", "hi", "pa"]:
                exp = ai_explanation.generate_plain_language_explanation(patient, medications, risk, language=lang)
                self.assertIn("text", exp)
                self.assertTrue(len(exp["text"]) > 50, f"Explanation in {lang} should be generated")

    def test_groq_model_ids_are_current(self):
        self.assertEqual(ai_explanation.GROQ_TEXT_MODELS, ["openai/gpt-oss-120b", "openai/gpt-oss-20b"])
        self.assertEqual(ai_explanation.GROQ_VISION_MODELS, ["qwen/qwen3.8-27b"])

    def test_pdf_report_generation(self):
        patient = {
            "case_id": "CASE-TEST-999",
            "age": 70,
            "biological_sex": "Male",
            "conditions": "Hypertension, Diabetes",
            "condition_duration": "5 years",
            "frailty_allergies": "None"
        }
        medications = [
            {"medicine_name": "Metformin", "dose": "500 mg", "frequency": "BID", "duration": "5y", "category": "Antidiabetic"},
            {"medicine_name": "Warfarin", "dose": "3 mg", "frequency": "Daily", "duration": "1y", "category": "Anticoagulant"}
        ]
        risk = {
            "risk_score": 4,
            "risk_level": "MEDIUM",
            "total_issues": 1,
            "findings": [
                {"title": "Test Alert", "severity": "Moderate", "points": 2, "explanation": "Test explanation", "reference": "BNF"}
            ]
        }
        exp = {"text": "Simple test summary for PDF.", "model": "Test Model"}
        pdf_path = report_generator.generate_pdf_report(patient, medications, risk, exp, "REP-TEST-001")
        self.assertTrue(os.path.exists(pdf_path), "PDF file should be created")
        self.assertGreater(os.path.getsize(pdf_path), 1000, "PDF size should be > 1KB")
        print("Generated test PDF at:", pdf_path)

if __name__ == "__main__":
    unittest.main()

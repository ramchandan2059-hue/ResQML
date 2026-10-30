import os
import sys
import time
import sqlite3
import csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "polypharmacy.db")
TSV_PATH = os.path.join(BASE_DIR, "data", "interactions.tsv")
XLSX_PATH = os.path.join(BASE_DIR, "Data.xlsx")

import database

def seed_all():
    print("=" * 60)
    print("Initializing Polypharmacy Risk Analyzer Database...")
    print("=" * 60)
    start_time = time.time()
    
    # 1. Initialize tables
    database.init_db()
    print("[OK] Initialized 5 core tables + patient_medications in SQLite")
    
    # 2. Seed default rules and curated medicines
    database.seed_default_rules_and_medicines()
    print("[OK] Seeded risk rules and curated core medicines with warnings & side effects")
    
    # 3. Seed synthetic patient cases
    database.seed_synthetic_patients()
    print("[OK] Seeded synthetic demonstration patient cases (High, Moderate, Low risk)")

    # 4. Ingest interactions dataset
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM interactions")
    existing_count = cursor.fetchone()[0]

    if existing_count < 100:
        print("[*] Ingesting interactions dataset...")
        t0 = time.time()
        inserted = 0
        seen_pairs = set()
        batch = []

        if os.path.exists(TSV_PATH):
            print(f"Reading from TSV: {TSV_PATH}")
            with open(TSV_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f, delimiter='\t')
                header = next(reader, None)
                for row in reader:
                    if len(row) < 5:
                        continue
                    _, drug_a, _, drug_b, level = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip(), row[4].strip()
                    if not drug_a or not drug_b or not level or level == "Level":
                        continue
                    a_low = drug_a.lower()
                    b_low = drug_b.lower()
                    pair = tuple(sorted([a_low, b_low]))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    exp = f"Documented {level.lower()} pharmacological interaction between {drug_a} and {drug_b}."
                    batch.append((a_low, b_low, drug_a, drug_b, level, exp, "DDInter Database v1.0"))
                    
                    if len(batch) >= 10000:
                        cursor.executemany("""
                        INSERT INTO interactions (medicine_a, medicine_b, drug_a_display, drug_b_display, severity, explanation, reference)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, batch)
                        conn.commit()
                        inserted += len(batch)
                        batch.clear()
        elif os.path.exists(XLSX_PATH):
            print(f"Reading from Excel: {XLSX_PATH}")
            import pandas as pd
            df = pd.read_excel(XLSX_PATH)
            for _, row in df.iterrows():
                drug_a = str(row['Drug_A']).strip()
                drug_b = str(row['Drug_B']).strip()
                level = str(row['Level']).strip()
                if not drug_a or not drug_b or not level or level == "Level":
                    continue
                a_low = drug_a.lower()
                b_low = drug_b.lower()
                pair = tuple(sorted([a_low, b_low]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                exp = f"Documented {level.lower()} pharmacological interaction between {drug_a} and {drug_b}."
                batch.append((a_low, b_low, drug_a, drug_b, level, exp, "DDInter Database v1.0"))
                if len(batch) >= 10000:
                    cursor.executemany("""
                    INSERT INTO interactions (medicine_a, medicine_b, drug_a_display, drug_b_display, severity, explanation, reference)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, batch)
                    conn.commit()
                    inserted += len(batch)
                    batch.clear()

        if batch:
            cursor.executemany("""
            INSERT INTO interactions (medicine_a, medicine_b, drug_a_display, drug_b_display, severity, explanation, reference)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, batch)
            conn.commit()
            inserted += len(batch)

        print(f"[OK] Successfully inserted {inserted} unique interaction records in {time.time() - t0:.2f}s")
    else:
        print(f"[OK] Interactions table already contains {existing_count} records.")

    conn.close()
    print(f"[OK] Database setup complete in {time.time() - start_time:.2f}s!")

if __name__ == "__main__":
    seed_all()

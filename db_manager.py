# db_manager.py
import sqlite3
import streamlit as st

def get_connection():
    return sqlite3.connect('finanzen.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # --- 1. WICHTIG: ERST ALLE TABELLEN ERSTELLEN ---
    # Dadurch gibt es keinen Fehler mehr, falls die DB ganz neu ist
    c.execute('''CREATE TABLE IF NOT EXISTS konten (name TEXT PRIMARY KEY, typ TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS anfangsbestaende (id INTEGER PRIMARY KEY, konto TEXT, monat TEXT, betrag REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transaktionen (id INTEGER PRIMARY KEY, konto TEXT, typ TEXT, betrag REAL, beschreibung TEXT, datum TEXT, monat TEXT, status TEXT, modus TEXT, link_id TEXT)''')
    
    # --- 2. AUTOMATISCHES CLEANUP ---
    alte_konten = ['Baloise Bank', 'Helvetia', 'Swiss Life']
    for alt in alte_konten:
        c.execute("DELETE FROM konten WHERE name=?", (alt,))
        c.execute("DELETE FROM transaktionen WHERE konto=?", (alt,))
        c.execute("DELETE FROM anfangsbestaende WHERE konto=?", (alt,))
    
    # --- 3. NEUE STRUKTUR ---
    fixe_konten = [
        ("Lohnkonto", "Lohnkonto"), ("Neon", "Lohnkonto"),
        ("Sparkonto", "Vermögen"), ("Neon Invest", "Vermögen"), ("Yuh Invest", "Vermögen"),
        ("Baloise 3a", "Vermögen"), ("Helvetia 3a", "Vermögen"), ("SwissLife 3a", "Vermögen"), 
        ("Kleider", "Nebenkosten"), ("Geschenke", "Nebenkosten"), 
        ("Ferien", "Nebenkosten"), ("Auto", "Nebenkosten"), 
        ("Steuern", "Nebenkosten"), ("Arzt", "Nebenkosten"), 
        ("Nebenkosten Wohnung", "Nebenkosten")
    ]
    
    for name, typ in fixe_konten:
        c.execute("INSERT OR IGNORE INTO konten (name, typ) VALUES (?,?)", (name, typ))
    
    conn.commit()
    conn.close()

def get_anfangsbestand(konto_name, target_monat):
    conn = get_connection()
    c = conn.cursor()
    res = c.execute("SELECT betrag FROM anfangsbestaende WHERE konto=? AND monat=?", (konto_name, target_monat)).fetchone()
    if res:
        conn.close()
        return res[0]
    
    typ_res = c.execute("SELECT typ FROM konten WHERE name=?", (konto_name,)).fetchone()
    ist_vermoegen = (typ_res and typ_res[0] == 'Vermögen')
    
    jahr, monat = map(int, target_monat.split('-'))
    aktueller_bestand = 0.0
    for m in range(1, (jahr - 2026) * 12 + monat):
        m_jahr = 2026 + (m - 1) // 12
        m_monat = ((m - 1) % 12) + 1
        monat_str = f"{m_jahr}-{m_monat:02}"
        query = "SELECT SUM(betrag) FROM transaktionen WHERE konto=? AND monat=? AND status='bestätigt'" if ist_vermoegen else "SELECT SUM(betrag) FROM transaktionen WHERE konto=? AND monat=?"
        txn_sum = c.execute(query, (konto_name, monat_str)).fetchone()[0] or 0
        aktueller_bestand += txn_sum
    conn.close()
    return aktueller_bestand

def set_anfangsbestand(konto_name, monat, betrag):
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO anfangsbestaende (konto, monat, betrag) VALUES (?,?,?)", (konto_name, monat, betrag))
    conn.commit()
    conn.close()
import sqlite3

def get_connection():
    return sqlite3.connect('finanzen.db', check_same_thread=False)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # --- 1. TABELLEN ERSTELLEN ---
    c.execute('''CREATE TABLE IF NOT EXISTS konten (name TEXT PRIMARY KEY, typ TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS anfangsbestaende (id INTEGER PRIMARY KEY, konto TEXT, monat TEXT, betrag REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transaktionen (id INTEGER PRIMARY KEY, konto TEXT, typ TEXT, betrag REAL, beschreibung TEXT, datum TEXT, monat TEXT, status TEXT, modus TEXT, link_id TEXT)''')
    
    # NEU: Tabelle für die Budget-Planung
    c.execute('''CREATE TABLE IF NOT EXISTS budget_nebenkosten (id INTEGER PRIMARY KEY AUTOINCREMENT, beschreibung TEXT, betrag_jaehrlich REAL, konto TEXT)''')
    
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
    if res is not None:
        conn.close()
        return res[0]
    
    typ_res = c.execute("SELECT typ FROM konten WHERE name=?", (konto_name,)).fetchone()
    ist_vermoegen = (typ_res and typ_res[0] == 'Vermögen')
    
    if ist_vermoegen:
        query = "SELECT SUM(betrag) FROM transaktionen WHERE konto=? AND monat < ? AND status='bestätigt'"
    else:
        query = "SELECT SUM(betrag) FROM transaktionen WHERE konto=? AND monat < ?"
        
    txn_sum = c.execute(query, (konto_name, target_monat)).fetchone()[0] or 0.0
    conn.close()
    return txn_sum

def set_anfangsbestand(konto_name, monat, betrag):
    conn = get_connection()
    c = conn.cursor()
    
    existing = c.execute("SELECT id FROM anfangsbestaende WHERE konto=? AND monat=?", (konto_name, monat)).fetchone()
    
    if existing:
        c.execute("UPDATE anfangsbestaende SET betrag=? WHERE id=?", (betrag, existing[0]))
    else:
        c.execute("INSERT INTO anfangsbestaende (konto, monat, betrag) VALUES (?,?,?)", (konto_name, monat, betrag))
        
    conn.commit()
    conn.close()
# app.py
import streamlit as st
from datetime import datetime
import os

# Datenbank sofort initialisieren
from db_manager import init_db, get_connection
init_db()

from config import MONATE_MAP
from theme import apply_banking_styles

# Die Ansichten importieren
from views.dashboard import show_dashboard
from views.lohnkonten import show_lohnkonten
from views.vermoegen import show_vermoegen
from views.konten_verwaltung import show_konten_verwaltung
from views.nebenkosten import show_nebenkosten

# --- 1. SETUP & SESSION STATE ---
st.set_page_config(layout="wide", page_title="Finanz-Cockpit")

if "auth" not in st.session_state: 
    st.session_state["auth"] = False
if 'view' not in st.session_state: 
    st.session_state.view = 'dashboard'

# --- 2. LOGIN GATE ---
if not st.session_state["auth"]:
    # Design zentriert, ohne Logo
    st.markdown("""
        <style>
            header {visibility: hidden;}
            .main .block-container {
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                height: 70vh;
            }
        </style>
    """, unsafe_allow_html=True)
    
    st.title("Login")
    user = st.text_input("Benutzername")
    password = st.text_input("Passwort", type="password")
    
    if st.button("Anmelden", use_container_width=True):
        if user == "Administrator" and password == "Finanzen2026":
            st.session_state["auth"] = True
            st.rerun()
        else:
            st.error("Benutzername oder Passwort falsch.")
    st.stop() 

# --- 3. HAUPTPROGRAMM (Nur sichtbar, wenn auth == True) ---
apply_banking_styles()

def reset_ansicht():
    st.session_state.view = 'dashboard'

# Dynamisches Laden der Konten
def get_konten_von_db(typ):
    conn = get_connection()
    try:
        konten = [row[0] for row in conn.execute("SELECT name FROM konten WHERE typ=?", (typ,)).fetchall()]
    except:
        konten = []
    conn.close()
    return konten

# --- SIDEBAR ---
with st.sidebar:
    st.title("🧭 Finanz-Cockpit")
    st.markdown("#### Navigation")
    
    nav_options = {
        "📊 Dashboard": "Dashboard",
        "💳 Lohnkonten": "Lohnkonten",
        "📈 Vermögen": "Vermögen",
        "🛒 Nebenkosten": "Nebenkosten",
        "⚙️ Konten-Verwaltung": "Konten-Verwaltung"
    }

    auswahl_anzeige = st.radio(
        "Bereich wählen", 
        list(nav_options.keys()),
        label_visibility="collapsed",
        on_change=reset_ansicht
    )
    bereich = nav_options[auswahl_anzeige]

    st.divider()
    
    # 1. Zeitraum Darstellung
    st.markdown("#### 📅 Zeitraum")
    col1, col2 = st.columns(2)
    akt_monat_index = datetime.now().month - 1
    with col1:
        ausgewaehlter_monat_name = st.selectbox("Monat", list(MONATE_MAP.keys()), index=akt_monat_index, label_visibility="collapsed")
    with col2:
        ausgewaehltes_jahr = st.selectbox("Jahr", [2024, 2025, 2026, 2027], index=2, label_visibility="collapsed")

    globaler_monat = f"{ausgewaehltes_jahr}-{MONATE_MAP[ausgewaehlter_monat_name]}"

    st.divider()
    
    # 2. Daten-Management (Buttons nun darunter)
    st.markdown("#### ☁️ Daten-Management")
    
    # Backup Button
    db_file = "finanzen.db"
    if os.path.exists(db_file):
        with open(db_file, "rb") as f:
            st.download_button(
                label="💾 Backup (Lokal)",
                data=f,
                file_name="finanzen_backup.db",
                mime="application/x-sqlite3",
                use_container_width=True
            )
    
    # Sync Button (identisch zu den anderen Buttons formatiert)
    if st.button("🔄 Sync zu Google Drive", use_container_width=True):
        st.warning("Sync-Funktion muss noch mit deinem Drive-Script verknüpft werden.")

    st.divider()
    
    # --- ABMELDEN BUTTON ---
    if st.button("🔴 Abmelden", use_container_width=True):
        st.session_state["auth"] = False
        st.rerun()

# --- ROUTING ---
if bereich == "Dashboard":
    show_dashboard(ausgewaehlter_monat_name, ausgewaehltes_jahr, globaler_monat)
elif bereich == "Lohnkonten":
    show_lohnkonten(ausgewaehlter_monat_name, ausgewaehltes_jahr, globaler_monat)
elif bereich == "Vermögen":
    show_vermoegen(ausgewaehlter_monat_name, ausgewaehltes_jahr, globaler_monat)
elif bereich == "Nebenkosten":
    show_nebenkosten(ausgewaehlter_monat_name, ausgewaehltes_jahr, globaler_monat)
elif bereich == "Konten-Verwaltung":
    show_konten_verwaltung()
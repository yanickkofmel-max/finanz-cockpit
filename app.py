import streamlit as st
from datetime import datetime
import os

# --- 0. BASIS-KONFIGURATION (Muss zwingend als allererstes stehen!) ---
st.set_page_config(layout="wide", page_title="Finanz-Cockpit")

# --- 1. DATENBANK-SYNC BEIM START (NUR EINMALIG!) ---
from utils.drive_sync import download_db, upload_db

# Verwende den Session State, damit der Download NUR BEIM ERSTEN START läuft
if "db_initial_loaded" not in st.session_state:
    with st.spinner("Lade aktuellsten Stand aus Google Drive..."):
        versuch = download_db()
        if versuch == False:
            st.error("ACHTUNG: Datenbank konnte nicht von Google Drive geladen werden!")
        else:
            st.session_state["db_initial_loaded"] = True

# Datenbank initialisieren (Nutzt ab jetzt die lokale Datei)
from db_manager import init_db, get_connection
init_db()

# Konfiguration und Design-Funktionen importieren
from config import MONATE_MAP
from theme import apply_banking_styles

# Die Ansichten importieren
from views.dashboard import show_dashboard
from views.lohnkonten import show_lohnkonten
from views.vermoegen import show_vermoegen
from views.konten_verwaltung import show_konten_verwaltung
from views.nebenkosten import show_nebenkosten

# --- 2. SESSION STATES INITIALISIEREN ---
if "auth" not in st.session_state: 
    st.session_state["auth"] = False
if 'view' not in st.session_state: 
    st.session_state.view = 'dashboard'

# --- 3. MODERNES LOGIN GATE (Design übernommen & angepasst, ohne Logo) ---
if not st.session_state["auth"]:
    st.markdown("""
        <style>
            /* 1. FLEXIBLER HINTERGRUND (Wechselt automatisch bei Light/Dark Mode) */
            .stApp {
                background-color: var(--background-color);
            }
            
            header {visibility: hidden;}
            
            .main .block-container {
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                height: 100vh;
                padding-top: 0rem !important;
            }

            .login-section {
                width: 320px !important;
                text-align: center;
            }

            /* 2. TEXTFARBEN ANPASSEN */
            .brand-title {
                font-family: 'Inter', sans-serif;
                color: var(--text-color);
                font-size: 42px;
                font-weight: 800;
                margin-top: 15px;
                letter-spacing: -1px;
            }

            .brand-subtitle {
                color: #58a6ff; 
                font-size: 18px;
                font-weight: 400;
                margin-bottom: 40px;
                letter-spacing: 2px;
                text-transform: uppercase;
            }

            /* 3. MINIMALISTISCHE EINGABEFELDER (Unterstrich statt Rahmen) */
            div[data-baseweb="input"] {
                background-color: transparent !important;
                border: none !important;
                border-bottom: 2px solid var(--secondary-background-color) !important;
                border-radius: 0px !important;
                padding: 0px !important;
            }
            
            div[data-baseweb="input"]:focus-within {
                border-bottom: 2px solid #58a6ff !important;
            }
            
            input {
                color: var(--text-color) !important;
                font-size: 18px !important;
                text-align: left !important;
                padding-left: 5px !important;
            }

            input::placeholder {
                color: var(--text-color);
                opacity: 0.5;
            }

            button[aria-label="Show password"] svg {
                fill: var(--text-color) !important;
            }

            /* GRÜNER ANMELDE-BUTTON */
            button[kind="primaryFormSubmit"] {
                background-color: #238636 !important;
                border: none !important;
                border-radius: 6px !important;
                color: white !important;
                height: 45px !important;
                width: 100% !important;
                margin-top: 40px !important;
                font-weight: 600 !important;
            }
            
            div[data-testid="stWidgetLabel"] {
                display: none !important;
            }

            .stForm {
                border: none !important;
                padding: 0 !important;
            }
        </style>
    """, unsafe_allow_html=True)

    # Physikalische Zentrierung über drei Spalten
    _, center_col, _ = st.columns([1.5, 1, 1.5])

    with center_col:
        st.markdown('<div class="login-section">', unsafe_allow_html=True)
        st.markdown('<div class="brand-title">FINANZ</div>', unsafe_allow_html=True)
        st.markdown('<div class="brand-subtitle">Cockpit</div>', unsafe_allow_html=True)
        
        with st.form("login_gate", border=False):
            user = st.text_input("Nutzer", placeholder="Benutzername", label_visibility="collapsed")
            password = st.text_input("Pass", type="password", placeholder="Passwort", label_visibility="collapsed")
            
            if st.form_submit_button("Anmelden"):
                if user == "Administrator" and password == "Finanzen2026":
                    st.session_state["auth"] = True
                    st.rerun()
                else:
                    st.error("Zugriff verweigert")
        
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop() 

# --- 4. HAUPTPROGRAMM (Nur sichtbar, wenn auth == True) ---
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
    
    # 2. Daten-Management
    st.markdown("#### ☁️ Daten-Management")
    
    # Backup Button (Lokal)
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
    
    # Sync Button
    if st.button("🔄 Sync zu Google Drive", use_container_width=True):
        with st.spinner("Synchronisiere mit Google Drive..."):
            erfolg = upload_db()
            if erfolg:
                st.success("Erfolgreich zu Google Drive hochgeladen!")
            else:
                st.error("Fehler beim Upload zu Google Drive.")

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
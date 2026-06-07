# components.py
import streamlit as st
import pandas as pd
import base64
from db_manager import get_connection, get_anfangsbestand

def get_image_base64(path):
    try:
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
            ext = path.split(".")[-1].lower()
            mime = "jpeg" if ext in ["jpg", "jpeg"] else ext
            return f"data:image/{mime};base64,{encoded}"
    except:
        return ""

def get_logo_fuer_konto(konto_name):
    LOGOS = {
        "Lohnkonto": get_image_base64("Raiffeisenbank.webp"),
        "Neon": get_image_base64("neon.png"),
        "Sparkonto": get_image_base64("Raiffeisenbank.webp"),
        "Neon Invest": get_image_base64("neon.png"),
        "Yuh Invest": get_image_base64("yuh.png"),
        "Baloise 3a": get_image_base64("baloise_bank_soba.png"),  # <-- NEU: Name angepasst
        "Helvetia 3a": get_image_base64("Helvetia.png"),          # <-- NEU: Name angepasst
        "SwissLife 3a": get_image_base64("Swiss_Life.png")        # <-- NEU: Name angepasst
    }
    return LOGOS.get(konto_name, get_image_base64("Raiffeisen.png"))

# --- ZENTRALE LOGIK FÜR KUMULIERTE SALDI ---
def get_saldo_bis_monat(konto_name, monat_str):
    """Berechnet den Saldo für Vermögen & Nebenkosten exakt bis zum Stichtag."""
    conn = get_connection()
    # 1. Basis-Startwert holen
    start_row = conn.execute("SELECT monat, betrag FROM anfangsbestaende WHERE konto=? ORDER BY monat ASC LIMIT 1", (konto_name,)).fetchone()
    base_monat = start_row[0] if start_row else '2000-01'
    base_betrag = start_row[1] if start_row else 0.0
    
    # 2. GEPLANT: Summe ALLER Transaktionen (geplant + verbucht)
    df_geo = pd.read_sql(f"SELECT SUM(betrag) as total FROM transaktionen WHERE konto='{konto_name}' AND monat >= '{base_monat}' AND monat <= '{monat_str}'", conn)
    
    # 3. AKTUELL: Summe NUR DER VERBUCHTEN Transaktionen
    df_akt = pd.read_sql(f"SELECT SUM(betrag) as total FROM transaktionen WHERE konto='{konto_name}' AND monat >= '{base_monat}' AND monat <= '{monat_str}' AND status='bestätigt'", conn)
    conn.close()
    
    s_geo = base_betrag + (df_geo['total'].iloc[0] or 0.0)
    s_akt = base_betrag + (df_akt['total'].iloc[0] or 0.0)
    return s_geo, s_akt

def render_bank_kachel(konto_name, monat_str, show_button=True):
    conn = get_connection()
    typ_res = conn.execute("SELECT typ FROM konten WHERE name=?", (konto_name,)).fetchone()
    k_typ = typ_res[0] if typ_res else ""
    conn.close()
    
    # Weiche je nach Kontotyp
    if k_typ in ["Vermögen", "Nebenkosten"]:
        # Kumulative Logik anwenden
        s_geo, s_akt = get_saldo_bis_monat(konto_name, monat_str)
    else:
        # Alte Logik für Lohnkonten (mit isoliertem Monat)
        conn = get_connection()
        df_geo = pd.read_sql(f"SELECT SUM(betrag) as total FROM transaktionen WHERE konto='{konto_name}' AND monat='{monat_str}'", conn)
        df_akt = pd.read_sql(f"SELECT SUM(betrag) as total FROM transaktionen WHERE konto='{konto_name}' AND monat='{monat_str}' AND status='bestätigt'", conn)
        conn.close()
        
        anfangsbestand = get_anfangsbestand(konto_name, monat_str)
        s_geo = (df_geo['total'].iloc[0] or 0.0) + anfangsbestand
        s_akt = (df_akt['total'].iloc[0] or 0.0) + anfangsbestand

    logo_b64 = get_logo_fuer_konto(konto_name)

    # 1. Kachel MIT den neuen Styles rendern
    st.markdown(f"""
        <div class="bank-tile">
            <div class="header-box">
                <div class="logo-wrapper">
                    <img src="{logo_b64}" class="logo-img">
                </div>
                <div class="title-text">{konto_name}</div>
            </div>
            <div class="grid-box">
                <div class="val-col">
                    <div class="label-text">Geplant</div>
                    <div class="val-text">{s_geo:,.2f} CHF</div>
                </div>
                <div class="val-col right">
                    <div class="label-text">Aktuell</div>
                    <div class="val-text">{s_akt:,.2f} CHF</div>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # 2. Der Button, um die Details/Kontoauszüge zu öffnen
    if show_button:
        if st.button("🔍 Details öffnen", key=f"btn_details_{konto_name}", use_container_width=True):
            st.session_state.selected_konto = konto_name
            st.session_state.view = 'lohn_details'
            st.rerun()
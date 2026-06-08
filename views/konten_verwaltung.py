# views/konten_verwaltung.py
import streamlit as st
import pandas as pd
from db_manager import get_connection

# In views/konten_verwaltung.py ganz oben anpassen:
GESCHÜTZTE_KONTEN = [
    "Lohnkonto", "Neon",
    "Sparkonto", "Neon Invest", "Yuh Invest", "Yuh USD", "Baloise 3a", "Helvetia 3a", "SwissLife 3a",
    "Kleider", "Geschenke", "Ferien", "Auto", "Steuern", "Arzt", "Nebenkosten Wohnung"
]

def get_alle_konten_sortiert():
    """Holt alle Konten aus der DB und sortiert sie logisch nach Typ."""
    conn = get_connection()
    df = pd.read_sql("SELECT name, typ FROM konten", conn)
    conn.close()
    
    if df.empty:
        return df
        
    # Reihenfolge-Mapping für die Sortierung definieren
    typ_order = {"Lohnkonto": 1, "Vermögen": 2, "Nebenkosten": 3}
    df['sort_order'] = df['typ'].map(typ_order).fillna(4)
    
    # Erst nach Typ-Reihenfolge sortieren, danach alphabetisch nach Namen
    df = df.sort_values(by=['sort_order', 'name']).drop(columns=['sort_order'])
    return df

def konto_hinzufuegen(name, typ):
    if not name.strip():
        st.error("Bitte gib einen gültigen Kontonamen ein.")
        return
    conn = get_connection()
    try:
        conn.execute("INSERT INTO konten (name, typ) VALUES (?,?)", (name.strip(), typ))
        conn.commit()
        st.success(f"Konto '{name}' erfolgreich als '{typ}' hinzugefügt!")
    except:
        st.error("Dieses Konto existiert bereits!")
    finally:
        conn.close()

def konto_loeschen(name):
    conn = get_connection()
    # Löscht das Konto
    conn.execute("DELETE FROM konten WHERE name=?", (name,))
    # Optionale Sicherheit: Löscht auch verwaiste Transaktionen dieses Kontos
    conn.execute("DELETE FROM transaktionen WHERE konto=?", (name,))
    conn.execute("DELETE FROM anfangsbestaende WHERE konto=?", (name,))
    conn.commit()
    conn.close()
    st.success(f"Konto '{name}' wurde erfolgreich gelöscht.")
    st.rerun()

def show_konten_verwaltung():
    st.title("⚙️ Konten-Verwaltung")
    st.caption("Verwalte hier deine Kontoverbindungen, Vermögenswerte und Nebenkostentöpfe.")
    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
    
    # --- FORMULAR: NEUES KONTO ERSTELLEN ---
    with st.expander("➕ Neues Konto / Spartopf anlegen", expanded=False):
        with st.form("form_add_konto"):
            c1, c2 = st.columns(2)
            neu_name = c1.text_input("Name des Kontos / Topfes", placeholder="z.B. Swisscanto, Reisekasse...")
            neu_typ = c2.selectbox("Kategorie / Typ", ["Lohnkonto", "Vermögen", "Nebenkosten"])
            
            if st.form_submit_button("🔒 Konto registrieren"):
                konto_hinzufuegen(neu_name, neu_typ)
                st.rerun()
                
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    st.subheader("📋 Bestehende Konten & Strukturen")
    
    df_konten = get_alle_konten_sortiert()
    
    if df_konten.empty:
        st.info("Es sind aktuell keine Konten in der Datenbank registriert.")
        return
        
    # --- TABELLARISCHES LISTENDESIGN ---
    # Header-Zeile rendern
    st.markdown("""
        <div style='display: flex; padding: 0px 8px 10px 8px; color: #6C727F; font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #262730; margin-bottom: 8px;'>
            <div style='flex: 3;'>Konto / Bezeichnung</div>
            <div style='flex: 2;'>Typ / Kategorie</div>
            <div style='flex: 1.5; text-align: center;'>Aktion</div>
        </div>
    """, unsafe_allow_html=True)
    
    # Einzelne Konten-Zeilen rendern
    for _, row in df_konten.iterrows():
        k_name = row['name']
        k_typ = row['typ']
        is_protected = k_name in GESCHÜTZTE_KONTEN
        
        col_name, col_typ, col_action = st.columns([3, 2, 1.5])
        
        with col_name:
            # Ein dezentes Icon je nach Typ für die visuelle Trennung
            icon = "💳" if k_typ == "Lohnkonto" else ("📈" if k_typ == "Vermögen" else "🛒")
            st.markdown(f"<div style='padding-top: 5px; font-weight: 500;'>{icon} {k_name}</div>", unsafe_allow_html=True)
            
        with col_typ:
            # Badge-Design für den Typ
            bg_color = "rgba(76, 110, 245, 0.15)" if k_typ == "Lohnkonto" else ("rgba(46, 204, 113, 0.15)" if k_typ == "Vermögen" else "rgba(230, 126, 34, 0.15)")
            text_color = "#4C6EF5" if k_typ == "Lohnkonto" else ("#2ECC71" if k_typ == "Vermögen" else "#E67E22")
            st.markdown(f"""
                <div style='background-color: {bg_color}; color: {text_color}; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 600; display: inline-block; margin-top: 3px;'>
                    {k_typ}
                </div>
            """, unsafe_allow_html=True)
            
        with col_action:
            if is_protected:
                # Button ist deaktiviert und trägt einen Hinweis-Text
                st.button("🔒 System", key=f"del_{k_name}", disabled=True, use_container_width=True, help="Systemrelevante Konten können nicht gelöscht werden.")
            else:
                # Custom-Konten des Users können gelöscht werden
                if st.button("🗑 Löschen", key=f"del_{k_name}", use_container_width=True):
                    konto_loeschen(k_name)
                    
        # Trennlinie
        st.markdown("<div style='border-bottom: 1px solid #1C1E24; margin-top: 4px; margin-bottom: 4px;'></div>", unsafe_allow_html=True)
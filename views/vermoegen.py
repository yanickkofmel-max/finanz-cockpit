import streamlit as st
import pandas as pd
import time
from datetime import datetime
from db_manager import get_connection, get_anfangsbestand
from components import render_bank_kachel, get_saldo_bis_monat
from theme import render_transaction_row, render_table_header
from utils.drive_sync import upload_db 
from utils.pdf_generator import generate_kontoauszug_pdf

def get_konten_von_db(typ=None):
    conn = get_connection()
    if typ:
        konten = [row[0] for row in conn.execute("SELECT name FROM konten WHERE typ=?", (typ,)).fetchall()]
    else:
        konten = [row[0] for row in conn.execute("SELECT name FROM konten").fetchall()]
    conn.close()
    return konten

def handle_confirm(id, status):
    conn = get_connection()
    new_status = "bestätigt" if status == "geplant" else "geplant"
    df = pd.read_sql(f"SELECT link_id FROM transaktionen WHERE id={id}", conn)
    link_id = df['link_id'].iloc[0] if not df.empty else None
    
    if link_id and str(link_id).strip() != "":
        conn.execute("UPDATE transaktionen SET status=? WHERE link_id=?", (new_status, link_id))
    else:
        conn.execute("UPDATE transaktionen SET status=? WHERE id=?", (new_status, id))
    conn.commit()
    conn.close()
    upload_db() 
    st.rerun()

def handle_delete(id):
    conn = get_connection()
    df = pd.read_sql(f"SELECT link_id FROM transaktionen WHERE id={id}", conn)
    link_id = df['link_id'].iloc[0] if not df.empty else None
    
    if link_id and str(link_id).strip() != "":
        conn.execute("DELETE FROM transaktionen WHERE link_id=?", (link_id,))
    else:
        conn.execute("DELETE FROM transaktionen WHERE id=?", (id,))
    conn.commit()
    conn.close()
    upload_db() 
    st.rerun()

def get_startbestand_bis_vormonat(konto_name, aktueller_monat_str):
    conn = get_connection()
    if aktueller_monat_str.endswith("-ALL"):
        jahr = aktueller_monat_str.split("-")[0]
        vergleichs_monat = f"{jahr}-01"
    else:
        vergleichs_monat = aktueller_monat_str

    start_row = conn.execute("SELECT monat, betrag FROM anfangsbestaende WHERE konto=? ORDER BY monat ASC LIMIT 1", (konto_name,)).fetchone()
    base_monat = start_row[0] if start_row else '2000-01'
    base_betrag = start_row[1] if start_row else 0.0
    
    df_vormonate = pd.read_sql(
        f"SELECT SUM(betrag) as total FROM transaktionen "
        f"WHERE konto='{konto_name}' AND monat >= '{base_monat}' AND monat < '{vergleichs_monat}' AND status='bestätigt'", 
        conn
    )
    conn.close()
    return base_betrag + (df_vormonate['total'].iloc[0] or 0.0)

def show_vermoegen(ausgewaehlter_monat_name, ausgewaehltes_jahr, globaler_monat):
    VERMOEGEN_KONTEN = get_konten_von_db("Vermögen")
    ALLE_KONTEN = get_konten_von_db()

    zeitraum_text = f"Jahr {ausgewaehltes_jahr}" if globaler_monat.endswith("-ALL") else f"{ausgewaehlter_monat_name} {ausgewaehltes_jahr}"

    if st.session_state.view == 'dashboard':
        st.title("📈 Vermögen Übersicht")
        st.caption(f"Zeitraum: {zeitraum_text}")
        st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
        
        for i in range(0, len(VERMOEGEN_KONTEN), 3):
            chunk = VERMOEGEN_KONTEN[i:i+3]
            spalten = st.columns(3)
            for j, k_name in enumerate(chunk):
                with spalten[j]:
                    render_bank_kachel(k_name, globaler_monat, show_button=True)

    elif st.session_state.view == 'lohn_details':
        konto_name = st.session_state.selected_konto
        if konto_name not in VERMOEGEN_KONTEN: return
            
        st.title(f"Cockpit: {konto_name}")
        st.caption(f"📅 Filter aktiv: {zeitraum_text}")
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

        if globaler_monat.endswith("-ALL"):
            st.info("💡 Um neue Buchungen zu erfassen, wähle bitte links in der Sidebar einen spezifischen Monat aus.")
        else:
            with st.expander("➕ Neue Transaktion erfassen"):
                typ = st.selectbox("Typ", ["Gutschrift", "Belastung", "Übertrag (Umbuchung)"])
                with st.form("add_txn_vermoegen"):
                    c1, c2 = st.columns(2)
                    betrag = c1.number_input("Betrag", min_value=0.0)
                    txn_datum = c1.date_input("Buchungsdatum", datetime.now())
                    desc = c2.text_input("Beschreibung / Zweck")
                    modus = c2.radio("Modus", ["Einmalig", "Dauerauftrag (bis Jahresende)"])
                    
                    von_konto, nach_konto = None, None
                    if typ == "Übertrag (Umbuchung)":
                        st.markdown("---")
                        c3, c4 = st.columns(2)
                        von_konto = c3.selectbox("Von Konto", ALLE_KONTEN, index=ALLE_KONTEN.index(konto_name))
                        nach_konto = c4.selectbox("Nach Konto", [k for k in ALLE_KONTEN if k != von_konto])

                    if st.form_submit_button("Buchung speichern"):
                        datum_str = txn_datum.strftime("%Y-%m-%d")
                        txn_jahr = txn_datum.year
                        txn_monat_num = txn_datum.month
                        
                        if modus == "Dauerauftrag (bis Jahresende)":
                            ziel_monate = [f"{txn_jahr}-{m_num:02}" for m_num in range(txn_monat_num, 13)]
                        else:
                            ziel_monate = [f"{txn_jahr}-{txn_monat_num:02}"]
                        
                        conn = get_connection()
                        for z_monat in ziel_monate:
                            if typ == "Übertrag (Umbuchung)":
                                link = f"TR-{z_monat}-{int(time.time()*1000)}"
                                conn.execute("INSERT INTO transaktionen (konto, typ, betrag, beschreibung, datum, monat, status, modus, link_id) VALUES (?,?,?,?,?,?,?,?,?)",
                                             (von_konto, "Belastung", -betrag, f"Übertrag an {nach_konto}: {desc}", datum_str, z_monat, "geplant", modus, link))
                                conn.execute("INSERT INTO transaktionen (konto, typ, betrag, beschreibung, datum, monat, status, modus, link_id) VALUES (?,?,?,?,?,?,?,?,?)",
                                             (nach_konto, "Gutschrift", betrag, f"Übertrag von {von_konto}: {desc}", datum_str, z_monat, "geplant", modus, link))
                            else:
                                val = -betrag if typ == "Belastung" else betrag
                                conn.execute("INSERT INTO transaktionen (konto, typ, betrag, beschreibung, datum, monat, status, modus, link_id) VALUES (?,?,?,?,?,?,?,?,?)",
                                             (konto_name, typ, val, desc, datum_str, z_monat, "geplant", modus, ""))
                        conn.commit()
                        conn.close()
                        upload_db() 
                        st.rerun()

        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        st.subheader(f"Buchungen im {zeitraum_text}")
        st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
        
        conn = get_connection()
        if globaler_monat.endswith("-ALL"):
            df = pd.read_sql(f"SELECT * FROM transaktionen WHERE konto='{konto_name}' AND monat LIKE '{ausgewaehltes_jahr}-%' ORDER BY datum DESC", conn)
        else:
            df = pd.read_sql(f"SELECT * FROM transaktionen WHERE konto='{konto_name}' AND monat='{globaler_monat}' ORDER BY datum DESC", conn)
        
        start_row = conn.execute("SELECT monat, betrag FROM anfangsbestaende WHERE konto=? ORDER BY monat ASC LIMIT 1", (konto_name,)).fetchone()
        base_monat = start_row[0] if start_row else '2000-01'
        base_betrag = start_row[1] if start_row else 0.0
        
        if globaler_monat.endswith("-ALL"):
            df_all = pd.read_sql(f"SELECT betrag, status FROM transaktionen WHERE konto='{konto_name}' AND monat >= '{base_monat}' AND monat LIKE '{ausgewaehltes_jahr}-%'", conn)
        else:
            df_all = pd.read_sql(f"SELECT betrag, status FROM transaktionen WHERE konto='{konto_name}' AND monat >= '{base_monat}' AND monat <= '{globaler_monat}'", conn)
        conn.close()
        
        startbestand_anzeige = get_startbestand_bis_vormonat(konto_name, globaler_monat)
        
        if not df_all.empty:
            summe_aktuell = base_betrag + df_all[df_all['status'] == 'bestätigt']['betrag'].sum()
            summe_geplant = base_betrag + df_all['betrag'].sum()
        else:
            summe_aktuell = base_betrag
            summe_geplant = base_betrag

        if not df.empty:
            render_table_header()
            for _, row in df.iterrows(): 
                render_transaction_row(row, handle_confirm, handle_delete)
        else:
            st.info("In diesem Zeitraum sind für dieses Konto keine direkten Buchungen vorhanden.")
            
        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        st.divider()
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Startbestand", f"{startbestand_anzeige:,.2f} CHF")
        col2.metric("Geplanter Endsaldo", f"{summe_geplant:,.2f} CHF")
        col3.metric("Aktueller Endsaldo", f"{summe_aktuell:,.2f} CHF")
        
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        
        # --- PDF & ZURÜCK BUTTONS ---
        btn_col1, btn_col2 = st.columns([1, 5], vertical_alignment="center")
        with btn_col1:
            if st.button("← Zurück", use_container_width=True):
                st.session_state.view = 'dashboard'
                st.rerun()
        with btn_col2:
            pdf_data = generate_kontoauszug_pdf(
                konto_name=konto_name,
                zeitraum_text=zeitraum_text,
                df_transactions=df,
                startbestand=startbestand_anzeige,
                endsaldo_geplant=summe_geplant,
                endsaldo_aktuell=summe_aktuell
            )
            
            st.download_button(
                label="📄 Kontoauszug als PDF herunterladen",
                data=pdf_data,
                file_name=f"Kontoauszug_{konto_name.replace(' ', '_')}_{zeitraum_text.replace(' ', '_')}.pdf",
                mime="application/pdf"
            )
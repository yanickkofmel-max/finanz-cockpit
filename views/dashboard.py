# views/dashboard.py
import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
from db_manager import get_connection, get_anfangsbestand
from components import render_bank_kachel, get_saldo_bis_monat
from theme import render_transaction_row, render_table_header

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
    st.rerun()

def get_startbestand_bis_vormonat(konto_name, aktueller_monat_str):
    conn = get_connection()
    start_row = conn.execute("SELECT monat, betrag FROM anfangsbestaende WHERE konto=? ORDER BY monat ASC LIMIT 1", (konto_name,)).fetchone()
    base_monat = start_row[0] if start_row else '2000-01'
    base_betrag = start_row[1] if start_row else 0.0
    
    df_vormonate = pd.read_sql(
        f"SELECT SUM(betrag) as total FROM transaktionen "
        f"WHERE konto='{konto_name}' AND monat >= '{base_monat}' AND monat < '{aktueller_monat_str}' AND status='bestätigt'", 
        conn
    )
    conn.close()
    return base_betrag + (df_vormonate['total'].iloc[0] or 0.0)

def show_dashboard(ausgewaehlter_monat_name, ausgewaehltes_jahr, globaler_monat):
    # --- ANSICHT 1: DAS HAUPT-DASHBOARD ---
    if st.session_state.view == 'dashboard':
        st.title("Dashboard")
        st.caption(f"📊 Finanz-Gesamtübersicht für {ausgewaehlter_monat_name} {ausgewaehltes_jahr}")
        st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
        
        lohn_konten = get_konten_von_db("Lohnkonto")
        vermoegen_konten = get_konten_von_db("Vermögen")
        
        if lohn_konten:
            st.subheader("💳 Lohnkonten")
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            for i in range(0, len(lohn_konten), 3):
                chunk = lohn_konten[i:i+3]
                spalten = st.columns(3)
                for j, k_name in enumerate(chunk):
                    with spalten[j]:
                        render_bank_kachel(k_name, globaler_monat, show_button=True)
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)

        if vermoegen_konten:
            st.subheader("📈 Vermögen")
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            for i in range(0, len(vermoegen_konten), 3):
                chunk = vermoegen_konten[i:i+3]
                spalten = st.columns(3)
                for j, k_name in enumerate(chunk):
                    with spalten[j]:
                        render_bank_kachel(k_name, globaler_monat, show_button=True)
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
            
            chart_data = []
            for k_name in vermoegen_konten:
                s_geo, s_akt = get_saldo_bis_monat(k_name, globaler_monat)
                if s_akt > 0:
                    chart_data.append({"Konto": k_name, "Saldo": s_akt})
            
            if chart_data:
                df_chart = pd.DataFrame(chart_data)
                with st.container(border=True):
                    st.markdown("#### 🍩 Vermögensaufteilung (Effektiv verbucht)")
                    st.caption("Visuelle Übersicht über die prozentuale Verteilung deines effektiv bestätigten Gesamtvermögens bis zum gewählten Monat.")
                    st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
                    
                    fig = px.pie(
                        df_chart, values='Saldo', names='Konto', hole=0.4,
                        color_discrete_sequence=px.colors.qualitative.Pastel
                    )
                    fig.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        font_color='#FFFFFF',
                        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
                        margin=dict(t=10, b=10, l=10, r=10)
                    )
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Noch kein positives, effektiv verbuchtes Vermögen für die Diagramm-Anzeige in diesem Monat vorhanden.")

    # --- ANSICHT 2: COCKPIT-DETAILS ---
    elif st.session_state.view == 'lohn_details':
        konto_name = st.session_state.selected_konto
        st.title(f"Cockpit: {konto_name}")
        st.caption(f"📅 Filter aktiv: {ausgewaehlter_monat_name} {ausgewaehltes_jahr}")
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        
        akt_bestand = get_anfangsbestand(konto_name, globaler_monat)
        neuer_bestand = akt_bestand
        
        conn = get_connection()
        typ_res = conn.execute("SELECT typ FROM konten WHERE name=?", (konto_name,)).fetchone()
        k_typ = typ_res[0] if typ_res else ""
        conn.close()
        
        is_lohn = (k_typ == "Lohnkonto")
        
        if is_lohn:
            with st.container(border=True):
                st.markdown("#### 🏦 Kontostand verwalten")
                st.caption("Lege hier den Startsaldo für den ausgewählten Monat fest.")
                col_content, col_spacer = st.columns([3, 5])
                with col_content:
                    neuer_bestand = st.number_input(
                        "Anfangsbestand (CHF)", value=float(akt_bestand), step=100.0, format="%.2f",
                        key=f"anfang_dash_{konto_name}_{globaler_monat}"
                    )
                    st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
                    if st.button("💾 Speichern", key=f"btn_dash_{konto_name}_{globaler_monat}", use_container_width=True):
                        from db_manager import set_anfangsbestand
                        set_anfangsbestand(konto_name, globaler_monat, neuer_bestand)
                        st.success("Gespeichert!")
                        time.sleep(0.5)
                        st.rerun()
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        with st.expander("➕ Neue Transaktion erfassen"):
            typ = st.selectbox("Typ", ["Gutschrift", "Belastung", "Übertrag (Umbuchung)"])
            with st.form("add_txn_dash"):
                c1, c2 = st.columns(2)
                betrag = c1.number_input("Betrag", min_value=0.0)
                txn_datum = c1.date_input("Buchungsdatum", datetime.now())
                desc = c2.text_input("Beschreibung / Zweck")
                modus = c2.radio("Modus", ["Einmalig", "Dauerauftrag (bis Jahresende)"])
                
                alle_konten_list = get_konten_von_db()
                von_konto, nach_konto = None, None
                if typ == "Übertrag (Umbuchung)":
                    st.markdown("---")
                    c3, c4 = st.columns(2)
                    von_konto = c3.selectbox("Von Konto", alle_konten_list, index=alle_konten_list.index(konto_name))
                    nach_konto = c4.selectbox("Nach Konto", [k for k in alle_konten_list if k != von_konto])

                if st.form_submit_button("Buchung speichern"):
                    datum_str = txn_datum.strftime("%Y-%m-%d")
                    
                    # --- DIE KORREKTUR STARTET HIER ---
                    txn_jahr = txn_datum.year
                    txn_monat_num = txn_datum.month
                    
                    if modus == "Dauerauftrag (bis Jahresende)":
                        ziel_monate = [f"{txn_jahr}-{m_num:02}" for m_num in range(txn_monat_num, 13)]
                    else:
                        ziel_monate = [f"{txn_jahr}-{txn_monat_num:02}"]
                    # --- DIE KORREKTUR ENDET HIER ---
                    
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
                    st.rerun()

        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        st.subheader(f"Buchungen im {ausgewaehlter_monat_name}")
        st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
        
        conn = get_connection()
        df = pd.read_sql(f"SELECT * FROM transaktionen WHERE konto='{konto_name}' AND monat='{globaler_monat}' ORDER BY datum DESC", conn)
        conn.close()
        
        if k_typ in ["Vermögen", "Nebenkosten"]:
            startbestand_anzeige = get_startbestand_bis_vormonat(konto_name, globaler_monat)
            summe_monat_geplant = df['betrag'].sum()
            summe_monat_aktuell = df[df['status'] == 'bestätigt']['betrag'].sum()
            
            summe_geplant = startbestand_anzeige + summe_monat_geplant
            summe_aktuell = startbestand_anzeige + summe_monat_aktuell
        else:
            summe_monat_geplant = df['betrag'].sum()
            summe_monat_aktuell = df[df['status'] == 'bestätigt']['betrag'].sum()
            
            startbestand_anzeige = neuer_bestand
            summe_geplant = startbestand_anzeige + summe_monat_geplant
            summe_aktuell = startbestand_anzeige + summe_monat_aktuell

        if not df.empty:
            render_table_header()
            for _, row in df.iterrows(): 
                render_transaction_row(row, handle_confirm, handle_delete)
        else:
            st.info("In diesem Monat sind für dieses Konto keine direkten Buchungen vorhanden.")
            
        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        st.divider()
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Startbestand", f"{startbestand_anzeige:,.2f} CHF")
        col2.metric("Geplanter Endsaldo", f"{summe_geplant:,.2f} CHF")
        col3.metric("Aktueller Endsaldo", f"{summe_aktuell:,.2f} CHF")
        
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        if st.button("← Zurück", key="btn_back_dash"):
            st.session_state.view = 'dashboard'
            st.rerun()
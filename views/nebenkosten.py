import streamlit as st
import pandas as pd
import time
from datetime import datetime
from db_manager import get_connection, get_anfangsbestand
# ---> WICHTIG: Hier ist format_num nun mit dabei <---
from components import render_bank_kachel, get_saldo_bis_monat, format_num
from theme import render_transaction_row, render_table_header
from utils.drive_sync import upload_db 
from utils.pdf_generator import generate_kontoauszug_pdf
from utils.market_data import get_exchange_rate

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

def show_nebenkosten(ausgewaehlter_monat_name, ausgewaehltes_jahr, globaler_monat):
    NEBENKOSTEN_KONTEN = get_konten_von_db("Nebenkosten")
    ALLE_KONTEN = get_konten_von_db()

    if st.session_state.view == 'dashboard':
        st.title("🛒 Nebenkosten Übersicht")
        zeitraum_label = f"Jahr {ausgewaehltes_jahr}" if globaler_monat.endswith("-ALL") else f"{ausgewaehlter_monat_name} {ausgewaehltes_jahr}"
        st.caption(f"Zeitraum: {zeitraum_label}")
        st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
        
        for i in range(0, len(NEBENKOSTEN_KONTEN), 3):
            chunk = NEBENKOSTEN_KONTEN[i:i+3]
            spalten = st.columns(3)
            for j, k_name in enumerate(chunk):
                with spalten[j]:
                    render_bank_kachel(k_name, globaler_monat, show_button=True)

        st.markdown("<div style='height: 35px;'></div>", unsafe_allow_html=True)
        st.divider()
        st.subheader(f"📊 Gesamtübersicht aller Nebenkosten-Töpfe ({zeitraum_label})")
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        total_startbestand = 0.0
        total_geplant_endsaldo = 0.0
        total_aktueller_saldo = 0.0

        conn = get_connection()
        for k_name in NEBENKOSTEN_KONTEN:
            startbestand = get_startbestand_bis_vormonat(k_name, globaler_monat)
            total_startbestand += startbestand
            
            start_row = conn.execute("SELECT monat, betrag FROM anfangsbestaende WHERE konto=? ORDER BY monat ASC LIMIT 1", (k_name,)).fetchone()
            base_monat = start_row[0] if start_row else '2000-01'
            base_betrag = start_row[1] if start_row else 0.0
            
            if globaler_monat.endswith("-ALL"):
                tx_query = f"SELECT betrag, status FROM transaktionen WHERE konto='{k_name}' AND monat >= '{base_monat}' AND monat LIKE '{ausgewaehltes_jahr}-%'"
            else:
                tx_query = f"SELECT betrag, status FROM transaktionen WHERE konto='{k_name}' AND monat >= '{base_monat}' AND monat <= '{globaler_monat}'"
                
            df_all = pd.read_sql(tx_query, conn)
            
            if not df_all.empty:
                aktuell_tx = df_all[df_all['status'] == 'bestätigt']['betrag'].sum()
                geplant_tx = df_all['betrag'].sum()
            else:
                aktuell_tx, geplant_tx = 0.0, 0.0
                
            total_aktueller_saldo += (base_betrag + aktuell_tx)
            total_geplant_endsaldo += (base_betrag + geplant_tx)
            
        col_tot1, col_tot2, col_tot3 = st.columns(3)
        col_tot1.metric("Gesamter Startbestand", f"{format_num(total_startbestand)} CHF")
        col_tot2.metric("Gesamter Geplanter Endsaldo", f"{format_num(total_geplant_endsaldo)} CHF")
        col_tot3.metric("Gesamter Aktueller Saldo (Ist-Stand)", f"{format_num(total_aktueller_saldo)} CHF")

        st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
        with st.expander("📝 Budget-Planung (Sparplan für deine Töpfe)"):
            if globaler_monat.endswith("-ALL"):
                st.info("Wähle einen spezifischen Monat in der Sidebar, um die Budget-Planung zu bearbeiten.")
            else:
                st.markdown("Erfasse hier deine wiederkehrenden jährlichen Ausgaben. Das System berechnet dir automatisch deinen monatlichen Sparbedarf pro Topf.")
                
                with st.form("budget_form", border=True):
                    c1, c2, c3 = st.columns([2, 1, 1])
                    b_desc = c1.text_input("Ausgabe (z.B. Autoversicherung, Steuern)")
                    b_topf = c2.selectbox("Zuweisen zu Topf", NEBENKOSTEN_KONTEN)
                    b_betrag = c3.number_input("Kosten pro Jahr (CHF)", min_value=0.0, step=50.0, format="%.2f")
                    
                    if st.form_submit_button("Budget-Position speichern"):
                        if b_desc and b_betrag > 0:
                            conn.execute("INSERT INTO budget_nebenkosten (beschreibung, betrag_jaehrlich, konto) VALUES (?,?,?)", (b_desc, b_betrag, b_topf))
                            conn.commit()
                            upload_db()
                            st.success("Erfolgreich hinzugefügt!")
                            time.sleep(0.5)
                            st.rerun()

                df_budget = pd.read_sql("SELECT * FROM budget_nebenkosten ORDER BY konto, beschreibung", conn)
                
                if not df_budget.empty:
                    st.markdown("### Erfasste Ausgaben")
                    for _, row in df_budget.iterrows():
                        col_t1, col_t2, col_t3, col_t4 = st.columns([3, 2, 2, 1])
                        col_t1.write(f"**{row['beschreibung']}**")
                        col_t2.write(f"Topf: {row['konto']}")
                        col_t3.write(f"{format_num(row['betrag_jaehrlich'])} CHF / Jahr")
                        
                        if col_t4.button("🗑️ Löschen", key=f"del_bud_{row['id']}"):
                            conn.execute("DELETE FROM budget_nebenkosten WHERE id=?", (row['id'],))
                            conn.commit()
                            upload_db()
                            st.rerun()
                    
                    st.divider()
                    st.markdown("### 🎯 Dein monatlicher Sparplan")
                    summary = df_budget.groupby('konto')['betrag_jaehrlich'].sum().reset_index()
                    sum_cols = st.columns(3)
                    col_idx = 0
                    for _, s_row in summary.iterrows():
                        topf = s_row['konto']
                        j_sum = s_row['betrag_jaehrlich']
                        m_sum = j_sum / 12
                        with sum_cols[col_idx % 3]:
                            st.info(f"**{topf}**\n\nZiel: **{format_num(m_sum)} CHF / Monat**\n\n*(Total: {format_num(j_sum)} CHF/Jahr)*")
                        col_idx += 1
                else:
                    st.info("Noch keine Ausgaben für das Budget erfasst.")
        conn.close()

    elif st.session_state.view == 'lohn_details':
        konto_name = st.session_state.selected_konto
        if konto_name not in NEBENKOSTEN_KONTEN: return
            
        zeitraum_text = f"Jahr {ausgewaehltes_jahr}" if globaler_monat.endswith("-ALL") else f"{ausgewaehlter_monat_name} {ausgewaehltes_jahr}"
        
        st.title(f"Cockpit: {konto_name}")
        st.caption(f"📅 Filter aktiv: {zeitraum_text}")
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

        with st.expander("➕ Neue Transaktion erfassen"):
            typ = st.selectbox("Typ", ["Gutschrift", "Belastung", "Übertrag (Umbuchung)"])
            with st.form("add_txn_nebenkosten"):
                c1, c2 = st.columns(2)
                curr_label = "USD" if konto_name == "Yuh USD" else "CHF"
                betrag = c1.number_input(f"Betrag ({curr_label})", min_value=0.0)
                txn_datum = c1.date_input("Buchungsdatum", datetime.now())
                desc = c2.text_input("Beschreibung / Zweck")
                modus = c2.radio("Modus", ["Einmalig", "Dauerauftrag (bis Jahresende)"])
                
                von_konto, nach_konto = None, None
                manuell_kurs = 0.0
                
                if typ == "Übertrag (Umbuchung)":
                    st.markdown("---")
                    c3, c4 = st.columns(2)
                    von_konto = c3.selectbox("Von Konto", ALLE_KONTEN, index=ALLE_KONTEN.index(konto_name))
                    nach_konto = c4.selectbox("Nach Konto", [k for k in ALLE_KONTEN if k != von_konto])
                    
                    st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
                    manuell_kurs = st.number_input("Wechselkurs (optional, bei Fremdwährungen)", min_value=0.0000, format="%.4f", step=0.0100, help="Lass dies auf 0.0000, um den tagesaktuellen Live-Kurs zu nutzen.")

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
                            
                            w_von = "USD" if von_konto == "Yuh USD" else "CHF"
                            w_nach = "USD" if nach_konto == "Yuh USD" else "CHF"
                            
                            b_von = betrag
                            b_nach = betrag
                            d_von = f"Übertrag an {nach_konto}: {desc}"
                            d_nach = f"Übertrag von {von_konto}: {desc}"
                            
                            if w_von != w_nach:
                                if manuell_kurs > 0:
                                    usd_rate = manuell_kurs
                                else:
                                    usd_rate = get_exchange_rate("USD", "CHF")
                                    
                                if w_von == "USD": 
                                    b_nach = betrag * usd_rate
                                    d_nach = f"Übertrag von {von_konto} (≈ {format_num(betrag)} USD @ Kurs {usd_rate:.4f}): {desc}"
                                    d_von = f"Übertrag an {nach_konto} (≈ {format_num(b_nach)} CHF @ Kurs {usd_rate:.4f}): {desc}"
                                else:
                                    b_nach = betrag / usd_rate
                                    d_nach = f"Übertrag von {von_konto} (≈ {format_num(betrag)} CHF @ Kurs {usd_rate:.4f}): {desc}"
                                    d_von = f"Übertrag an {nach_konto} (≈ {format_num(b_nach)} USD @ Kurs {usd_rate:.4f}): {desc}"

                            conn.execute("INSERT INTO transaktionen (konto, typ, betrag, beschreibung, datum, monat, status, modus, link_id) VALUES (?,?,?,?,?,?,?,?,?)",
                                         (von_konto, "Belastung", -b_von, d_von, datum_str, z_monat, "geplant", modus, link))
                            conn.execute("INSERT INTO transaktionen (konto, typ, betrag, beschreibung, datum, monat, status, modus, link_id) VALUES (?,?,?,?,?,?,?,?,?)",
                                         (nach_konto, "Gutschrift", b_nach, d_nach, datum_str, z_monat, "geplant", modus, link))
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
        col1.metric("Startbestand", f"{format_num(startbestand_anzeige)} CHF")
        col2.metric("Geplanter Endsaldo", f"{format_num(summe_geplant)} CHF")
        col3.metric("Aktueller Endsaldo", f"{format_num(summe_aktuell)} CHF")
        
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        
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
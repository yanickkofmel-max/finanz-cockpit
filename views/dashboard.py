import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
from db_manager import get_connection, get_anfangsbestand
from components import render_bank_kachel, get_saldo_bis_monat
from theme import render_transaction_row, render_table_header
from utils.drive_sync import upload_db 
from utils.pdf_generator import generate_kontoauszug_pdf
from utils.market_data import get_exchange_rate, get_current_price

def get_konten_von_db(typ=None):
    conn = get_connection()
    if typ:
        konten = [row[0] for row in conn.execute("SELECT name FROM konten WHERE typ=?", (typ,)).fetchall()]
    else:
        konten = [row[0] for row in conn.execute("SELECT name FROM konten").fetchall()]
    conn.close()
    return konten

# Hilfsfunktion zur Live-Berechnung des gesamten Portfoliowertes in CHF
def get_total_portfolio_value_chf():
    conn = get_connection()
    try:
        df_trades = pd.read_sql("SELECT * FROM portfolio_trades", conn)
    except:
        df_trades = pd.DataFrame()
    conn.close()
    
    if df_trades.empty:
        return 0.0
        
    portfolio = {}
    for _, row in df_trades.iterrows():
        t = row['ticker']
        if t not in portfolio:
            portfolio[t] = {'menge': 0.0, 'waehrung': row['waehrung']}
        
        if row['aktion'] == 'Kauf':
            portfolio[t]['menge'] += row['menge']
        elif row['aktion'] == 'Verkauf':
            portfolio[t]['menge'] -= row['menge']
            
    total_chf = 0.0
    for t, data in portfolio.items():
        if data['menge'] > 0.00001:
            live_preis = get_current_price(t)
            live_kurs_chf = get_exchange_rate(data['waehrung'], "CHF")
            total_chf += data['menge'] * live_preis * live_kurs_chf
    return total_chf

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

def show_dashboard(ausgewaehlter_monat_name, ausgewaehltes_jahr, globaler_monat):
    zeitraum_text = f"Jahr {ausgewaehltes_jahr}" if globaler_monat.endswith("-ALL") else f"{ausgewaehlter_monat_name} {ausgewaehltes_jahr}"

    # --- ANSICHT 1: DAS HAUPT-DASHBOARD ---
    if st.session_state.view == 'dashboard':
        st.title("Dashboard")
        st.caption(f"📊 Finanz-Gesamtübersicht für {zeitraum_text}")
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        
        lohn_konten = get_konten_von_db("Lohnkonto")
        vermoegen_konten = get_konten_von_db("Vermögen")
        
        # ---> ERWEITERUNG 1: MATHEMATISCHE BERECHNUNG FÜR DAS COCKPIT <---
        total_lohn_chf = 0.0
        for l_name in lohn_konten:
            if globaler_monat.endswith("-ALL"):
                conn = get_connection()
                df_all_l = pd.read_sql(f"SELECT betrag FROM transaktionen WHERE konto='{l_name}' AND monat LIKE '{ausgewaehltes_jahr}-%' AND status='bestätigt'", conn)
                start_l = get_startbestand_bis_vormonat(l_name, globaler_monat)
                conn.close()
                total_lohn_chf += start_l + (df_all_l['betrag'].sum() if not df_all_l.empty else 0.0)
            else:
                conn = get_connection()
                df_monat_l = pd.read_sql(f"SELECT SUM(betrag) as total FROM transaktionen WHERE konto='{l_name}' AND monat='{globaler_monat}' AND status='bestätigt'", conn)
                conn.close()
                total_lohn_chf += (df_monat_l['total'].iloc[0] or 0.0) + get_anfangsbestand(l_name, globaler_monat)

        total_vermoegen_chf = 0.0
        for v_name in vermoegen_konten:
            s_geo, s_akt = get_saldo_bis_monat(v_name, globaler_monat)
            if v_name == "Yuh USD":
                total_vermoegen_chf += s_akt * get_exchange_rate("USD", "CHF")
            else:
                total_vermoegen_chf += s_akt

        portfolio_live_value = get_total_portfolio_value_chf()
        echtes_gesamtvermoegen = total_lohn_chf + total_vermoegen_chf + portfolio_live_value

        # Visuelles Cockpit ganz oben rendern
        with st.container(border=True):
            st.markdown("#### 👑 Dein Vermögens-Cockpit (Net Worth)")
            st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
            sum_c1, sum_c2, sum_c3 = st.columns(3)
            sum_c1.metric("💳 Flüssige Mittel (Lohnkonten)", f"{total_lohn_chf:,.2f} CHF")
            sum_c2.metric("📈 Anlagen (Ersparnisse + Depots)", f"{(total_vermoegen_chf + portfolio_live_value):,.2f} CHF")
            sum_c3.metric("💰 Echte Net-Worth (Gesamt)", f"{echtes_gesamtvermoegen:,.2f} CHF")
        
        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

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
            st.subheader("📈 Vermögen & Investments")
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            
            # ---> ERWEITERUNG 2: MIX DER REALEN KACHELN + DIE PORTFOLIO-VIRTUAL-KACHEL <---
            alle_kacheln = list(vermoegen_konten) + ["_VIRTUAL_PORTFOLIO_"]
            for i in range(0, len(alle_kacheln), 3):
                chunk = alle_kacheln[i:i+3]
                spalten = st.columns(3)
                for j, item in enumerate(chunk):
                    with spalten[j]:
                        if item == "_VIRTUAL_PORTFOLIO_":
                            # Wunderschöne, farblich angepasste Kachel für das Portfolio
                            st.markdown(f"""
                                <div class="bank-tile" style="border-color: rgba(46, 204, 113, 0.25);">
                                    <div class="header-box">
                                        <div class="logo-wrapper" style="background: #2ECC71; display: flex; align-items: center; justify-content: center; font-size: 1.4rem;">
                                            🚀
                                        </div>
                                        <div class="title-text" style="color: #2ECC71; font-weight: bold;">Wertschriften-Portfolio</div>
                                    </div>
                                    <div class="grid-box" style="background: rgba(46, 204, 113, 0.03);">
                                        <div class="val-col">
                                            <div class="label-text">Live-Wert</div>
                                            <div class="val-text" style="color: #2ECC71;">{portfolio_live_value:,.2f} CHF</div>
                                        </div>
                                        <div class="val-col right">
                                            <div class="label-text">Status</div>
                                            <div class="val-text" style="font-size: 0.85rem; color: #2ECC71; padding-top: 4px;">● Aktiv (Live)</div>
                                        </div>
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)
                            st.caption("💡 Details & historische Trades findest du im Menü unter 'Aktien & Krypto'.")
                        else:
                            render_bank_kachel(item, globaler_monat, show_button=True)
            st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
            
            # KREISDIAGRAMM-STRUKTUR
            chart_data = []
            for k_name in vermoegen_konten:
                s_geo, s_akt = get_saldo_bis_monat(k_name, globaler_monat)
                if s_akt > 0:
                    if k_name == "Yuh USD":
                        usd_rate = get_exchange_rate("USD", "CHF")
                        chart_data.append({"Konto": k_name, "Saldo": s_akt * usd_rate})
                    else:
                        chart_data.append({"Konto": k_name, "Saldo": s_akt})
            
            # ---> ERWEITERUNG 3: PORTFOLIO IN DAS KREISDIAGRAMM EINSPEISEN <---
            if portfolio_live_value > 0:
                chart_data.append({"Konto": "🚀 Wertschriften-Portfolio", "Saldo": portfolio_live_value})
            
            if chart_data:
                df_chart = pd.DataFrame(chart_data)
                with st.container(border=True):
                    st.markdown("#### 🍩 Vermögensaufteilung (Effektiv verbucht)")
                    st.caption("Visuelle Übersicht über die prozentuale Verteilung deines effektiv bestätigten Gesamtvermögens in CHF.")
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
                st.info("Noch kein positives, effektiv verbuchtes Vermögen für die Diagramm-Anzeige in diesem Zeitraum vorhanden.")

    # --- ANSICHT 2: COCKPIT-DETAILS ---
    elif st.session_state.view == 'lohn_details':
        konto_name = st.session_state.selected_konto
        st.title(f"Cockpit: {konto_name}")
        st.caption(f"📅 Filter aktiv: {zeitraum_text}")
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        
        conn = get_connection()
        typ_res = conn.execute("SELECT typ FROM konten WHERE name=?", (konto_name,)).fetchone()
        k_typ = typ_res[0] if typ_res else ""
        conn.close()
        
        is_lohn = (k_typ == "Lohnkonto")
        neuer_bestand = 0.0

        if globaler_monat.endswith("-ALL"):
            st.info("💡 Um den Startbestand zu verwalten oder neue Buchungen zu erfassen, wähle bitte links in der Sidebar einen spezifischen Monat aus.")
        else:
            akt_bestand = get_anfangsbestand(konto_name, globaler_monat)
            neuer_bestand = akt_bestand
            
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
                            upload_db()
                            st.success("Gespeichert!")
                            time.sleep(0.5)
                            st.rerun()
                st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

            with st.expander("➕ Neue Transaktion erfassen"):
                typ = st.selectbox("Typ", ["Gutschrift", "Belastung", "Übertrag (Umbuchung)"])
                with st.form("add_txn_dash"):
                    c1, c2 = st.columns(2)
                    curr_label = "USD" if konto_name == "Yuh USD" else "CHF"
                    betrag = c1.number_input(f"Betrag ({curr_label})", min_value=0.0)
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
                                    usd_rate = get_exchange_rate("USD", "CHF")
                                    if w_von == "USD":
                                        b_nach = betrag * usd_rate
                                        d_nach = f"Übertrag von {von_konto} (≈ {betrag:,.2f} USD @ Kurs {usd_rate:.4f}): {desc}"
                                        d_von = f"Übertrag an {nach_konto} (≈ {b_nach:,.2f} CHF @ Kurs {usd_rate:.4f}): {desc}"
                                    else:
                                        b_nach = betrag / usd_rate
                                        d_nach = f"Übertrag von {von_konto} (≈ {betrag:,.2f} CHF @ Kurs {usd_rate:.4f}): {desc}"
                                        d_von = f"Übertrag an {nach_konto} (≈ {b_nach:,.2f} USD @ Kurs {usd_rate:.4f}): {desc}"

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
            startbestand_anzeige = get_startbestand_bis_vormonat(konto_name, globaler_monat)
        else:
            df = pd.read_sql(f"SELECT * FROM transaktionen WHERE konto='{konto_name}' AND monat='{globaler_monat}' ORDER BY datum DESC", conn)
            if k_typ in ["Vermögen", "Nebenkosten"]:
                startbestand_anzeige = get_startbestand_bis_vormonat(konto_name, globaler_monat)
            else:
                startbestand_anzeige = neuer_bestand
        conn.close()
        
        summe_monat_geplant = df['betrag'].sum() if not df.empty else 0.0
        summe_monat_aktuell = df[df['status'] == 'bestätigt']['betrag'].sum() if not df.empty else 0.0
        
        summe_geplant = startbestand_anzeige + summe_monat_geplant
        summe_aktuell = startbestand_anzeige + summe_monat_aktuell

        if not df.empty:
            render_table_header()
            for _, row in df.iterrows(): 
                render_transaction_row(row, handle_confirm, handle_delete)
        else:
            st.info("In diesem Zeitraum sind für dieses Konto keine direkten Buchungen vorhanden.")
            
        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        st.divider()
        
        col1, col2, col3 = st.columns(3)
        if konto_name == "Yuh USD":
            usd_rate = get_exchange_rate("USD", "CHF")
            col1.metric("Startbestand", f"{startbestand_anzeige:,.2f} USD")
            col1.markdown(f"<div style='margin-top:-15px; font-size:0.85rem; color:#8A8F98;'>≈ {startbestand_anzeige * usd_rate:,.2f} CHF</div>", unsafe_allow_html=True)
            col2.metric("Geplanter Endsaldo", f"{summe_geplant:,.2f} USD")
            col2.markdown(f"<div style='margin-top:-15px; font-size:0.85rem; color:#8A8F98;'>≈ {summe_geplant * usd_rate:,.2f} CHF</div>", unsafe_allow_html=True)
            col3.metric("Aktueller Endsaldo", f"{summe_aktuell:,.2f} USD")
            col3.markdown(f"<div style='margin-top:-15px; font-size:0.85rem; color:#8A8F98;'>≈ {summe_aktuell * usd_rate:,.2f} CHF</div>", unsafe_allow_html=True)
        else:
            col1.metric("Startbestand", f"{startbestand_anzeige:,.2f} CHF")
            col2.metric("Geplanter Endsaldo", f"{summe_geplant:,.2f} CHF")
            col3.metric("Aktueller Endsaldo", f"{summe_aktuell:,.2f} CHF")
        
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        
        btn_col1, btn_col2 = st.columns([1, 5], vertical_alignment="center")
        with btn_col1:
            if st.button("← Zurück", key="btn_back_dash", use_container_width=True):
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
                mime="application/pdf",
                key="btn_pdf_dash"
            )
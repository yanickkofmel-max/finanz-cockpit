import streamlit as st
import pandas as pd
from datetime import datetime
import time
from db_manager import get_connection
from utils.market_data import get_current_price, get_exchange_rate, search_ticker
from utils.drive_sync import upload_db

def get_vermoegen_konten():
    conn = get_connection()
    konten = [row[0] for row in conn.execute("SELECT name FROM konten WHERE typ='Vermögen'").fetchall()]
    conn.close()
    return konten

def delete_trade(trade_id, aktion, menge, ticker, depot, gebuehren, datum_str):
    conn = get_connection()
    conn.execute("DELETE FROM portfolio_trades WHERE id=?", (trade_id,))
    trans_desc = f"Trade {depot}: {aktion} {menge} {ticker} (inkl. {gebuehren} CHF Geb.)"
    conn.execute("DELETE FROM transaktionen WHERE beschreibung=? AND datum=?", (trans_desc, datum_str))
    conn.commit()
    conn.close()
    upload_db()
    st.rerun()

def delete_ticker(ticker, depot):
    conn = get_connection()
    df_trades = pd.read_sql("SELECT * FROM portfolio_trades WHERE ticker=? AND depot=?", conn, params=(ticker, depot))
    for _, row in df_trades.iterrows():
        trans_desc = f"Trade {row['depot']}: {row['aktion']} {row['menge']} {row['ticker']} (inkl. {row.get('gebuehren', 0.0)} CHF Geb.)"
        conn.execute("DELETE FROM transaktionen WHERE beschreibung=? AND datum=?", (trans_desc, row['datum']))
    
    conn.execute("DELETE FROM portfolio_trades WHERE ticker=? AND depot=?", (ticker, depot))
    conn.commit()
    conn.close()
    upload_db()
    st.rerun()

@st.dialog("📜 Trade-Historie & Details")
def show_history_dialog(ticker, depot_name, df_history, gebuehren_total):
    st.markdown(f"### {ticker}")
    # Hier war der Tippfehler: gebueuren_total -> gebuehren_total
    st.caption(f"Depot: **{depot_name}** &nbsp;|&nbsp; Gesamte Gebühren: **{gebuehren_total:.2f} CHF**")
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    for _, tr_row in df_history.iterrows():
        trade_fremd = tr_row['menge'] * tr_row['kaufpreis_einzeln']
        trade_chf_rein = trade_fremd * tr_row['wechselkurs_kauf']
        
        if tr_row['aktion'] == "Kauf":
            total_chf = trade_chf_rein + tr_row['gebuehren']
            bg_color = "rgba(255, 107, 107, 0.08)" 
            border_color = "#FF6B6B"
            aktion_text = "Total Belastung"
        else:
            total_chf = trade_chf_rein - tr_row['gebuehren']
            bg_color = "rgba(46, 204, 113, 0.08)" 
            border_color = "#2ECC71"
            aktion_text = "Total Gutschrift"
            
        fremd_str = f" <span style='font-size:0.8rem; font-weight:normal; color:gray;'>(≈ {trade_fremd:,.2f} {tr_row['waehrung']})</span>" if tr_row['waehrung'] != "CHF" else ""

        html_card = f"""
        <div style='background-color: {bg_color}; padding: 12px; border-radius: 6px; border-left: 4px solid {border_color}; margin-bottom: 10px;'>
            <div style='font-size: 0.9rem; margin-bottom: 4px;'>
                <strong>{tr_row['datum']} &nbsp;|&nbsp; {tr_row['aktion']}</strong>
            </div>
            <div style='font-size: 0.85rem; color: #E2E8F0;'>
                {tr_row['menge']:g} Stück à {tr_row['kaufpreis_einzeln']} {tr_row['waehrung']} 
                <span style='color: gray;'>(Gebühr: {tr_row['gebuehren']:.2f} CHF)</span>
            </div>
            <div style='font-size: 0.95rem; font-weight: 600; margin-top: 6px;'>
                {aktion_text}: {total_chf:,.2f} CHF {fremd_str}
            </div>
        </div>
        """
        
        hc1, hc2 = st.columns([4, 1], vertical_alignment="center")
        hc1.markdown(html_card, unsafe_allow_html=True)
        with hc2:
            if st.button("🗑️", key=f"del_tr_mod_{tr_row['id']}", help="Nur diesen Trade löschen", use_container_width=True):
                delete_trade(tr_row['id'], tr_row['aktion'], tr_row['menge'], tr_row['ticker'], tr_row['depot'], tr_row['gebuehren'], tr_row['datum'])

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
    st.divider()
    st.markdown("<div style='font-size: 0.95rem; font-weight: bold; color: #FF6B6B; margin-bottom: 5px;'>⚠️ Gefahrenzone</div>", unsafe_allow_html=True)
    st.caption(f"Achtung: Dies löscht den kompletten Titel **{ticker}** aus diesem Depot, inklusive aller aufgeführten Käufe und Verkäufe unwiderruflich.")
    if st.button(f"🗑️ Gesamten Titel '{ticker}' löschen", key=f"del_entire_ticker_{ticker}_{depot_name}", use_container_width=True):
        delete_ticker(ticker, depot_name)

def show_portfolio():
    # --- AUTOMATISCHE DATENBANK-MIGRATION FÜR DIE NEUEN DEPOTNAMEN ---
    conn = get_connection()
    conn.execute("UPDATE portfolio_trades SET depot = 'Depot Neon' WHERE depot = 'Neon Invest'")
    conn.execute("UPDATE portfolio_trades SET depot = 'Depot Yuh' WHERE depot = 'Yuh Invest'")
    conn.execute("UPDATE transaktionen SET beschreibung = REPLACE(beschreibung, 'Trade Neon Invest:', 'Trade Depot Neon:') WHERE beschreibung LIKE 'Trade Neon Invest:%'")
    conn.execute("UPDATE transaktionen SET beschreibung = REPLACE(beschreibung, 'Trade Yuh Invest:', 'Trade Depot Yuh:') WHERE beschreibung LIKE 'Trade Yuh Invest:%'")
    conn.commit()
    conn.close()

    st.title("📈 Aktien & Krypto Portfolio")
    st.caption("Verwalte deine Wertpapiere getrennt nach Depots (Neon, Yuh).")
    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    vermoegen_konten = get_vermoegen_konten() + ["Andere (Keine Verrechnung)"]
    
    # --- Umbenannte Depots in der Auswahl ---
    verfuegbare_depots = ["Depot Neon", "Depot Yuh", "Anderes Depot"]

    # --- 1. NEUEN KAUF / VERKAUF ERFASSEN ---
    with st.expander("➕ Neuen Trade (Kauf/Verkauf) erfassen"):
        
        st.markdown("**(0) Symbol suchen (falls unbekannt)**")
        c_s1, c_s2 = st.columns([3, 1], vertical_alignment="bottom")
        suchbegriff = c_s1.text_input("Name der Firma oder Kryptowährung (z.B. Ripple, Novartis)", placeholder="Suchbegriff eingeben...")
        if c_s2.button("🔍 Live Suchen", use_container_width=True):
            ergebnisse = search_ticker(suchbegriff)
            if ergebnisse:
                for e in ergebnisse:
                    if e['symbol'] != "Fehler":
                        st.info(f"**Symbol:** `{e['symbol']}` &nbsp;&nbsp;|&nbsp;&nbsp; {e['name']} *({e['info']})*")
            else:
                st.warning("Kein Ticker gefunden.")
        
        st.divider()

        with st.form("trade_form", border=False):
            st.markdown("**(1) Was hast du gehandelt?**")
            c1, c2, c3 = st.columns(3)
            aktion = c1.selectbox("Aktion", ["Kauf", "Verkauf"])
            ticker = c2.text_input("Ticker-Symbol", help="Beispiele: NOVN.SW (Novartis), AAPL (Apple), BTC-USD (Bitcoin)")
            menge = c3.number_input("Menge (Stück)", min_value=0.0000, format="%.4f", step=1.0)

            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            st.markdown("**(2) Kosten & Gebühren**")
            c4, c5, c6 = st.columns(3)
            preis = c4.number_input("Preis pro Stück (Fremdwährung)", min_value=0.00, format="%.4f", step=1.0)
            waehrung = c5.selectbox("Währung des Wertpapiers", ["USD", "CHF", "EUR"])
            gebuehren = c6.number_input("Total Gebühren/Spesen (in CHF)", min_value=0.00, format="%.2f", step=1.0)

            manuell_kurs = st.number_input("Wechselkurs (optional, falls anders als heute)", min_value=0.0000, format="%.4f", step=0.0100, help="Lass dies auf 0.0000, um automatisch den tagesaktuellen Live-Kurs zu verwenden.")

            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            st.markdown("**(3) Zuordnung**")
            c7, c8, c9 = st.columns(3)
            ziel_depot = c7.selectbox("In welches Depot legen?", verfuegbare_depots)
            cash_konto = c8.selectbox("Verrechnungskonto (Cash)", vermoegen_konten)
            datum = c9.date_input("Datum", datetime.now())

            if st.form_submit_button("Trade buchen", type="primary"):
                if ticker and menge > 0 and preis > 0:
                    ticker = ticker.upper().strip()
                    
                    test_preis = 0.0
                    with st.spinner("Validiere Ticker-Symbol bei Yahoo Finance..."):
                        test_preis = get_current_price(ticker)
                        
                    if test_preis == 0.0:
                        st.error(f"❌ Ungültiges Symbol: '{ticker}' konnte nicht gefunden werden. Bitte nutze die Live-Suche (Schritt 0), um das korrekte Kürzel herauszufinden.")
                    else:
                        if manuell_kurs > 0:
                            wechselkurs = manuell_kurs
                        else:
                            wechselkurs = get_exchange_rate(waehrung, "CHF")
                        
                        reiner_wert_chf = menge * preis * wechselkurs
                        
                        if aktion == "Kauf":
                            gesamt_cashflow_chf = reiner_wert_chf + gebuehren
                        else:
                            gesamt_cashflow_chf = reiner_wert_chf - gebuehren
                        
                        datum_str = datum.strftime("%Y-%m-%d")
                        monat_str = datum.strftime("%Y-%m")

                        conn = get_connection()
                        
                        conn.execute('''INSERT INTO portfolio_trades 
                            (konto, ticker, aktion, menge, kaufpreis_einzeln, waehrung, wechselkurs_kauf, datum, depot, gebuehren) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                            (cash_konto, ticker, aktion, menge, preis, waehrung, wechselkurs, datum_str, ziel_depot, gebuehren))
                        
                        if "Andere" not in cash_konto:
                            trans_typ = "Belastung" if aktion == "Kauf" else "Gutschrift"
                            trans_desc = f"Trade {ziel_depot}: {aktion} {menge} {ticker} (inkl. {gebuehren} CHF Geb.)"
                            
                            if cash_konto == "Yuh USD":
                                usd_rate = get_exchange_rate("USD", "CHF")
                                gesamt_cashflow_usd = gesamt_cashflow_chf / usd_rate
                                trans_betrag = -gesamt_cashflow_usd if aktion == "Kauf" else gesamt_cashflow_usd
                            else:
                                trans_betrag = -gesamt_cashflow_chf if aktion == "Kauf" else gesamt_cashflow_chf
                            
                            conn.execute('''INSERT INTO transaktionen 
                                (konto, typ, betrag, beschreibung, datum, monat, status, modus, link_id) 
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                (cash_konto, trans_typ, trans_betrag, trans_desc, datum_str, monat_str, "geplant", "Einmalig", ""))
                        
                        conn.commit()
                        conn.close()
                        upload_db()
                        st.success("Erfolgreich als geplant verbucht!")
                        time.sleep(1.0)
                        st.rerun()
                else:
                    st.error("Bitte fülle Ticker, Menge und Preis aus.")

    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

    # --- 2. PORTFOLIO ÜBERSICHT (GRUPPIERT NACH DEPOT) ---
    st.subheader("📊 Deine Portfolios")
    st.caption("Aktuelle Live-Kurse werden von Yahoo Finance abgerufen...")
    
    conn = get_connection()
    df_trades = pd.read_sql("SELECT * FROM portfolio_trades ORDER BY datum ASC", conn)
    conn.close()

    if not df_trades.empty:
        if 'depot' not in df_trades.columns:
            df_trades['depot'] = 'Depot Neon'
            
        alle_depots = df_trades['depot'].unique()
        
        global_investiert = 0.0
        global_aktuell = 0.0
        global_gebuehren = 0.0
        
        depot_summaries = {}

        for depot_name in alle_depots:
            df_depot = df_trades[df_trades['depot'] == depot_name]
            
            portfolio = {}
            for _, row in df_depot.iterrows():
                t = row['ticker']
                if t not in portfolio:
                    portfolio[t] = {'menge': 0.0, 'investiert_chf': 0.0, 'investiert_fremd': 0.0, 'gebuehren_total': 0.0, 'waehrung': row['waehrung']}
                
                trade_wert_fremd = row['menge'] * row['kaufpreis_einzeln']
                trade_wert_chf = trade_wert_fremd * row['wechselkurs_kauf']
                geb = row.get('gebuehren', 0.0)
                
                if row['aktion'] == 'Kauf':
                    portfolio[t]['menge'] += row['menge']
                    portfolio[t]['investiert_chf'] += trade_wert_chf 
                    portfolio[t]['investiert_fremd'] += trade_wert_fremd
                    portfolio[t]['gebuehren_total'] += geb
                elif row['aktion'] == 'Verkauf':
                    if portfolio[t]['menge'] > 0:
                        durchschnittskosten_chf = portfolio[t]['investiert_chf'] / portfolio[t]['menge']
                        durchschnittskosten_fremd = portfolio[t]['investiert_fremd'] / portfolio[t]['menge']
                        portfolio[t]['investiert_chf'] -= (durchschnittskosten_chf * row['menge'])
                        portfolio[t]['investiert_fremd'] -= (durchschnittskosten_fremd * row['menge'])
                    portfolio[t]['menge'] -= row['menge']
                    portfolio[t]['gebuehren_total'] += geb 

            depot_investiert = 0.0
            depot_aktuell = 0.0
            depot_gebuehren = 0.0
            aktive_positionen = []

            for t, data in portfolio.items():
                if data['menge'] > 0.00001 or data['menge'] < -0.00001: 
                    live_preis_fremd = get_current_price(t)
                    live_kurs_chf = get_exchange_rate(data['waehrung'], "CHF")
                    
                    wert_aktuell_chf = data['menge'] * live_preis_fremd * live_kurs_chf
                    
                    depot_investiert += data['investiert_chf']
                    depot_aktuell += wert_aktuell_chf
                    depot_gebuehren += data['gebuehren_total']
                    
                    aktive_positionen.append((t, data, live_preis_fremd, wert_aktuell_chf, live_kurs_chf))

            global_investiert += depot_investiert
            global_aktuell += depot_aktuell
            global_gebuehren += depot_gebuehren

            if aktive_positionen:
                depot_netto = depot_aktuell - depot_investiert - depot_gebuehren
                depot_perf_proz = (depot_netto / depot_investiert * 100) if depot_investiert > 0 else 0
                
                depot_summaries[depot_name] = {
                    'aktuell': depot_aktuell,
                    'netto': depot_netto,
                    'prozent': depot_perf_proz
                }
                
                with st.expander(f"🏦 Depot: {depot_name} | Aktueller Wert: {depot_aktuell:,.2f} CHF", expanded=True):
                    st.markdown(f"**Reines Investment:** {depot_investiert:,.2f} CHF &nbsp;&nbsp;|&nbsp;&nbsp; **Bezahlte Gebühren:** {depot_gebuehren:,.2f} CHF &nbsp;&nbsp;|&nbsp;&nbsp; **Netto-Rendite:** <span style='color:{'#28A745' if depot_netto >=0 else '#FF6B6B'}'>{depot_netto:+,.2f} CHF ({depot_perf_proz:+.2f}%)</span>", unsafe_allow_html=True)
                    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                    
                    for pos in aktive_positionen:
                        t, data, live_preis_fremd, wert_aktuell_chf, live_kurs_chf = pos
                        
                        brutto_gewinn = wert_aktuell_chf - data['investiert_chf']
                        netto_gewinn = brutto_gewinn - data['gebuehren_total']
                        gewinn_prozent = (netto_gewinn / data['investiert_chf'] * 100) if data['investiert_chf'] > 0 else 0
                        
                        wert_aktuell_fremd = data['menge'] * live_preis_fremd
                        
                        with st.container(border=True):
                            st.markdown(f"<div style='font-size: 1.2rem; font-weight: bold; margin-bottom: -5px;'>{t}</div><div style='font-size: 0.9rem; color: gray;'>Bestand: {data['menge']:.4f}</div>", unsafe_allow_html=True)
                            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                            
                            c_m1, c_m2, c_m3 = st.columns(3)
                            c_m1.metric(f"Kurs ({data['waehrung']})", f"{live_preis_fremd:,.4f}")
                            
                            if data['waehrung'] != "CHF":
                                gebuehren_fremd = data['gebuehren_total'] / live_kurs_chf if live_kurs_chf > 0 else 0
                                netto_gewinn_fremd = (wert_aktuell_fremd - data['investiert_fremd']) - gebuehren_fremd
                                gewinn_prozent_fremd = (netto_gewinn_fremd / data['investiert_fremd'] * 100) if data['investiert_fremd'] > 0 else 0
                                
                                c_m2.metric(f"Reiner Wert ({data['waehrung']})", f"{wert_aktuell_fremd:,.2f} {data['waehrung']}")
                                c_m2.markdown(f"<div style='margin-top: -15px; font-size: 0.85rem; color: #8A8F98;'>≈ {wert_aktuell_chf:,.2f} CHF</div>", unsafe_allow_html=True)
                                
                                c_m3.metric(f"Netto-Rendite ({data['waehrung']})", f"{netto_gewinn_fremd:+,.2f} {data['waehrung']}", f"{gewinn_prozent_fremd:+.2f}%")
                                c_m3.markdown(f"<div style='margin-top: -15px; font-size: 0.85rem; color: #8A8F98;'>≈ {netto_gewinn:+,.2f} CHF ({gewinn_prozent:+.2f}%)</div>", unsafe_allow_html=True)
                            else:
                                c_m2.metric("Reiner Wert (CHF)", f"{wert_aktuell_chf:,.2f} CHF")
                                c_m3.metric("Netto-Rendite", f"{netto_gewinn:+,.2f} CHF", f"{gewinn_prozent:+.2f}%")
                            
                            if data['waehrung'] != "CHF":
                                asset_gewinn_fremd = wert_aktuell_fremd - data['investiert_fremd']
                                asset_gewinn_chf_heute = asset_gewinn_fremd * live_kurs_chf
                                waehrungs_effekt_chf = brutto_gewinn - asset_gewinn_chf_heute
                                
                                fx_color = "#2ECC71" if waehrungs_effekt_chf >= 0 else "#FF6B6B"
                                asset_color = "#2ECC71" if asset_gewinn_chf_heute >= 0 else "#FF6B6B"
                                
                                st.markdown(f"""
                                <div style='background: rgba(0,0,0,0.15); border-radius: 8px; padding: 12px 15px; margin-top: 10px; border: 1px solid rgba(255,255,255,0.05);'>
                                    <div style='display: flex; flex-wrap: wrap; gap: 12px;'>
                                        <div style='flex: 1; min-width: 130px;'>
                                            <div style='font-size: 0.7rem; color: #8A8F98; text-transform: uppercase; letter-spacing: 0.5px;'>Kursgewinn Titel</div>
                                            <div style='font-size: 1rem; font-weight: 600; color: {asset_color}; margin-top: 2px;'>{asset_gewinn_chf_heute:+,.2f} CHF</div>
                                        </div>
                                        <div style='flex: 1; min-width: 130px;'>
                                            <div style='font-size: 0.7rem; color: #8A8F98; text-transform: uppercase; letter-spacing: 0.5px;'>Währungseffekt ({data['waehrung']})</div>
                                            <div style='font-size: 1rem; font-weight: 600; color: {fx_color}; margin-top: 2px;'>{waehrungs_effekt_chf:+,.2f} CHF</div>
                                        </div>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                            
                            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                            
                            df_history = df_depot[df_depot['ticker'] == t].copy()
                            if st.button(f"📜 Historie & Details öffnen ({len(df_history)} Trades)", key=f"btn_hist_{t}_{depot_name}", use_container_width=True):
                                show_history_dialog(t, depot_name, df_history, data['gebuehren_total'])

        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        st.divider()
        st.markdown("### 💰 Gesamtvermögen (Alle Depots)")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Investiert (Ohne Gebühren)", f"{global_investiert:,.2f} CHF")
        c2.metric("Aktueller Wert", f"{global_aktuell:,.2f} CHF")
        
        gesamt_netto_chf = global_aktuell - global_investiert - global_gebuehren
        gesamt_perf_prozent = (gesamt_netto_chf / global_investiert * 100) if global_investiert > 0 else 0
        c3.metric("Total Netto-Rendite (Nach Gebühren)", f"{gesamt_netto_chf:+,.2f} CHF", f"{gesamt_perf_prozent:+.2f}%")

        if depot_summaries:
            st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
            st.markdown("#### 🏢 Aufteilung nach Depot")
            
            d_cols = st.columns(len(depot_summaries))
            
            for i, (d_name, d_stats) in enumerate(depot_summaries.items()):
                with d_cols[i]:
                    with st.container(border=True):
                        st.markdown(f"**{d_name}**")
                        st.metric(
                            label="Wert", 
                            value=f"{d_stats['aktuell']:,.2f} CHF", 
                            delta=f"{d_stats['netto']:+,.2f} CHF", 
                            label_visibility="collapsed"
                        )

    else:
        st.info("Dein Portfolio ist noch leer. Erfasse oben deinen ersten Trade!")
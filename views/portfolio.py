import streamlit as st
import pandas as pd
from datetime import datetime
import time
from db_manager import get_connection
from utils.market_data import get_current_price, get_exchange_rate, search_ticker
from utils.drive_sync import upload_db
# ---> NEU: Formatter importieren <---
from components import format_num

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
    st.caption(f"Depot: **{depot_name}** &nbsp;|&nbsp; Gesamte Gebühren/Steuern: **{format_num(gebuehren_total)} CHF**")
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    current_menge = 0.0
    current_invest_chf = 0.0

    for _, tr_row in df_history.iterrows():
        if tr_row['aktion'] == "Dividende":
            trade_fremd = tr_row['kaufpreis_einzeln'] 
        else:
            trade_fremd = tr_row['menge'] * tr_row['kaufpreis_einzeln']
            
        trade_chf_rein = trade_fremd * tr_row['wechselkurs_kauf']
        geb = tr_row.get('gebuehren', 0.0)
        
        realisiert_str = ""
        menge_str = f"{format_num(tr_row['menge'], 4)} Stück à {format_num(tr_row['kaufpreis_einzeln'], 4)} {tr_row['waehrung']}"
        
        if tr_row['aktion'] == "Kauf":
            current_menge += tr_row['menge']
            current_invest_chf += trade_chf_rein
            total_chf = trade_chf_rein + geb
            bg_color = "rgba(255, 107, 107, 0.08)" 
            border_color = "#FF6B6B"
            aktion_text = "Total Belastung"
            
        elif tr_row['aktion'] == "Verkauf":
            total_chf = trade_chf_rein - geb
            bg_color = "rgba(46, 204, 113, 0.08)" 
            border_color = "#2ECC71"
            aktion_text = "Total Gutschrift"
            
            if current_menge > 0:
                avg_cost = current_invest_chf / current_menge
                cost_sold = avg_cost * tr_row['menge']
                realisiert_trade = trade_chf_rein - cost_sold - geb
                current_invest_chf -= cost_sold
                
                r_color = "#2ECC71" if realisiert_trade >= 0 else "#FF6B6B"
                realisiert_str = f"<div style='margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem; color: {r_color};'><strong>Realisierter G/V (inkl. Gebühr): {format_num(realisiert_trade, 2, True)} CHF</strong></div>"
                
            current_menge -= tr_row['menge']
            
        elif tr_row['aktion'] == "Dividende":
            total_chf = trade_chf_rein - geb
            bg_color = "rgba(241, 196, 15, 0.08)" 
            border_color = "#F1C40F"
            aktion_text = "Netto-Dividende"
            menge_str = f"Brutto-Auszahlung: {format_num(tr_row['kaufpreis_einzeln'])} {tr_row['waehrung']}"
            realisiert_str = f"<div style='margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem; color: #F1C40F;'><strong>Ertrag in die Tasche: {format_num(total_chf, 2, True)} CHF</strong></div>"
            
        fremd_str = f" <span style='font-size:0.8rem; font-weight:normal; color:gray;'>(≈ {format_num(trade_fremd)} {tr_row['waehrung']})</span>" if tr_row['waehrung'] != "CHF" else ""

        html_card = f"""
        <div style='background-color: {bg_color}; padding: 12px; border-radius: 6px; border-left: 4px solid {border_color}; margin-bottom: 10px;'>
            <div style='font-size: 0.9rem; margin-bottom: 4px;'>
                <strong>{tr_row['datum']} &nbsp;|&nbsp; {tr_row['aktion']}</strong>
            </div>
            <div style='font-size: 0.85rem; color: #E2E8F0;'>
                {menge_str} 
                <span style='color: gray;'>(Spesen/Steuern: {format_num(geb)} CHF)</span>
            </div>
            <div style='font-size: 0.95rem; font-weight: 600; margin-top: 6px;'>
                {aktion_text}: {format_num(total_chf)} CHF {fremd_str}
            </div>
            {realisiert_str}
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
    st.caption(f"Achtung: Dies löscht den kompletten Titel **{ticker}** aus diesem Depot, inklusive aller aufgeführten Käufe, Verkäufe und Dividenden unwiderruflich.")
    if st.button(f"🗑️ Gesamten Titel '{ticker}' löschen", key=f"del_entire_ticker_{ticker}_{depot_name}", use_container_width=True):
        delete_ticker(ticker, depot_name)

def show_portfolio():
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
    verfuegbare_depots = ["Depot Neon", "Depot Yuh", "Anderes Depot"]

    with st.expander("➕ Neuen Trade oder Dividende erfassen", expanded=False):
        tab_trade, tab_div = st.tabs(["🛒 Kauf / Verkauf", "💸 Dividende verbuchen"])
        
        with tab_trade:
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
                            st.error(f"❌ Ungültiges Symbol: '{ticker}' konnte nicht gefunden werden.")
                        else:
                            wechselkurs = manuell_kurs if manuell_kurs > 0 else get_exchange_rate(waehrung, "CHF")
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
                            st.success("Trade erfolgreich verbucht!")
                            time.sleep(1.0)
                            st.rerun()
                    else:
                        st.error("Bitte fülle Ticker, Menge und Preis aus.")

        with tab_div:
            with st.form("div_form", border=False):
                st.markdown("**(1) Von welchem Titel hast du Geld erhalten?**")
                cd1, cd2 = st.columns(2)
                div_ticker = cd1.text_input("Ticker-Symbol (z.B. MSFT)", key="div_ticker")
                div_depot = cd2.selectbox("Aus welchem Depot?", verfuegbare_depots, key="div_depot")

                st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                st.markdown("**(2) Gutschrift & Steuern**")
                cd3, cd4, cd5 = st.columns(3)
                div_betrag = cd3.number_input("Brutto-Dividende (Fremdwährung)", min_value=0.00, format="%.2f", step=1.0)
                div_waehrung = cd4.selectbox("Währung der Dividende", ["USD", "CHF", "EUR"], key="div_waehrung")
                div_steuern = cd5.number_input("Quellensteuer/Spesen (in CHF)", min_value=0.00, format="%.2f", step=1.0)

                div_kurs = st.number_input("Wechselkurs (optional, falls anders als heute)", min_value=0.0000, format="%.4f", step=0.0100, key="div_kurs")

                st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                st.markdown("**(3) Zuordnung**")
                cd6, cd7 = st.columns(2)
                div_cash = cd6.selectbox("Gutschrift auf Konto", vermoegen_konten, key="div_cash")
                div_datum = cd7.date_input("Auszahlungsdatum", datetime.now(), key="div_datum")

                if st.form_submit_button("Dividende verbuchen", type="primary"):
                    if div_ticker and div_betrag > 0:
                        div_ticker = div_ticker.upper().strip()
                        wechselkurs_div = div_kurs if div_kurs > 0 else get_exchange_rate(div_waehrung, "CHF")
                        
                        brutto_chf = div_betrag * wechselkurs_div
                        netto_chf = brutto_chf - div_steuern
                        
                        datum_str = div_datum.strftime("%Y-%m-%d")
                        monat_str = div_datum.strftime("%Y-%m")

                        conn = get_connection()
                        conn.execute('''INSERT INTO portfolio_trades 
                            (konto, ticker, aktion, menge, kaufpreis_einzeln, waehrung, wechselkurs_kauf, datum, depot, gebuehren) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                            (div_cash, div_ticker, "Dividende", 0.0, div_betrag, div_waehrung, wechselkurs_div, datum_str, div_depot, div_steuern))
                        
                        if "Andere" not in div_cash:
                            trans_desc = f"Dividende {div_depot}: {div_ticker} (Abzug {div_steuern} CHF Steuern/Geb.)"
                            
                            if div_cash == "Yuh USD":
                                usd_rate = get_exchange_rate("USD", "CHF")
                                netto_usd = netto_chf / usd_rate
                                conn.execute('''INSERT INTO transaktionen (konto, typ, betrag, beschreibung, datum, monat, status, modus, link_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                    (div_cash, "Gutschrift", netto_usd, trans_desc, datum_str, monat_str, "geplant", "Einmalig", ""))
                            else:
                                conn.execute('''INSERT INTO transaktionen (konto, typ, betrag, beschreibung, datum, monat, status, modus, link_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                    (div_cash, "Gutschrift", netto_chf, trans_desc, datum_str, monat_str, "geplant", "Einmalig", ""))
                        
                        conn.commit()
                        conn.close()
                        upload_db()
                        st.success("Dividende erfolgreich verbucht!")
                        time.sleep(1.0)
                        st.rerun()
                    else:
                        st.error("Bitte fülle Ticker und Betrag aus.")

    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

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
        global_realisiert = 0.0  
        
        depot_summaries = {}

        for depot_name in alle_depots:
            df_depot = df_trades[df_trades['depot'] == depot_name]
            
            portfolio = {}
            for _, row in df_depot.iterrows():
                t = row['ticker']
                if t not in portfolio:
                    portfolio[t] = {'menge': 0.0, 'investiert_chf': 0.0, 'investiert_fremd': 0.0, 'gebuehren_total': 0.0, 'waehrung': row['waehrung'], 'realisiert_chf': 0.0, 'dividenden_chf': 0.0}
                
                geb = row.get('gebuehren', 0.0)
                
                if row['aktion'] == 'Kauf':
                    trade_wert_fremd = row['menge'] * row['kaufpreis_einzeln']
                    trade_wert_chf = trade_wert_fremd * row['wechselkurs_kauf']
                    portfolio[t]['menge'] += row['menge']
                    portfolio[t]['investiert_chf'] += trade_wert_chf 
                    portfolio[t]['investiert_fremd'] += trade_wert_fremd
                    portfolio[t]['gebuehren_total'] += geb
                    
                elif row['aktion'] == 'Verkauf':
                    trade_wert_fremd = row['menge'] * row['kaufpreis_einzeln']
                    trade_wert_chf = trade_wert_fremd * row['wechselkurs_kauf']
                    if portfolio[t]['menge'] > 0:
                        durchschnittskosten_chf = portfolio[t]['investiert_chf'] / portfolio[t]['menge']
                        durchschnittskosten_fremd = portfolio[t]['investiert_fremd'] / portfolio[t]['menge']
                        
                        cost_sold_chf = durchschnittskosten_chf * row['menge']
                        cost_sold_fremd = durchschnittskosten_fremd * row['menge']
                        
                        realisiert_trade = trade_wert_chf - cost_sold_chf - geb
                        portfolio[t]['realisiert_chf'] += realisiert_trade
                        
                        portfolio[t]['investiert_chf'] -= cost_sold_chf
                        portfolio[t]['investiert_fremd'] -= cost_sold_fremd
                        
                    portfolio[t]['menge'] -= row['menge']
                    portfolio[t]['gebuehren_total'] += geb 
                    
                elif row['aktion'] == 'Dividende':
                    div_brutto_fremd = row['kaufpreis_einzeln']
                    div_brutto_chf = div_brutto_fremd * row['wechselkurs_kauf']
                    div_netto_chf = div_brutto_chf - geb
                    portfolio[t]['dividenden_chf'] += div_netto_chf
                    portfolio[t]['realisiert_chf'] += div_netto_chf
                    portfolio[t]['gebuehren_total'] += geb 

            depot_investiert = 0.0
            depot_aktuell = 0.0
            depot_gebuehren = 0.0
            depot_realisiert = sum(d['realisiert_chf'] for d in portfolio.values()) 
            
            aktive_positionen = []
            geschlossene_positionen = [] 

            for t, data in portfolio.items():
                if data['menge'] > 0.00001 or data['menge'] < -0.00001: 
                    live_preis_fremd = get_current_price(t)
                    live_kurs_chf = get_exchange_rate(data['waehrung'], "CHF")
                    
                    wert_aktuell_chf = data['menge'] * live_preis_fremd * live_kurs_chf
                    
                    depot_investiert += data['investiert_chf']
                    depot_aktuell += wert_aktuell_chf
                    depot_gebuehren += data['gebuehren_total']
                    
                    aktive_positionen.append((t, data, live_preis_fremd, wert_aktuell_chf, live_kurs_chf))
                else:
                    if data['realisiert_chf'] != 0:
                        geschlossene_positionen.append((t, data))

            global_investiert += depot_investiert
            global_aktuell += depot_aktuell
            global_gebuehren += depot_gebuehren
            global_realisiert += depot_realisiert

            if aktive_positionen or geschlossene_positionen:
                depot_netto = depot_aktuell - depot_investiert - depot_gebuehren
                depot_perf_proz = (depot_netto / depot_investiert * 100) if depot_investiert > 0 else 0
                
                depot_summaries[depot_name] = {
                    'aktuell': depot_aktuell,
                    'netto': depot_netto,
                    'prozent': depot_perf_proz,
                    'realisiert': depot_realisiert
                }
                
                with st.expander(f"🏦 Depot: {depot_name} | Aktueller Wert: {format_num(depot_aktuell)} CHF", expanded=True):
                    st.markdown(f"**Investiert (Aktiv):** {format_num(depot_investiert)} CHF &nbsp;&nbsp;|&nbsp;&nbsp; **Buchgewinn (Laufend):** <span style='color:{'#28A745' if depot_netto >=0 else '#FF6B6B'}'>{format_num(depot_netto, 2, True)} CHF ({format_num(depot_perf_proz, 2, True)}%)</span> &nbsp;&nbsp;|&nbsp;&nbsp; **Bereits Realisiert:** <span style='color:{'#28A745' if depot_realisiert >=0 else '#FF6B6B'}'>{format_num(depot_realisiert, 2, True)} CHF</span>", unsafe_allow_html=True)
                    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                    
                    for pos in aktive_positionen:
                        t, data, live_preis_fremd, wert_aktuell_chf, live_kurs_chf = pos
                        
                        brutto_gewinn = wert_aktuell_chf - data['investiert_chf']
                        netto_gewinn = brutto_gewinn - data['gebuehren_total']
                        gewinn_prozent = (netto_gewinn / data['investiert_chf'] * 100) if data['investiert_chf'] > 0 else 0
                        
                        wert_aktuell_fremd = data['menge'] * live_preis_fremd
                        
                        with st.container(border=True):
                            st.markdown(f"<div style='font-size: 1.2rem; font-weight: bold; margin-bottom: -5px;'>{t}</div><div style='font-size: 0.9rem; color: gray;'>Bestand: {format_num(data['menge'], 4)}</div>", unsafe_allow_html=True)
                            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                            
                            c_m1, c_m2, c_m3 = st.columns(3)
                            c_m1.metric(f"Kurs ({data['waehrung']})", f"{format_num(live_preis_fremd, 4)}")
                            
                            if data['waehrung'] != "CHF":
                                gebuehren_fremd = data['gebuehren_total'] / live_kurs_chf if live_kurs_chf > 0 else 0
                                netto_gewinn_fremd = (wert_aktuell_fremd - data['investiert_fremd']) - gebuehren_fremd
                                gewinn_prozent_fremd = (netto_gewinn_fremd / data['investiert_fremd'] * 100) if data['investiert_fremd'] > 0 else 0
                                
                                c_m2.metric(f"Reiner Wert ({data['waehrung']})", f"{format_num(wert_aktuell_fremd)} {data['waehrung']}")
                                c_m2.markdown(f"<div style='margin-top: -15px; font-size: 0.85rem; color: #8A8F98;'>≈ {format_num(wert_aktuell_chf)} CHF</div>", unsafe_allow_html=True)
                                
                                c_m3.metric(f"Netto-Rendite ({data['waehrung']})", f"{format_num(netto_gewinn_fremd, 2, True)} {data['waehrung']}", f"{format_num(gewinn_prozent_fremd, 2, True)}%")
                                c_m3.markdown(f"<div style='margin-top: -15px; font-size: 0.85rem; color: #8A8F98;'>≈ {format_num(netto_gewinn, 2, True)} CHF ({format_num(gewinn_prozent, 2, True)}%)</div>", unsafe_allow_html=True)
                            else:
                                c_m2.metric("Reiner Wert (CHF)", f"{format_num(wert_aktuell_chf)} CHF")
                                c_m3.metric("Netto-Rendite", f"{format_num(netto_gewinn, 2, True)} CHF", f"{format_num(gewinn_prozent, 2, True)}%")
                            
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
                                            <div style='font-size: 1rem; font-weight: 600; color: {asset_color}; margin-top: 2px;'>{format_num(asset_gewinn_chf_heute, 2, True)} CHF</div>
                                        </div>
                                        <div style='flex: 1; min-width: 130px;'>
                                            <div style='font-size: 0.7rem; color: #8A8F98; text-transform: uppercase; letter-spacing: 0.5px;'>Währungseffekt ({data['waehrung']})</div>
                                            <div style='font-size: 1rem; font-weight: 600; color: {fx_color}; margin-top: 2px;'>{format_num(waehrungs_effekt_chf, 2, True)} CHF</div>
                                        </div>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                            
                            if data['dividenden_chf'] > 0:
                                st.markdown(f"<div style='margin-top: 12px; font-size: 0.85rem; color: #F1C40F;'><strong>💸 Erhaltene Dividenden: +{format_num(data['dividenden_chf'])} CHF</strong></div>", unsafe_allow_html=True)
                            
                            if data['realisiert_chf'] != 0 and (data['realisiert_chf'] - data['dividenden_chf']) != 0:
                                val_verkauf = data['realisiert_chf'] - data['dividenden_chf']
                                st.markdown(f"<div style='margin-top: 4px; font-size: 0.85rem; color: {'#2ECC71' if val_verkauf >= 0 else '#FF6B6B'};'><strong>💸 Realisiert durch Teilverkäufe: {format_num(val_verkauf, 2, True)} CHF</strong></div>", unsafe_allow_html=True)
                                
                            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                            
                            df_history = df_depot[df_depot['ticker'] == t].copy()
                            if st.button(f"📜 Historie & Details öffnen ({len(df_history)} Einträge)", key=f"btn_hist_{t}_{depot_name}", use_container_width=True):
                                show_history_dialog(t, depot_name, df_history, data['gebuehren_total'])
                                
                    if geschlossene_positionen:
                        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                        st.markdown("#### 🔒 Geschlossene Positionen (Komplett verkauft)")
                        for t, data in geschlossene_positionen:
                            r_color = "#2ECC71" if data['realisiert_chf'] >= 0 else "#FF6B6B"
                            st.markdown(f"- **{t}**: <span style='color: {r_color}; font-weight: bold;'>{format_num(data['realisiert_chf'], 2, True)} CHF Gewinn/Verlust</span>", unsafe_allow_html=True)

        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        st.divider()
        st.markdown("### 💰 Gesamtvermögen (Alle Depots)")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Investiert (Aktiv)", f"{format_num(global_investiert)} CHF")
        c2.metric("Aktueller Wert (Aktiv)", f"{format_num(global_aktuell)} CHF")
        
        gesamt_netto_chf = global_aktuell - global_investiert - global_gebuehren
        gesamt_perf_prozent = (gesamt_netto_chf / global_investiert * 100) if global_investiert > 0 else 0
        
        c3.metric("Buchgewinn (Laufend)", f"{format_num(gesamt_netto_chf, 2, True)} CHF", f"{format_num(gesamt_perf_prozent, 2, True)}%")
        c4.metric("Realisiert (Verkauf+Div.)", f"{format_num(global_realisiert, 2, True)} CHF")

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
                            value=f"{format_num(d_stats['aktuell'])} CHF", 
                            delta=f"{format_num(d_stats['netto'], 2, True)} CHF", 
                            label_visibility="collapsed"
                        )

    else:
        st.info("Dein Portfolio ist noch leer. Erfasse oben deinen ersten Trade!")
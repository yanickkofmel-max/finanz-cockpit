import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import time
from db_manager import get_connection
from utils.market_data import get_current_price, get_exchange_rate, search_ticker
from utils.drive_sync import upload_db
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

        html_card = f"""<div style='background-color: {bg_color}; padding: 12px; border-radius: 6px; border-left: 4px solid {border_color}; margin-bottom: 10px;'><div style='font-size: 0.9rem; margin-bottom: 4px;'><strong>{tr_row['datum']} &nbsp;|&nbsp; {tr_row['aktion']}</strong></div><div style='font-size: 0.85rem; color: #E2E8F0;'>{menge_str} <span style='color: gray;'>(Spesen/Steuern: {format_num(geb)} CHF)</span></div><div style='font-size: 0.95rem; font-weight: 600; margin-top: 6px;'>{aktion_text}: {format_num(total_chf)} CHF {fremd_str}</div>{realisiert_str}</div>"""
        
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

@st.dialog("⚡ Trade / Dividende erfassen", width="large")
def show_entry_dialog():
    vermoegen_konten = get_vermoegen_konten() + ["Andere (Keine Verrechnung)"]
    verfuegbare_depots = ["Depot Neon", "Depot Yuh", "Anderes Depot"]

    tab_trade, tab_div = st.tabs(["🛒 Kauf / Verkauf", "💸 Dividende verbuchen"])
    
    with tab_trade:
        st.markdown("**(0) Symbol suchen (falls unbekannt)**")
        c_s1, c_s2 = st.columns([3, 1], vertical_alignment="bottom")
        suchbegriff = c_s1.text_input("Name der Firma oder Kryptowährung", placeholder="z.B. Ripple, Novartis")
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
            ticker = c2.text_input("Ticker-Symbol", help="Beispiele: NOVN.SW, AAPL, XRP-USD")
            menge = c3.number_input("Menge (Stück)", min_value=0.0000, format="%.4f", step=1.0)

            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
            st.markdown("**(2) Kosten & Gebühren**")
            c4, c5, c6 = st.columns(3)
            preis = c4.number_input("Preis pro Stück (Fremdwährung)", min_value=0.00, format="%.4f", step=1.0)
            waehrung = c5.selectbox("Währung des Wertpapiers", ["USD", "CHF", "EUR"])
            gebuehren = c6.number_input("Total Gebühren/Spesen (in CHF)", min_value=0.00, format="%.2f", step=1.0)

            manuell_kurs = st.number_input("Wechselkurs (optional, falls anders als heute)", min_value=0.0000, format="%.4f", step=0.0100)

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
                        
                        gesamt_cashflow_chf = reiner_wert_chf + gebuehren if aktion == "Kauf" else reiner_wert_chf - gebuehren
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
                                trans_betrag = (-gesamt_cashflow_chf / usd_rate) if aktion == "Kauf" else (gesamt_cashflow_chf / usd_rate)
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
                            conn.execute('''INSERT INTO transaktionen (konto, typ, betrag, beschreibung, datum, monat, status, modus, link_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                (div_cash, "Gutschrift", netto_chf / usd_rate, trans_desc, datum_str, monat_str, "geplant", "Einmalig", ""))
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

def show_portfolio():
    # ---> NEUES CSS-DESIGN FÜR DIE KACHELN <---
    st.markdown("""
        <style>
        .asset-card {
            background: linear-gradient(145deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.01) 100%);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 18px;
            margin-bottom: 15px;
            transition: transform 0.2s ease, border-color 0.2s ease;
        }
        .asset-card:hover {
            border-color: rgba(46, 204, 113, 0.4);
            transform: translateY(-2px);
        }
        .ticker-badge {
            background: rgba(46, 204, 113, 0.15);
            color: #2ECC71;
            border: 1px solid rgba(46, 204, 113, 0.3);
            padding: 4px 8px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 0.85rem;
            letter-spacing: 0.5px;
        }
        .depot-badge {
            font-size: 0.7rem;
            color: #8A8F98;
            background: rgba(255,255,255,0.05);
            padding: 3px 6px;
            border-radius: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .asset-icon {
            width: 30px;
            height: 30px;
            border-radius: 50%;
            object-fit: cover;
            background: #fff;
            padding: 2px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        }
        </style>
    """, unsafe_allow_html=True)

    conn = get_connection()
    conn.execute("UPDATE portfolio_trades SET depot = 'Depot Neon' WHERE depot = 'Neon Invest'")
    conn.execute("UPDATE portfolio_trades SET depot = 'Depot Yuh' WHERE depot = 'Yuh Invest'")
    conn.execute("UPDATE transaktionen SET beschreibung = REPLACE(beschreibung, 'Trade Neon Invest:', 'Trade Depot Neon:') WHERE beschreibung LIKE 'Trade Neon Invest:%'")
    conn.execute("UPDATE transaktionen SET beschreibung = REPLACE(beschreibung, 'Trade Yuh Invest:', 'Trade Depot Yuh:') WHERE beschreibung LIKE 'Trade Yuh Invest:%'")
    conn.commit()
    conn.close()

    col_h1, col_h2 = st.columns([4, 1], vertical_alignment="center")
    with col_h1:
        st.title("📈 Aktien & Krypto Portfolio")
        st.caption("Echtzeit-Analyse deines Vermögens")
    with col_h2:
        if st.button("⚡ Trade / Div. buchen", use_container_width=True, type="primary"):
            show_entry_dialog()

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    conn = get_connection()
    df_trades = pd.read_sql("SELECT * FROM portfolio_trades ORDER BY datum ASC", conn)
    conn.close()

    if df_trades.empty:
        st.info("Dein Portfolio ist noch leer. Klicke oben rechts auf 'Trade / Div. buchen', um zu starten!")
        return

    if 'depot' not in df_trades.columns:
        df_trades['depot'] = 'Depot Neon'
        
    alle_depots = df_trades['depot'].unique()
    
    global_investiert = 0.0
    global_aktuell = 0.0
    global_gebuehren = 0.0
    global_realisiert = 0.0  
    
    depot_totals = {}
    active_cards = []
    closed_cards = []

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
                div_netto_chf = (row['kaufpreis_einzeln'] * row['wechselkurs_kauf']) - geb
                portfolio[t]['dividenden_chf'] += div_netto_chf
                portfolio[t]['realisiert_chf'] += div_netto_chf
                portfolio[t]['gebuehren_total'] += geb 

        depot_investiert = 0.0
        depot_aktuell = 0.0
        depot_gebuehren = 0.0
        depot_realisiert = sum(d['realisiert_chf'] for d in portfolio.values())

        for t, data in portfolio.items():
            if data['menge'] > 0.00001 or data['menge'] < -0.00001: 
                live_preis_fremd = get_current_price(t)
                live_kurs_chf = get_exchange_rate(data['waehrung'], "CHF")
                wert_aktuell_chf = data['menge'] * live_preis_fremd * live_kurs_chf
                
                depot_investiert += data['investiert_chf']
                depot_aktuell += wert_aktuell_chf
                depot_gebuehren += data['gebuehren_total']
                
                brutto_gewinn = wert_aktuell_chf - data['investiert_chf']
                netto_gewinn = brutto_gewinn - data['gebuehren_total']
                gewinn_prozent = (netto_gewinn / data['investiert_chf'] * 100) if data['investiert_chf'] > 0 else 0
                
                active_cards.append({
                    'depot': depot_name,
                    'ticker': t,
                    'menge': data['menge'],
                    'waehrung': data['waehrung'],
                    'investiert_chf': data['investiert_chf'],
                    'investiert_fremd': data['investiert_fremd'],
                    'gebuehren_total': data['gebuehren_total'],
                    'dividenden_chf': data['dividenden_chf'],
                    'realisiert_chf': data['realisiert_chf'],
                    'live_preis_fremd': live_preis_fremd,
                    'wert_aktuell_chf': wert_aktuell_chf,
                    'netto_gewinn': netto_gewinn,
                    'gewinn_prozent': gewinn_prozent
                })
            else:
                if data['realisiert_chf'] != 0:
                    closed_cards.append({
                        'depot': depot_name,
                        'ticker': t,
                        'realisiert_chf': data['realisiert_chf']
                    })

        depot_totals[depot_name] = {
            'investiert': depot_investiert,
            'aktuell': depot_aktuell,
            'gebuehren': depot_gebuehren,
            'realisiert': depot_realisiert
        }

        global_investiert += depot_investiert
        global_aktuell += depot_aktuell
        global_gebuehren += depot_gebuehren
        global_realisiert += depot_realisiert

    tab_dash, tab_assets, tab_hist = st.tabs(["📊 Dashboard & Analytics", "💼 Meine Bestände", "📜 Gesamthistorie"])

    with tab_dash:
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        filter_options = ["Alle Depots"] + list(alle_depots)
        selected_depot_filter = st.radio("Ansicht filtern:", filter_options, horizontal=True)
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

        if selected_depot_filter == "Alle Depots":
            dash_invest = global_investiert
            dash_aktuell = global_aktuell
            dash_geb = global_gebuehren
            dash_realized = global_realisiert
            filtered_cards = active_cards
        else:
            dash_invest = depot_totals[selected_depot_filter]['investiert']
            dash_aktuell = depot_totals[selected_depot_filter]['aktuell']
            dash_geb = depot_totals[selected_depot_filter]['gebuehren']
            dash_realized = depot_totals[selected_depot_filter]['realisiert']
            filtered_cards = [c for c in active_cards if c['depot'] == selected_depot_filter]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Investiert (Aktiv)", f"{format_num(dash_invest)} CHF")
        c2.metric("Aktueller Wert (Aktiv)", f"{format_num(dash_aktuell)} CHF")
        
        dash_netto_chf = dash_aktuell - dash_invest - dash_geb
        dash_perf_prozent = (dash_netto_chf / dash_invest * 100) if dash_invest > 0 else 0
        
        c3.metric("Buchgewinn (Laufend)", f"{format_num(dash_netto_chf, 2, True)} CHF", f"{format_num(dash_perf_prozent, 2, True)}%")
        c4.metric("Realisiert (Verkauf+Div.)", f"{format_num(dash_realized, 2, True)} CHF")
        
        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        
        if filtered_cards:
            df_plot = pd.DataFrame(filtered_cards)
            c_left, c_right = st.columns(2)
            
            with c_left:
                st.markdown("#### 🍩 Asset Allocation")
                df_donut = df_plot.groupby('ticker')['wert_aktuell_chf'].sum().reset_index()
                fig_donut = px.pie(df_donut, values='wert_aktuell_chf', names='ticker', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_donut.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#FFFFFF', margin=dict(t=20, b=20, l=10, r=10))
                st.plotly_chart(fig_donut, use_container_width=True)
                
            with c_right:
                st.markdown("#### 🏆 Profit Ranking (CHF)")
                df_bar = df_plot.groupby('ticker')['netto_gewinn'].sum().reset_index()
                df_bar = df_bar.sort_values(by='netto_gewinn', ascending=True)
                fig_bar = px.bar(df_bar, x='netto_gewinn', y='ticker', orientation='h', color='netto_gewinn', color_continuous_scale=['#FF6B6B', '#2ECC71'])
                fig_bar.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#FFFFFF', coloraxis_showscale=False, xaxis_title="Netto Gewinn (CHF)", yaxis_title="")
                st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info(f"Keine aktiven Positionen für die Ansicht '{selected_depot_filter}'.")

    with tab_assets:
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        
        if not active_cards and not closed_cards:
            st.info("Aktuell keine Positionen im Depot.")
        else:
            for current_depot in alle_depots:
                depot_active = [c for c in active_cards if c['depot'] == current_depot]
                depot_closed = [c for c in closed_cards if c['depot'] == current_depot]
                
                if depot_active or depot_closed:
                    st.markdown(f"### 🏢 {current_depot}")
                    st.divider()
                    
                    if depot_active:
                        cols = st.columns(3)
                        for idx, card in enumerate(depot_active):
                            with cols[idx % 3]:
                                color = "#2ECC71" if card['netto_gewinn'] >= 0 else "#FF6B6B"
                                
                                base_ticker = card['ticker'].split('-')[0].split('.')[0].upper()
                                primary_icon = f"https://assets.coincap.io/assets/icons/{base_ticker.lower()}@2x.png"
                                fallback_icon = f"https://ui-avatars.com/api/?name={base_ticker}&background=2b2b36&color=2ECC71&rounded=true&bold=true"
                                
                                fx_html = ""
                                if card['waehrung'] != "CHF":
                                    asset_gewinn_fremd = (card['menge'] * card['live_preis_fremd']) - card['investiert_fremd']
                                    live_kurs_chf = get_exchange_rate(card['waehrung'], "CHF")
                                    asset_gewinn_chf_heute = asset_gewinn_fremd * live_kurs_chf
                                    waehrungs_effekt_chf = card['netto_gewinn'] + card['gebuehren_total'] - asset_gewinn_chf_heute
                                    
                                    fx_color = "#2ECC71" if waehrungs_effekt_chf >= 0 else "#FF6B6B"
                                    asset_color = "#2ECC71" if asset_gewinn_chf_heute >= 0 else "#FF6B6B"
                                    
                                    fx_html = f"<div style='background: rgba(0,0,0,0.2); border-radius: 6px; padding: 10px; margin-top: 12px; border: 1px solid rgba(255,255,255,0.05);'><div style='display: flex; justify-content: space-between; margin-bottom: 6px;'><span style='font-size: 0.7rem; color: #8A8F98; text-transform: uppercase;'>Kursgewinn</span><span style='font-size: 0.85rem; font-weight: bold; color: {asset_color};'>{format_num(asset_gewinn_chf_heute, 2, True)} CHF</span></div><div style='display: flex; justify-content: space-between;'><span style='font-size: 0.7rem; color: #8A8F98; text-transform: uppercase;'>FX-Effekt ({card['waehrung']})</span><span style='font-size: 0.85rem; font-weight: bold; color: {fx_color};'>{format_num(waehrungs_effekt_chf, 2, True)} CHF</span></div></div>"

                                div_html = f"<div style='color: #F1C40F; font-size: 0.8rem; font-weight: bold; margin-top: 10px;'>💸 Dividenden: +{format_num(card['dividenden_chf'])} CHF</div>" if card['dividenden_chf'] > 0 else ""
                                
                                val_verkauf = card['realisiert_chf'] - card['dividenden_chf']
                                realized_html = f"<div style='color: {'#2ECC71' if val_verkauf >= 0 else '#FF6B6B'}; font-size: 0.8rem; margin-top: 4px;'>Realisiert (Verkauf): {format_num(val_verkauf, 2, True)} CHF</div>" if val_verkauf != 0 else ""

                                # ---> HTML KARTEN-AUFBAU (KUGELSICHER OHNE ZEILENUMBRÜCHE) <---
                                html_card = f"""
                                <div class="asset-card">
                                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                                        <div style="display: flex; align-items: center; gap: 10px;">
                                            <div class="ticker-badge">{card['ticker']}</div>
                                            <img src="{primary_icon}" onerror="this.onerror=null; this.src='{fallback_icon}';" class="asset-icon">
                                        </div>
                                        <div style="text-align: right;">
                                            <div class="depot-badge" style="margin:0;">{card['depot']}</div>
                                            <div style="color: #8A8F98; font-size: 0.8rem; margin-top: 5px; font-weight: 500;">{format_num(card['menge'], 4)} Stück</div>
                                        </div>
                                    </div>
                                    <div style="font-size: 1.6rem; font-weight: 700; line-height: 1.2; color: #FFFFFF;">
                                        {format_num(card['live_preis_fremd'], 4)} <span style="font-size: 0.9rem; color: #8A8F98; font-weight: 500;">{card['waehrung']}</span>
                                    </div>
                                    <div style="font-size: 1.1rem; font-weight: 600; color: {color}; margin-top: 2px; padding-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                        {format_num(card['netto_gewinn'], 2, True)} CHF ({format_num(card['gewinn_prozent'], 2, True)}%)
                                    </div>
                                    <div style="margin-top: 12px; display: flex; justify-content: space-between; font-size: 0.9rem;">
                                        <span style="color: #8A8F98; font-weight: 500;">Wert in CHF</span>
                                        <span style="font-weight: 700; color: #FFFFFF;">{format_num(card['wert_aktuell_chf'])} CHF</span>
                                    </div>
                                    {fx_html}{div_html}{realized_html}
                                </div>
                                """.replace('\n', '')
                                
                                st.markdown(html_card, unsafe_allow_html=True)
                                
                                df_depot_hist = df_trades[df_trades['depot'] == card['depot']]
                                df_ticker_hist = df_depot_hist[df_depot_hist['ticker'] == card['ticker']].copy()
                                if st.button("📜 Details & Historie", key=f"btn_{card['ticker']}_{card['depot']}", use_container_width=True):
                                    show_history_dialog(card['ticker'], card['depot'], df_ticker_hist, card['gebuehren_total'])
                                    
                    if depot_closed:
                        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                        st.markdown("#### 🔒 Geschlossene Positionen")
                        for card in depot_closed:
                            r_color = "#2ECC71" if card['realisiert_chf'] >= 0 else "#FF6B6B"
                            st.markdown(f"- **{card['ticker']}**: <span style='color: {r_color}; font-weight: bold;'>{format_num(card['realisiert_chf'], 2, True)} CHF Gewinn/Verlust</span>", unsafe_allow_html=True)

                    st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)

    with tab_hist:
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("#### Logbuch aller Transaktionen")
        st.caption("Chronologische Übersicht aller Käufe, Verkäufe und Dividenden über alle Depots hinweg.")
        st.divider()
        
        for _, row in df_trades.iloc[::-1].iterrows():
            c_h1, c_h2, c_h3, c_h4, c_h5 = st.columns([1.5, 2, 2, 2, 1])
            c_h1.write(f"**{row['datum']}**")
            
            icon = "🛒" if row['aktion'] in ["Kauf", "Verkauf"] else "💸"
            c_h2.write(f"{icon} **{row['aktion']}** {row['ticker']}")
            c_h3.write(f"{row['depot']}")
            
            val = row['menge'] * row['kaufpreis_einzeln'] if row['aktion'] != "Dividende" else row['kaufpreis_einzeln']
            c_h4.write(f"{format_num(val)} {row['waehrung']}")
            
            if c_h5.button("🗑️", key=f"del_global_hist_{row['id']}", help="Diesen Trade unwiderruflich löschen"):
                delete_trade(row['id'], row['aktion'], row['menge'], row['ticker'], row['depot'], row['gebuehren'], row['datum'])
            st.markdown("<div style='margin-bottom: -15px;'></div>", unsafe_allow_html=True)
            st.divider()
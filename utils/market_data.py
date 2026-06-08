import yfinance as yf
import pandas as pd
import urllib.request
import urllib.parse
import json

def get_current_price(ticker):
    try:
        asset = yf.Ticker(ticker)
        todays_data = asset.history(period='1d')
        if not todays_data.empty:
            return float(todays_data['Close'].iloc[0])
        else:
            return 0.0
    except Exception as e:
        print(f"Fehler beim Abrufen von {ticker}: {e}")
        return 0.0

def get_exchange_rate(from_currency="USD", to_currency="CHF"):
    if from_currency == to_currency:
        return 1.0
    ticker = f"{from_currency}{to_currency}=X"
    try:
        rate_data = yf.Ticker(ticker).history(period='1d')
        if not rate_data.empty:
            return float(rate_data['Close'].iloc[0])
        else:
            return 1.0
    except:
        return 1.0

def search_ticker(query):
    """Sucht live auf Yahoo Finance nach dem passenden Ticker-Symbol."""
    if not query:
        return []
    
    query_encoded = urllib.parse.quote(query)
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query_encoded}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            quotes = data.get('quotes', [])
            results = []
            for q in quotes:
                sym = q.get('symbol')
                name = q.get('shortname') or q.get('longname') or 'Unbekannt'
                typ = q.get('quoteType', '')
                exch = q.get('exchange', '')
                if sym:
                    results.append({"symbol": sym, "name": name, "info": f"{typ}, {exch}"})
            return results[:6] # Zeigt die besten 6 Treffer
    except Exception as e:
        return [{"symbol": "Fehler", "name": "Suche fehlgeschlagen", "info": str(e)}]
import pandas as pd
from finvizfinance.quote import finvizfinance
import time
import glob
import os
import datetime

# --- CONFIGURARE ---
TICKERS_FILE = 'tickers.txt'
OUTPUT_CSV = 'market_scan_extended.csv'
OUTPUT_HTML = 'index.html'

def load_tickers(filename=TICKERS_FILE):
    try:
        with open(filename, 'r') as f:
            tickers = [line.strip() for line in f if line.strip()]
        return tickers
    except FileNotFoundError:
        print(f"Eroare: {filename} lipsește.")
        return []

# --- DATA CLEANING (Robust) ---
def clean_value(value):
    """Elimină caracterele nedorite ($ , %)"""
    if not value or value == '-': return ""
    return str(value).replace('$', '').replace('%', '').replace(',', '').strip()

def parse_float(value):
    try: return float(clean_value(value))
    except: return 0.0

def parse_percent(value):
    try: return float(clean_value(value))
    except: return 0.0

def parse_volume(v_str):
    cleaned = clean_value(v_str)
    if not cleaned: return 0
    mult = 1
    if 'M' in v_str: mult = 1_000_000; cleaned = cleaned.replace('M','')
    elif 'B' in v_str: mult = 1_000_000_000; cleaned = cleaned.replace('B','')
    elif 'K' in v_str: mult = 1_000; cleaned = cleaned.replace('K','')
    try: return float(cleaned) * mult
    except: return 0

# --- MARKET OVERVIEW (Finviz) ---
def get_market_indices():
    indices = ['SPY', 'QQQ', 'DIA', 'IWM']
    data = []
    print("\nPreiau date Market Overview (Finviz)...")
    for t in indices:
        try:
            stock = finvizfinance(t)
            fund = stock.ticker_fundament()
            data.append({
                'Symbol': t,
                'Price': parse_float(fund.get('Price', '0')),
                'Nx_Change': parse_percent(fund.get('Change', '0'))
            })
            time.sleep(0.3)
        except Exception as e:
            print(f"Eroare index {t}: {e}")
    return data

# --- ANALIZĂ TICKER ---
def analyze_ticker(ticker):
    try:
        stock = finvizfinance(ticker)
        fund = stock.ticker_fundament()
        
        # Extragere date brute
        price = parse_float(fund.get('Price', '0'))
        target = parse_float(fund.get('Target Price', '0'))
        rsi = parse_float(fund.get('RSI (14)', '0'))
        atr = parse_float(fund.get('ATR', '0'))
        recom = parse_float(fund.get('Recom', '3.0'))
        sma50_chg = parse_percent(fund.get('SMA50', '0'))
        sma200_chg = parse_percent(fund.get('SMA200', '0'))
        
        # Calcule SMA
        sma50 = price / (1 + sma50_chg/100) if sma50_chg != -100 else 0
        sma200 = price / (1 + sma200_chg/100) if sma200_chg != -100 else 0
        
        # Trend Logic
        trend = "Neutral"
        if sma50 > sma200:
            trend = "Strong Bullish" if price > sma50 else "Bullish Pullback"
        elif sma50 < sma200:
            trend = "Bearish" if price < sma50 else "Bearish Bounce"
            
        # Consensus
        market_consensus = "Hold"
        if recom <= 1.5: market_consensus = "Strong Buy"
        elif recom <= 2.5: market_consensus = "Buy"
        elif recom > 4.5: market_consensus = "Strong Sell"
        elif recom > 3.5: market_consensus = "Sell"
        
        # Stop Loss Sugerat (2x ATR)
        stop_loss = round(price - (2 * atr), 2) if atr > 0 else 0
        
        # To Target %
        to_target = round(((target - price) / price) * 100, 2) if price > 0 and target > 0 else 0.0

        return {
            'TICKER': ticker,
            'PRICE': price,
            'TARGET': target,
            'TO TARGET %': to_target,
            'CONSENSUS': market_consensus,
            'INDUSTRY': fund.get('Industry', 'Unknown'),
            'TREND': trend,
            'RSI': rsi,
            'STATUS': "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral",
            'ATR': atr,
            'SUGGESTED STOP': stop_loss,
            'SMA 50': round(sma50, 2),
            'SMA 200': round(sma200, 2)
        }
    except Exception as e:
        print(f"Eroare {ticker}: {e}")
        return None

# --- GENERARE DASHBOARD HTML ---
def generate_html(df, market_data):
    # Market Cards
    cards_html = ""
    for m in market_data:
        color = "text-success" if m['Nx_Change'] >= 0 else "text-danger"
        name_map = {'SPY': 'S&P 500', 'QQQ': 'Nasdaq 100', 'DIA': 'Dow Jones', 'IWM': 'Russell 2000'}
        display_name = name_map.get(m['Symbol'], m['Symbol'])
        
        cards_html += f"""
        <div class="col-md-3 mb-3">
            <div class="card bg-dark border-secondary text-white h-100">
                <div class="card-body text-center">
                    <h6 class="text-muted">{display_name} ({m['Symbol']})</h6>
                    <h3 class="my-2">${m['Price']}</h3>
                    <span class="{color} fw-bold">{m['Nx_Change']}%</span>
                </div>
            </div>
        </div>"""

    # Table Rows
    rows_html = ""
    for _, row in df.iterrows():
        trend_color = "text-warning"
        if "Strong Bullish" in row['TREND']: trend_color = "text-success"
        elif "Bearish" in row['TREND']: trend_color = "text-danger"
        
        target_color = "text-success" if row['TO TARGET %'] > 0 else "text-danger"
        
        rows_html += f"""
        <tr>
            <td class="fw-bold">{row['TICKER']}</td>
            <td>${row['PRICE']}</td>
            <td>${row['TARGET']}</td>
            <td class="{target_color}">{row['TO TARGET %']}%</td>
            <td>{row['CONSENSUS']}</td>
            <td>{row['INDUSTRY']}</td>
            <td class="{trend_color}">{row['TREND']}</td>
            <td>{row['RSI']}</td>
            <td class="text-danger">${row['SUGGESTED STOP']}</td>
        </tr>"""

    html = f"""
    <!DOCTYPE html>
    <html lang="en" data-bs-theme="dark">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Market Scanner Pro</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdn.datatables.net/1.13.4/css/dataTables.bootstrap5.min.css" rel="stylesheet">
        <style>
            body {{ background-color: #0f0f0f; font-family: 'Segoe UI', sans-serif; }}
            .card {{ box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
            .nav-tabs .nav-link.active {{ background-color: #1f1f1f; color: #4caf50; border-bottom-color: #1f1f1f; }}
            .nav-tabs .nav-link {{ color: #aaa; }}
        </style>
    </head>
    <body class="p-4">
        <div class="container-fluid">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h2 class="text-success">Market Scanner <span class="text-white fw-light">Pro</span></h2>
                <small class="text-muted">Updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</small>
            </div>

            <ul class="nav nav-tabs mb-4" id="myTab" role="tablist">
                <li class="nav-item"><button class="nav-link active" data-bs-target="#market" data-bs-toggle="tab">Market Overview</button></li>
                <li class="nav-item"><button class="nav-link" data-bs-target="#portfolio" data-bs-toggle="tab">Portofoliu Activ</button></li>
                <li class="nav-item"><button class="nav-link" data-bs-target="#watchlist" data-bs-toggle="tab">Watchlist</button></li>
            </ul>

            <div class="tab-content">
                <!-- MARKET OVERVIEW -->
                <div class="tab-pane fade show active" id="market">
                    <div class="row">{cards_html}</div>
                </div>

                <!-- PORTFOLIO PLACEHOLDER -->
                <div class="tab-pane fade" id="portfolio">
                    <div class="alert alert-info border-secondary bg-dark text-white">
                        Conectarea portofoliului nu este încă configurată. Adăugați poziții manual în versiunile viitoare.
                    </div>
                </div>

                <!-- WATCHLIST TABLE -->
                <div class="tab-pane fade" id="watchlist">
                    <div class="card bg-dark border-secondary p-3">
                        <table id="scanTable" class="table table-dark table-hover w-100">
                            <thead>
                                <tr>
                                    <th>Ticker</th>
                                    <th>Price</th>
                                    <th>Target</th>
                                    <th>To Target %</th>
                                    <th>Consensus</th>
                                    <th>Industry</th>
                                    <th>Trend</th>
                                    <th>RSI</th>
                                    <th>Sug. Stop</th>
                                </tr>
                            </thead>
                            <tbody>{rows_html}</tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script src="https://cdn.datatables.net/1.13.4/js/jquery.dataTables.min.js"></script>
        <script src="https://cdn.datatables.net/1.13.4/js/dataTables.bootstrap5.min.js"></script>
        <script>
            $(document).ready(function() {{
                $('#scanTable').DataTable({{
                    "pageLength": 25,
                    "order": [[3, "desc"]] // Sort by To Target %
                }});
            }});
        </script>
    </body>
    </html>
    """
    with open(OUTPUT_HTML, 'w') as f: f.write(html)
    print(f"Dashboard generat: {OUTPUT_HTML}")

# --- MAIN ---
def main():
    print("--- Market Scanner v2.0 (Finviz Only) ---")
    
    # Cleanup
    for f in glob.glob("*.csv"):
        try: os.remove(f); print(f"Sters: {f}")
        except: pass
        
    tickers = load_tickers()
    if not tickers: return

    print(f"Scanare {len(tickers)} simboluri...")
    results = []
    
    for t in tickers:
        print(f"Analizez {t}...", end="\r")
        res = analyze_ticker(t)
        if res: results.append(res)
        time.sleep(0.5)

    market_data = get_market_indices()
    
    if results:
        df = pd.DataFrame(results)
        # Selectare coloane finale
        cols = ['TICKER', 'PRICE', 'TARGET', 'TO TARGET %', 'CONSENSUS', 'INDUSTRY', 
                'TREND', 'RSI', 'STATUS', 'ATR', 'SUGGESTED STOP', 'SMA 50', 'SMA 200']
        final_df = df[[c for c in cols if c in df.columns]]
        
        final_df.to_csv(OUTPUT_CSV, index=False)
        print(f"\nCSV Salvat: {OUTPUT_CSV}")
        
        generate_html(final_df, market_data)
        print("\nScanare completă! Verifică index.html.")
    else:
        print("\nNu s-au găsit date.")

if __name__ == "__main__":
    main()

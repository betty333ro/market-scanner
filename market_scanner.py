import pandas as pd
from finvizfinance.quote import finvizfinance
import yfinance as yf
import time
import glob
import os
import datetime
import requests
import math

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

# --- SVG SPARKLINE GENERATOR ---
def generate_sparkline(data_list, color="#4caf50", width=120, height=40):
    if not data_list or len(data_list) < 2:
        return ""
    
    min_val = min(data_list)
    max_val = max(data_list)
    val_range = max_val - min_val if max_val != min_val else 1
    
    points = []
    step = width / (len(data_list) - 1)
    
    for i, val in enumerate(data_list):
        x = i * step
        # Flip Y axis because SVG 0 is top
        y = height - ((val - min_val) / val_range * height)
        points.append(f"{x},{y}")
        
    polyline = f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2" />'
    return f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">{polyline}</svg>'

# --- DATA FETCHING (ADVANCED) ---
def get_crypto_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1")
        data = r.json()
        return int(data['data'][0]['value'])
    except:
        return 50

def get_market_cortex_data():
    print("\nPreiau date Market Cortex (yfinance)...")
    
    # Mapare Ticker Afisat -> Ticker Yahoo
    indices = {
        'VIX3M': '^VIX3M',
        'VIX': '^VIX',
        'VIX1D': '^VIX1D', # Poate lipsi
        'VIX9D': '^VIX9D',
        'VXN': '^VXN',     # Nasdaq Vol
        'LTV': '^VIX6M',   # Long Term Vol (6 Months)
        'SKEW': '^SKEW',
        'MOVE': '^MOVE',   # ICE BofA MOVE Index
        'GVZ': '^GVZ',     # Gold Vol
        'OVX': '^OVX',     # Oil Vol
        'SPX': '^GSPC'
    }
    
    cortex_data = {}
    
    # Batch download pentru eficienta
    tickers_list = list(indices.values())
    try:
        # Preluam date pe 1 luna pentru sparklines
        data = yf.download(tickers_list, period="1mo", interval="1d", progress=False)['Close']
        
        # Procesare fiecare index
        for name, ticker in indices.items():
            try:
                # Extragem seria de date (handle NaN)
                series = data[ticker].dropna()
                
                if series.empty:
                    # Fallback daca nu exista in batch (uneori pt indici exotici)
                    raise ValueError("Empty series")
                
                current_price = series.iloc[-1]
                prev_price = series.iloc[-2] if len(series) > 1 else current_price
                change = current_price - prev_price
                
                # Sparkline data (normalizata pt vizualizare)
                spark_data = series.tolist()
                
                # Determinare Sentiment/Status (Logica simpla bazata pe medii)
                status = "NORMAL"
                status_color = "#888" # Grey
                
                # Logica specifica VIX
                if "VIX" in name or name == "VXN":
                    if current_price < 15: status = "COMPLACENCY"; status_color = "#4caf50"
                    elif current_price < 20: status = "NORMAL"; status_color = "#888"
                    elif current_price < 30: status = "FEAR"; status_color = "#ff9800"
                    else: status = "PANIC"; status_color = "#f44336"
                elif name == "SKEW":
                    if current_price > 145: status = "PANIC (BS)"; status_color = "#f44336" # Black Swan Risk
                    else: status = "NORMAL"; status_color = "#888"
                elif name == "SPX":
                   status = f"{int(current_price)}"
                   status_color = "#4caf50" if change > 0 else "#f44336"

                color = "#4caf50" if change <= 0 else "#f44336" # Volatilitate in scadere = Bine (Verde)
                if name == "SPX": # Pt SPX invers: crestere = Bine
                    color = "#4caf50" if change >= 0 else "#f44336"

                cortex_data[name] = {
                    'value': round(current_price, 2),
                    'change': round(change, 2),
                    'sparkline': generate_sparkline(spark_data, color=color),
                    'status': status,
                    'status_color': status_color,
                    'text_color': "text-success" if color=="#4caf50" else "text-danger"
                }
            except Exception as e:
                # Fallback pt date lipsa
                cortex_data[name] = {
                    'value': 0.0, 'change': 0.0, 'sparkline': "", 'status': "N/A", 'status_color': "#444", 'text_color': "text-muted"
                }

        # CRYPTO FEAR (External API)
        fng = get_crypto_fear_greed()
        fng_color = "#f44336" if fng < 25 else "#4caf50" if fng > 60 else "#ff9800"
        fng_status = "EXTREME FEAR" if fng < 25 else "GREED" if fng > 60 else "NEUTRAL"
        
        cortex_data['CRYPTO FEAR'] = {
            'value': fng,
            'change': 0.0, # Nu avem istoric zi vs zi usor
            'sparkline': "", # Placeholder
            'status': fng_status,
            'status_color': "#888",
            'text_color': "text-success" if fng > 50 else "text-danger" # Doar coloram textul
        }
        
    except Exception as e:
        print(f"Eroare critica fetching yfinance: {e}")

    return cortex_data

def calculate_verdict(cortex):
    # Logica 'Antigravity' simplificata
    
    # 1. Term Structure (VIX3M / VIX)
    try:
        vix = cortex['VIX']['value']
        vix3m = cortex['VIX3M']['value']
        term_structure = round(vix3m / vix, 2) if vix > 0 else 1.0
    except:
        term_structure = 1.0

    term_text = "Contango (Normal)"
    term_color = "text-success"
    if term_structure < 1.0:
        term_text = "Backwardation (PANIC)"
        term_color = "text-danger"
    elif term_structure < 1.1:
        term_text = "Flat (Caution)"
        term_color = "text-warning"
        
    # 2. Bullish Probability (Fictiv - bazat pe VIX si SPX status)
    # Daca VIX scade si SPX creste -> Bullish
    bull_prob = 50
    if cortex['VIX']['change'] < 0: bull_prob += 10
    if cortex['VIX3M']['change'] < 0: bull_prob += 10
    if cortex['GVZ']['change'] < 0: bull_prob += 5
    if cortex['SPX']['change'] > 0: bull_prob += 10
    
    # Cap la 95% si 5%
    bull_prob = max(5, min(95, bull_prob))
    bear_prob = 100 - bull_prob
    
    # 3. AI Sentiment (Mockup pt moment)
    sentiment = 65 
    
    verdict = "Neutral"
    if bull_prob > 60: verdict = "Bullish"
    if bull_prob > 80: verdict = "Strong Bullish"
    if bear_prob > 60: verdict = "Bearish"
    if bear_prob > 80: verdict = "Strong Bearish"

    return {
        'term_val': term_structure,
        'term_text': term_text,
        'term_color': term_color,
        'bull_prob': bull_prob,
        'bear_prob': bear_prob,
        'verdict': verdict,
        'sentiment': sentiment
    }

# --- EXISTING ANALYZE TICKER ---
# (Pastram functia existenta pentru tabelul Watchlist, e buna)
def clean_value(value):
    if not value or value == '-': return ""
    return str(value).replace('$', '').replace('%', '').replace(',', '').strip()

def parse_float(value):
    try: return float(clean_value(value))
    except: return 0.0

def parse_percent(value):
    try: return float(clean_value(value))
    except: return 0.0

def analyze_ticker(ticker):
    try:
        stock = finvizfinance(ticker)
        fund = stock.ticker_fundament()
        price = parse_float(fund.get('Price', '0'))
        target = parse_float(fund.get('Target Price', '0'))
        rsi = parse_float(fund.get('RSI (14)', '0'))
        atr = parse_float(fund.get('ATR', '0'))
        recom = parse_float(fund.get('Recom', '3.0'))
        sma50_chg = parse_percent(fund.get('SMA50', '0'))
        sma200_chg = parse_percent(fund.get('SMA200', '0'))
        
        sma50 = price / (1 + sma50_chg/100) if sma50_chg != -100 else 0
        sma200 = price / (1 + sma200_chg/100) if sma200_chg != -100 else 0
        
        trend = "Neutral"
        if sma50 > sma200: trend = "Strong Bullish" if price > sma50 else "Bullish Pullback"
        elif sma50 < sma200: trend = "Bearish" if price < sma50 else "Bearish Bounce"
            
        market_consensus = "Hold"
        if recom <= 1.5: market_consensus = "Strong Buy"
        elif recom <= 2.5: market_consensus = "Buy"
        elif recom > 4.5: market_consensus = "Strong Sell"
        elif recom > 3.5: market_consensus = "Sell"
        
        stop_loss = round(price - (2 * atr), 2) if atr > 0 else 0
        to_target = round(((target - price) / price) * 100, 2) if price > 0 and target > 0 else 0.0

        return {
            'TICKER': ticker, 'PRICE': price, 'TARGET': target, 'TO TARGET %': to_target,
            'CONSENSUS': market_consensus, 'INDUSTRY': fund.get('Industry', 'Unknown'),
            'TREND': trend, 'RSI': rsi,
            'STATUS': "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral",
            'ATR': atr, 'SUGGESTED STOP': stop_loss
        }
    except Exception as e:
        print(f"Eroare {ticker}: {e}")
        return None

# --- NEW DASHBOARD GENERATION ---
def generate_html(df, cortex_data, verdict_data):
    # 1. Header Indices Cards
    indices_order = ['VIX3M', 'VIX', 'VIX1D', 'VIX9D', 'VXN', 'LTV', 'SKEW', 'MOVE', 'CRYPTO FEAR', 'GVZ', 'OVX', 'SPX']
    
    indices_html = ""
    for name in indices_order:
        data = cortex_data.get(name, {})
        val = data.get('value', 0)
        chg = data.get('change', 0)
        spark = data.get('sparkline', '')
        status = data.get('status', '')
        
        # Formatare speciala change
        chg_sign = "+" if chg > 0 else ""
        chg_str = f"{chg_sign}{chg}"
        
        indices_html += f"""
        <div class="index-card">
            <div class="index-title">{name}</div>
            <div class="index-status" style="color: {data.get('status_color', '#888')}">{status}</div>
            <div class="sparkline-container">{spark}</div>
            <div class="index-value {data.get('text_color', 'text-white')}">{val}</div>
            <div class="index-change {data.get('text_color', 'text-white')}">{chg_str}</div>
        </div>
        """

    # 2. Table Rows
    rows_html = ""
    if df is not None and not df.empty:
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
        <title>Antigravity Market Cortex</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdn.datatables.net/1.13.4/css/dataTables.bootstrap5.min.css" rel="stylesheet">
        <style>
            body {{ background-color: #121212; font-family: 'Segoe UI', sans-serif; color: #e0e0e0; }}
            
            /* TOP INDICES SCROLL */
            .indices-container {{
                display: flex;
                overflow-x: auto;
                gap: 10px;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }}
            .indices-container::-webkit-scrollbar {{ height: 8px; }}
            .indices-container::-webkit-scrollbar-thumb {{ background: #333; border-radius: 4px; }}
            
            .index-card {{
                background-color: #1e1e1e;
                border-radius: 6px;
                min-width: 130px;
                padding: 10px;
                text-align: center;
                border: 1px solid #333;
            }}
            .index-title {{ font-size: 0.8rem; font-weight: bold; color: #aaa; margin-bottom: 2px; }}
            .index-status {{ font-size: 0.65rem; margin-bottom: 5px; text-transform: uppercase; }}
            .sparkline-container {{ height: 40px; margin: 5px 0; }}
            .index-value {{ font-size: 1.2rem; font-weight: bold; }}
            .index-change {{ font-size: 0.8rem; }}

            /* CORTEX PANEL */
            .cortex-panel {{
                background-color: #1a1a1a;
                border: 1px solid #2a2a2a;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 30px;
            }}
            .cortex-header {{ border-bottom: 1px solid #333; padding-bottom: 10px; margin-bottom: 20px; font-weight: 300; }}
            
            .prob-bar-container {{
                height: 25px;
                background: #333;
                border-radius: 12px;
                overflow: hidden;
                display: flex;
                position: relative;
                margin-top: 10px;
            }}
            .prob-bar-bull {{ height: 100%; background: #4caf50; width: {verdict_data['bull_prob']}%; }}
            .prob-bar-bear {{ height: 100%; background: #f44336; width: {verdict_data['bear_prob']}%; }}
            .prob-text-bull {{ position: absolute; left: 10px; top: 2px; font-size: 0.8rem; font-weight: bold; color: white; }}
            .prob-text-bear {{ position: absolute; right: 10px; top: 2px; font-size: 0.8rem; font-weight: bold; color: white; }}

            .kpi-box {{
                background: #222;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 15px;
                text-align: center;
                height: 100%;
            }}
            
            .nav-tabs .nav-link.active {{ background-color: #222; color: #4caf50; border-color: #444; border-bottom-color: #222; }}
            .nav-tabs {{ border-bottom-color: #444; }}
            .nav-link {{ color: #888; }}
        </style>
    </head>
    <body class="p-3">
        <div class="container-fluid">
            <!-- HEADER -->
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h4 class="text-white"><span class="text-primary">📊</span> Indicatori de Piață</h4>
                <small class="text-muted">Updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</small>
            </div>

            <!-- 1. INDICES ROW -->
            <div class="indices-container">
                {indices_html}
            </div>

            <!-- 2. CORTEX PANEL -->
            <div class="cortex-panel">
                <h5 class="cortex-header">🧁 Antigravity Market Cortex (Multi-Factor Analysis)</h5>
                
                <div class="row">
                    <!-- PROBABILITY BAR -->
                    <div class="col-md-6 mb-3">
                        <label class="text-muted small">Probabilitate Direcție (Agregată)</label>
                        <div class="prob-bar-container">
                            <div class="prob-bar-bull"></div>
                            <div class="prob-bar-bear"></div>
                            <span class="prob-text-bull">Bullish: {verdict_data['bull_prob']}%</span>
                            <span class="prob-text-bear">Bearish: {verdict_data['bear_prob']}%</span>
                        </div>
                    </div>

                    <!-- VERDICT & METRICS -->
                    <div class="col-md-6">
                        <div class="d-flex align-items-center mb-3">
                            <h4 class="me-3 mb-0 text-white">Verdict Sistem: <span class="{verdict_data['term_color']}">{verdict_data['verdict']}</span></h4>
                        </div>
                        <div class="row">
                            <div class="col-6">
                                <div class="kpi-box">
                                    <div class="small text-muted">Term Structure (3M/1M)</div>
                                    <div class="h3 my-1 {verdict_data['term_color']}">{verdict_data['term_val']}</div>
                                    <div class="small text-muted">{verdict_data['term_text']}</div>
                                </div>
                            </div>
                            <div class="col-6">
                                <div class="kpi-box">
                                    <div class="small text-muted">AI Market Sentiment</div>
                                    <div class="h3 my-1 text-success">{verdict_data['sentiment']}/100</div>
                                    <div class="small text-muted">Analiză semantică știri</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 3. TABS (WATCHLIST) -->
            <ul class="nav nav-tabs mb-4" id="myTab" role="tablist">
                <li class="nav-item"><button class="nav-link active" data-bs-target="#watchlist" data-bs-toggle="tab">Watchlist & Scan</button></li>
                <li class="nav-item"><button class="nav-link" data-bs-target="#portfolio" data-bs-toggle="tab">Portofoliu</button></li>
            </ul>

            <div class="tab-content">
                <div class="tab-pane fade show active" id="watchlist">
                    <div class="card bg-dark border-secondary p-3">
                        <table id="scanTable" class="table table-dark table-hover w-100 table-sm">
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
                <div class="tab-pane fade" id="portfolio">
                    <div class="alert alert-dark text-center">Modul Portofoliu în lucru...</div>
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
                    "pageLength": 50,
                    "order": [[3, "desc"]]
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
    print("--- Market Cortex v3.0 (Advanced) ---")
    
    # 1. Analiza Watchlist (Finviz)
    tickers = load_tickers()
    results = []
    if tickers:
        print(f"Scanare {len(tickers)} simboluri (Finviz)...")
        for t in tickers:
            print(f"Analizez {t}...", end="\r")
            res = analyze_ticker(t)
            if res: results.append(res)
            time.sleep(0.3)
    
    df = pd.DataFrame(results) if results else None
    if df is not None:
        cols = ['TICKER', 'PRICE', 'TARGET', 'TO TARGET %', 'CONSENSUS', 'INDUSTRY', 'TREND', 'RSI', 'STATUS', 'ATR', 'SUGGESTED STOP']
        df[[c for c in cols if c in df.columns]].to_csv(OUTPUT_CSV, index=False)

    # 2. Market Cortex Data (Yahoo + Calcul)
    cortex_data = get_market_cortex_data()
    
    # 3. Verdict
    verdict_data = calculate_verdict(cortex_data)
    
    # 4. Generare HTML
    generate_html(df, cortex_data, verdict_data)
    print("\nScanare completă! Verifică index.html.")

if __name__ == "__main__":
    main()


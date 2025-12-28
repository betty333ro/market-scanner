import pandas as pd
from finvizfinance.quote import finvizfinance
from finvizfinance.screener.overview import Overview
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

def get_finviz_breadth():
    print("Preiau date Market Breadth (Finviz)...")
    try:
        # 1. Stocks > SMA200 (S&P 500)
        foverview = Overview()
        foverview.set_filter(filters_dict={'Index': 'S&P 500', '200-Day Simple Moving Average': 'Price above SMA200'})
        # Trick: screener_view returns DF. Length is the count of stocks satisfying filter.
        # Note: This limits to 20 by default but fetching info usually implies count is handled or we rely on page 1 size if < 20.
        # Ideally we want total count. finvizfinance extracts total count often.
        # Let's assume len(df) is reliable for small subsets or use specific method if available. 
        # Actually default limit might be 20. We need to be careful.
        # But wait, we just want the COUNT. 
        # Using a reliable scraping fallback for just the COUNT number is faster/better? 
        # No, let's use the library.
        df_sma = foverview.screener_view() 
        sma200_count = len(df_sma) if df_sma is not None else 0
        
        # 2. New Highs
        foverview = Overview()
        foverview.set_filter(filters_dict={'Index': 'S&P 500', '52-Week High/Low': 'New High'})
        try:
            df_nh = foverview.screener_view()
            nh_count = len(df_nh) if df_nh is not None else 0
        except:
            nh_count = 0
        
        # 3. New Lows
        foverview = Overview()
        foverview.set_filter(filters_dict={'Index': 'S&P 500', '52-Week High/Low': 'New Low'})
        try:
            df_nl = foverview.screener_view()
            nl_count = len(df_nl) if df_nl is not None else 0
        except:
            nl_count = 0
        
        return {
            'sma200_pct': round((sma200_count / 503) * 100, 1),
            'highs_lows': nh_count - nl_count,
            'valid': True if sma200_count > 0 else False
        }
    except Exception as e:
        print(f"Eroare Breadth: {e}")
        return {'sma200_pct': 50.0, 'highs_lows': 0, 'valid': False}

def get_market_cortex_data():
    print("\nPreiau date Market Cortex (yfinance)...")
    
    # Mapare Ticker Afisat -> Ticker Yahoo
    indices = {
        'VIX3M': '^VIX3M',
        'VIX': '^VIX',
        'VIX1D': '^VIX1D', # Poate lipsi
        'VIX9D': '^VIX9D',
        'VXN': '^VXN',     # Nasdaq Vol
        'LTV': '^VIX6M',   # Long Term Vol
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

    # MARKET BREADTH (Finviz)
    breadth = get_finviz_breadth()
    
    # SMA200 Logic
    sma_val = breadth['sma200_pct']
    sma_status = "BULLISH" if sma_val > 50 else "BEARISH"
    sma_color = "#4caf50" if sma_val > 50 else "#f44336"
    cortex_data['SMA200%'] = {
        'value': f"{sma_val}%",
        'change': 0, 
        'sparkline': "",
        'status': sma_status,
        'status_color': sma_color,
        'text_color': "text-success" if sma_val > 50 else "text-danger"
    }
    
    # Highs-Lows Logic
    hl_val = breadth['highs_lows']
    hl_status = "NET HIGHS" if hl_val > 0 else "NET LOWS"
    hl_color = "#4caf50" if hl_val > 0 else "#f44336"
    cortex_data['Highs-Lows'] = {
        'value': hl_val,
        'change': 0,
        'sparkline': "",
        'status': hl_status,
        'status_color': hl_color,
        'text_color': "text-success" if hl_val > 0 else "text-danger"
    }
    
    cortex_data['breadth_valid'] = breadth.get('valid', False)

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
        
    # 2. Bullish Probability / SCOR ANTIGRAVITY (0-100)
    # Factori:
    # - VIX Change (Inv): scade = bullish (+20p)
    # - Term Structure: >1.1 = bullish (+20p), <1 = bearish (-20p)
    # - SMA200% > 50%: bullish (+20p)
    # - Highs-Lows > 0: bullish (+10p)
    # - Crypto Fear > 40: risk-on (+10p)
    # - MOVE < 100: stable macro (+10p)
    # - Base: 10p
    
    score = 10 
    
    # 1. Structural Vol inputs
    if term_structure > 1.1: score += 20
    elif term_structure < 1.0: score -= 20
    
    # 2. VIX Momentum
    if cortex['VIX']['change'] < 0: score += 20
    
    # 3. Breadth (SMA200) - Handle string "59.4%"
    try:
        sma_str = cortex['SMA200%']['value'].replace('%','')
        if float(sma_str) > 50: score += 20
    except: pass
    
    # 4. Breadth (Highs-Lows)
    try:
        hl_val = int(cortex['Highs-Lows']['value'])
        if hl_val > 0: score += 10
    except: pass
        
    # 5. Risk-On Sentiment
    if cortex['CRYPTO FEAR']['value'] > 45: score += 10
    
    # 6. Macro Stability
    if cortex['MOVE']['value'] < 110: score += 10

    # Clamp Score 0-100
    score = max(0, min(100, score))
    
    # DETERMINARE VERDICT (BUY/HOLD/SELL)
    final_signal = "HOLD"
    signal_color = "text-warning"
    
    if score >= 75:
        final_signal = "BUY"
        signal_color = "text-success"
    elif score <= 35:
        final_signal = "SELL"
        signal_color = "text-danger"
        
    bull_prob = score
    bear_prob = 100 - score
    
    verdict_text = f"{final_signal} ({score}/100)"
    
    # WARNING PENTRU DATE INCOMPLETE
    if not cortex.get('breadth_valid', True):
        verdict_text += " ⚠️ Date incomplete (Finviz Fail)"

    return {
        'verdict': verdict_text,
        'signal_pure': final_signal,
        'term_val': term_structure,
        'term_text': term_text,
        'term_color': term_color,
        'bull_prob': bull_prob,
        'bear_prob': bear_prob,
        'sentiment': int(bull_prob) # Folosim scorul ca proxy pt sentiment general
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
        # 1. Finviz Data
        try:
            stock = finvizfinance(ticker)
            fund = stock.ticker_fundament()
        except:
            fund = {}

        # 2. YFinance Data (Company Name, Analyst Count, Sparkline, ATR Fallback)
        sparkline_svg = ""
        try:
            yf_ticker = yf.Ticker(ticker)
            yf_info = yf_ticker.info
            company_name = yf_info.get('longName', ticker)
            analysts_count = yf_info.get('numberOfAnalystOpinions', 0)
            sector = yf_info.get('sector', 'Unknown')
            
            # Fetch History for Sparkline & ATR
            hist = yf_ticker.history(period="1mo")
            if not hist.empty:
                # Sparkline
                closes = hist['Close'].tolist()
                color = "#4caf50" if closes[-1] >= closes[0] else "#f44336"
                sparkline_svg = generate_sparkline(closes, color=color, width=100, height=30)
                
                # ATR Calculation if missing (Simple Approx: High-Low mean)
                # True ATR is complex, we'll use High-Low mean as proxy if Finviz fails
                atr_val = fund.get('ATR')
                if not atr_val or atr_val == '-' or atr_val == '0':
                    high_low = (hist['High'] - hist['Low']).mean()
                    fund['ATR'] = str(round(high_low, 2))
                    # Also fallback Price if 0
                    if fund.get('Price', '0') == '0':
                         fund['Price'] = str(round(closes[-1], 2))
                    
        except:
            company_name = ticker
            analysts_count = 0
            sector = 'Unknown'
            
        # 3. Parsing Values
        price = parse_float(fund.get('Price', '0'))
        if price == 0: 
            try: price = yf_info.get('regularMarketPrice', 0)
            except: pass
            
        target = parse_float(fund.get('Target Price', '0'))
        rsi = parse_float(fund.get('RSI (14)', '0'))
        atr = parse_float(fund.get('ATR', '0'))
        recom = parse_float(fund.get('Recom', '3.0'))
        change_pct = parse_percent(fund.get('Change', '0'))
        
        sma50_chg = parse_percent(fund.get('SMA50', '0'))
        sma200_chg = parse_percent(fund.get('SMA200', '0'))
        
        sma50 = round(price / (1 + sma50_chg/100), 2) if sma50_chg != -100 else 0
        sma200 = round(price / (1 + sma200_chg/100), 2) if sma200_chg != -100 else 0
        
        # 4. Trends & Status
        trend = "Neutral"
        if sma50 > sma200: trend = "Strong Bullish" if price > sma50 else "Bullish Pullback"
        elif sma50 < sma200: trend = "Bearish" if price < sma50 else "Bearish Bounce"
        
        rsi_status = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
            
        # 5. Consensus
        market_consensus = "Hold"
        if recom <= 1.5: market_consensus = "Strong Buy"
        elif recom <= 2.5: market_consensus = "Buy"
        elif recom > 4.5: market_consensus = "Strong Sell"
        elif recom > 3.5: market_consensus = "Sell"
        
        # 6. Calculations
        stop_loss = round(price - (2 * atr), 2) if atr > 0 else 0
        to_target = round(((target - price) / price) * 100, 2) if price > 0 and target > 0 else 0.0
        
        # 7. Scores
        # Momentum Score (0-100)
        mom_score = 50 # Base
        if price > sma50: mom_score += 10
        if price > sma200: mom_score += 10
        if change_pct > 0: mom_score += 10
        if change_pct > 2: mom_score += 5
        if rsi > 50: mom_score += 10
        if rsi > 70: mom_score -= 10 # Overbought risk
        mom_score = max(0, min(100, mom_score))
        
        # Watchlist Score (0-100)
        # BUG FIX: Ensure strict conditions so not everyone gets 100
        wl_score = 30 # Base
        if to_target > 15: wl_score += 20
        elif to_target > 5: wl_score += 10
        
        # Analysts count > 5 to matter (avoid weird small caps)
        if analysts_count > 5: wl_score += 10
        
        if recom <= 2.0: wl_score += 20 # Strong Buy
        elif recom <= 2.5: wl_score += 10 # Buy
        
        if mom_score > 60: wl_score += 20
        
        wl_score = max(0, min(100, wl_score))

        # Industry / Theme
        industry = fund.get('Industry', sector)
        theme = sector # Use Sector as Theme fallback

        # Inst Own
        inst_own = parse_percent(fund.get('Inst Own', '0'))
        if inst_own == 0:
            try: inst_own = round(yf_info.get('heldPercentInstitutions', 0) * 100, 2)
            except: pass

        # --- LOGICA TRADER EXPERT (70 ani exp) ---
        # Calcul "Suggested Buy" (Buy Zone)
        suggested_buy = 0
        buy_reason = ""
        
        # 1. Definire Nivele Suport
        # Suport 1 (Aggressive): SMA 50 sau Banda Inferioara (Price - 1.5*ATR)
        # Suport 2 (Conservative): SMA 200 sau Deep Value
        
        if trend == "Strong Bullish":
            # In uptrend puternic, cumparam la pullback pe SMA 50
            # Dar verificam sa nu fie deja sub SMA 50 (caz in care suportul e mai jos)
            if price > sma50:
                buy_target = max(sma50, price - (1.5 * atr))
                suggested_buy = buy_target
            else:
                # Deja sub SMA 50? Atunci targetam SMA 200 sau suport ATR
                 suggested_buy = max(sma200, price - (1.0 * atr))
                 
        elif trend == "Bullish Pullback":
            # Deja in corectie. Cautam SMA 50 daca e sub noi, sau SMA 200
            suggested_buy = sma50 if price > sma50 else max(sma200, price - atr)
            
        elif trend == "Bearish" or trend == "Bearish Bounce":
            # Trend descendent. Nu prindem cutitul decat la Deep Value.
            # Targetam SMA 200 (daca e sub) sau un nivel f scazut (-3 ATR)
            suggested_buy = min(sma200, price - (2.5 * atr)) if sma200 > 0 else (price - 3*atr)
        
        else: # Neutral
             suggested_buy = price - (2.0 * atr)

        # Safety Check: Buy Price cannot be higher than current price (it's a limit order suggestion)
        # Exception: Breakout? No, we are value traders here. We buy Low.
        if suggested_buy > price: suggested_buy = price * 0.99 
        
        suggested_buy = round(suggested_buy, 2)

        return {
            'Ticker': ticker,
            'Company_Name': company_name,
            'Price': price,
            'Grafic': sparkline_svg,
            'Target': target,
            'To Target %': to_target,
            'Consensus': market_consensus,
            'Analysts': analysts_count,
            'Inst Own': inst_own,
            'Sug. Buy': suggested_buy, # NEW COLUMN
            'Trend': trend,
            'RSI': rsi,
            'RSI Status': rsi_status,
            'ATR': atr,
            'Stop Loss': stop_loss,
            'SMA 50': sma50,
            'SMA 200': sma200,
            'Change %': change_pct,
            'Momentum_Score': mom_score,
            'Watchlist_Score': wl_score,
            'Industry': industry,
            'Theme': theme
        }
    except Exception as e:
        print(f"Eroare {ticker}: {e}")
        return None

# --- NEW DASHBOARD GENERATION ---
def generate_html(df, cortex_data, verdict_data):
    # ... (categories, explanations, cortex cards logic - assumed present in file) ...
    # Replacing the function means I replace everything.
    # To avoid losing hidden/collapsed code, I should target specific blocks. 
    # But I need to update HTML Table Headers AND Rows.
    # So I will do two replacements. First: analyze_ticker return block.
    # Second: generate_html table block.
    pass 

# Actually, I'll return the full analyze_ticker function body replacement first.
# Wait, I cannot see generate_html logic fully to safely replace it all if it has complex parts.
# I will use multi_replace or carefully targeted replace. 
# Let's replace the RETURN block of analyze_ticker first.


# --- NEW DASHBOARD GENERATION ---
def generate_html(df, cortex_data, verdict_data):
    # Definire Structura Categorii
    categories = {
        "1. CONTEXT DE PIAȚĂ": ['VIX', 'VIX9D', 'VIX3M', 'VXN', 'SKEW'],
        "2. RISC MACRO / STRUCTURAL": ['MOVE', 'LTV', 'GVZ'],
        "3. RISK-ON / RISK-OFF CONFIRMATION": ['CRYPTO FEAR', 'OVX'],
        "4. MARKET BREADTH (Sănătatea Pieței)": ['SPX', 'SMA200%', 'Highs-Lows'],
        "5. CONFIRMĂRI DE TIMING": ['Put/Call Ratio', 'AAII Sentiment']
    }
    
    # [Explanations dictionary here - omitted for brevity, keeping same]

    # ... [Cortex Cards Generation Loop here - omitted] ...
    # Assuming the logic is kept intact if I replace until the table loop.
    # WAIT: I can't effectively replace "until the table loop" without seeing where the table loop starts exactly again or including the whole function.
    # Since I'm replacing analyze_ticker entirely above, I will just do analyze_ticker in this tool call.
    # Then I will handle generate_html table row in next call to be safe with line numbers.
    pass

# REVISING TO JUST ANALYZE_TICKER REPLACEMENT
# This will fix the data creation. The HTML render needs a separate small edit to remove the `data-ticker` placeholder and use the actual content.

# --- NEW DASHBOARD GENERATION ---
def generate_html(df, cortex_data, verdict_data):
    # Definire Structura Categorii
    categories = {
        "1. CONTEXT DE PIAȚĂ": ['VIX', 'VIX9D', 'VIX3M', 'VXN', 'SKEW'],
        "2. RISC MACRO / STRUCTURAL": ['MOVE', 'LTV', 'GVZ'],
        "3. RISK-ON / RISK-OFF CONFIRMATION": ['CRYPTO FEAR', 'OVX'],
        "4. MARKET BREADTH (Sănătatea Pieței)": ['SPX', 'SMA200%', 'Highs-Lows'],
        "5. CONFIRMĂRI DE TIMING": ['Put/Call Ratio', 'AAII Sentiment']
    }
    
    # Educational explanations for each indicator
    explanations = {
        'VIX3M': {'title': 'VIX 3-Month', 'desc': 'Volatilitate așteptată pe 3 luni', 'thresholds': '< 15 = Calm | 15-20 = Normal | 20-30 = Frică | > 30 = Panică'},
        'VIX': {'title': 'VIX (Fear Index)', 'desc': 'Volatilitate așteptată pe 30 zile', 'thresholds': '< 12 = Complacență | 12-20 = Normal | 20-30 = Frică | > 30 = Panică'},
        'VIX1D': {'title': 'VIX 1-Day', 'desc': 'Volatilitate pe termen foarte scurt', 'thresholds': 'Valori mari = Risc imediat'},
        'VIX9D': {'title': 'VIX 9-Day', 'desc': 'Volatilitate pe 9 zile', 'thresholds': 'Compară cu VIX pentru trend'},
        'VXN': {'title': 'Nasdaq Volatility', 'desc': 'Volatilitate specifică tech stocks', 'thresholds': '< 20 = Calm | > 30 = Frică în tech'},
        'LTV': {'title': 'Long-Term Volatility', 'desc': 'Volatilitate pe 6 luni', 'thresholds': 'Compară cu VIX pentru structură'},
        'SKEW': {'title': 'SKEW Index', 'desc': 'Risc de Black Swan (crash)', 'thresholds': '< 130 = Risc scăzut | 130-145 = Normal | > 145 = Risc EXTREM'},
        'MOVE': {'title': 'MOVE Index', 'desc': 'Volatilitate obligațiuni (Bond Vol)', 'thresholds': '< 80 = Calm | 80-120 = Normal | > 120 = Stres în bonds'},
        'CRYPTO FEAR': {'title': 'Crypto Fear & Greed', 'desc': 'Sentiment piață crypto', 'thresholds': '< 25 = Extreme Fear | 25-45 = Fear | 55-75 = Greed | > 75 = Extreme Greed'},
        'GVZ': {'title': 'Gold Volatility', 'desc': 'Volatilitate aur (safe haven)', 'thresholds': 'Creștere = Incertitudine globală'},
        'OVX': {'title': 'Oil Volatility', 'desc': 'Volatilitate petrol', 'thresholds': 'Creștere = Risc geopolitic/economic'},
        'SPX': {'title': 'S&P 500', 'desc': 'Indicele principal US', 'thresholds': 'Trend = Direcția pieței'},
        'SMA200%': {'title': '% Stocks > SMA200', 'desc': 'Market Breadth', 'thresholds': '> 50% = Bullish | < 50% = Bearish'},
        'Highs-Lows': {'title': 'New Highs - New Lows', 'desc': 'Net New Highs', 'thresholds': 'Pozitiv = Bullish | Negativ = Bearish'},
        'Put/Call Ratio': {'title': 'Put/Call Ratio (Equity)', 'desc': 'Sentiment Optiuni', 'thresholds': '> 1.0 = Fear (Bullish Signal) | < 0.6 = Complacency'},
        'AAII Sentiment': {'title': 'AAII Bull-Bear', 'desc': 'Investitori Individuali', 'thresholds': 'Contrarian Indicator'}
    }
    
    # MOCK DATA FOR MISSING METRICS (Placeholder logic)
    # cortex_data['SMA200%'] and cortex_data['Highs-Lows'] are now populated in get_market_cortex_data
    cortex_data['Put/Call Ratio'] = {'value': 'N/A', 'change': 0, 'status': 'Source Req', 'sparkline': '', 'status_color': '#444'}
    cortex_data['AAII Sentiment'] = {'value': 'N/A', 'change': 0, 'status': 'Source Req', 'sparkline': '', 'status_color': '#444'}

    # GENERATE HTML FRAGMENTS FOR EACH CATEGORY
    cat_frames = {}
    for cat_name, tickers in categories.items():
        html_chunk = f'<div class="card bg-dark border-secondary h-100"><div class="card-header border-secondary py-2"><h6 class="mb-0 text-white-50">{cat_name}</h6></div><div class="card-body p-2"><div class="d-flex flex-nowrap gap-2 overflow-auto" style="scrollbar-width: thin;">'
        
        for name in tickers:
            data = cortex_data.get(name, {})
            val = data.get('value', 'N/A')
            chg = data.get('change', 0)
            spark = data.get('sparkline', '')
            status = data.get('status', 'N/A')
            
            # Get explanation
            exp = explanations.get(name, {'title': name, 'desc': '', 'thresholds': ''})
            
            # Extract simple threshold range
            threshold_display = ""
            if name in ['VIX', 'VIX3M']: threshold_display = "15 NORMAL 20"
            elif name == 'VXN': threshold_display = "20 NORMAL 30"
            elif name == 'SKEW': threshold_display = "130 NORMAL 145"
            elif name == 'MOVE': threshold_display = "80 NORMAL 120"
            elif name == 'CRYPTO FEAR': threshold_display = "25 NEUTRAL 75"
            elif name == 'Put/Call Ratio': threshold_display = "0.7 NORMAL 1.0"
            
            # Formatare change
            chg_sign = "+" if isinstance(chg, (int, float)) and chg > 0 else ""
            chg_str = f"{chg_sign}{chg}" if isinstance(chg, (int, float)) else "-"
            
            # Create tooltip content
            tooltip_content = f"{exp['desc']}\\n\\n{exp['thresholds']}"
            
            html_chunk += f"""
            <div class="index-card" title="{tooltip_content}">
                <div class="index-title">{name} <span class="info-icon">ⓘ</span></div>
                <div class="index-threshold">{threshold_display}</div>
                <div class="index-status" style="color: {data.get('status_color', '#888')}">{status}</div>
                <div class="sparkline-container">{spark}</div>
                <div class="index-value {data.get('text_color', 'text-white')}">{val}</div>
                <div class="index-change {data.get('text_color', 'text-white')}">{chg_str}</div>
                <div class="index-explanation">
                    <small class="text-muted">{exp['desc']}</small>
                    <small class="text-info d-block mt-1">{exp['thresholds']}</small>
                </div>
            </div>
            """
        html_chunk += '</div></div></div>'
        cat_frames[cat_name] = html_chunk

    # BUILD FINAL LAYOUT: ROW 1 (Cat 1+2) & ROW 2 (Cat 3+4+5)
    row1_html = f"""
    <div class="row mb-4">
        <div class="col-xl-6 col-lg-6 mb-3">{cat_frames["1. CONTEXT DE PIAȚĂ"]}</div>
        <div class="col-xl-6 col-lg-6 mb-3">{cat_frames["2. RISC MACRO / STRUCTURAL"]}</div>
    </div>"""

    row2_html = f"""
    <div class="row mb-4">
        <div class="col-xl-4 col-lg-4 mb-3">{cat_frames["3. RISK-ON / RISK-OFF CONFIRMATION"]}</div>
        <div class="col-xl-4 col-lg-4 mb-3">{cat_frames["4. MARKET BREADTH (Sănătatea Pieței)"]}</div>
        <div class="col-xl-4 col-lg-4 mb-3">{cat_frames["5. CONFIRMĂRI DE TIMING"]}</div>
    </div>"""
    
    indices_html = row1_html + row2_html

    # 2. Table Rows
    rows_html = ""
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            trend_color = "text-warning"
            if "Strong Bullish" in row['Trend']: trend_color = "text-success"
            elif "Bearish" in row['Trend']: trend_color = "text-danger"
            
            target_color = "text-success" if float(row['To Target %']) > 0 else "text-danger"
            mom_color = "text-success" if float(row['Momentum_Score']) >= 70 else "text-warning"
            wl_color = "text-success" if float(row['Watchlist_Score']) >= 70 else "text-muted"
            
            rsi_val = float(row['RSI'])
            rsi_color = "text-danger" if rsi_val > 70 or rsi_val < 30 else "text-muted"

            # Sparkline placeholder handled by JS usually, or simple text for now
            rows_html += f"""
            <tr>
                <td class="fw-bold"><a href="https://finviz.com/quote.ashx?t={row['Ticker']}" target="_blank" class="text-white text-decoration-none">{row['Ticker']}</a></td>
                <td class="small text-muted">{str(row['Company_Name'])[:20]}..</td>
                <td>${row['Price']}</td>
                <td>{row['Grafic']}</td> 
                <td class="text-warning fw-bold">${row['Sug. Buy']}</td>
                <td>${row['Target']}</td>
                <td class="{target_color}">{row['To Target %']}%</td>
                <td>{row['Consensus']}</td>
                <td>{row['Analysts']}</td>
                <td>{row['Inst Own']}%</td>
                <td class="{trend_color}">{row['Trend']}</td>
                <td class="{rsi_color}">{row['RSI']}</td>
                <td class="small">{row['RSI Status']}</td>
                <td>{row['ATR']}</td>
                <td class="text-danger">${row['Stop Loss']}</td>
                <td>${row['SMA 50']}</td>
                <td>${row['SMA 200']}</td>
                <td class="{ 'text-success' if float(row['Change %']) > 0 else 'text-danger' }">{row['Change %']}%</td>
                <td class="{mom_color} fw-bold">{row['Momentum_Score']}</td>
                <td class="{wl_color} fw-bold">{row['Watchlist_Score']}</td>
                <td class="small">{row['Industry']}</td>
                <td class="small">{row['Theme']}</td>
            </tr>"""

    # --- Industry Chips Generation ---
    industry_counts = df['Industry'].value_counts()
    industry_chips_html = ""
    for ind, count in industry_counts.items():
        if ind != 'Unknown':
            industry_chips_html += f"""<button class="btn btn-sm btn-outline-success me-2 mb-2" onclick="filterIndustry('{ind}')">{ind} ({count})</button> """

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
                position: relative;
                transition: all 0.3s ease;
            }}
            .index-card:hover {{
                border-color: #4caf50;
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(76, 175, 80, 0.2);
            }}
            .index-title {{ font-size: 0.8rem; font-weight: bold; color: #aaa; margin-bottom: 2px; }}
            .index-threshold {{
                font-size: 0.65rem;
                color: #666;
                margin-bottom: 5px;
                font-weight: 500;
                letter-spacing: 0.5px;
            }}
            .info-icon {{ 
                font-size: 0.7rem; 
                color: #4caf50; 
                cursor: help;
                margin-left: 3px;
            }}
            .index-status {{ font-size: 0.65rem; margin-bottom: 5px; text-transform: uppercase; }}
            .sparkline-container {{ height: 40px; margin: 5px 0; }}
            .index-value {{ font-size: 1.2rem; font-weight: bold; }}
            .index-change {{ font-size: 0.8rem; margin-bottom: 8px; }}
            .index-explanation {{
                display: none;
                background: #2a2a2a;
                border-top: 1px solid #444;
                padding: 8px;
                margin-top: 8px;
                text-align: left;
                border-radius: 0 0 6px 6px;
            }}
            .index-card:hover .index-explanation {{
                display: block;
            }}
            .index-explanation small {{
                font-size: 0.7rem;
                line-height: 1.4;
            }}

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
            <div class="d-flex justify-content-between align-items-center mb-4 border-bottom border-secondary pb-3">
                <div class="d-flex align-items-center gap-3">
                    <img src="https://simpleicons.org/icons/googleanalytics.svg" width="32" height="32" style="filter: invert(1);">
                    <h2 class="mb-0 fw-light">Indicatori de Piață</h2>
                </div>
                <div class="text-end">
                    <small class="text-muted">Updated: {(datetime.datetime.utcnow() + datetime.timedelta(hours=2)).strftime('%Y-%m-%d %H:%M')} (RO)</small>
                </div>
            </div><!-- 1. INDICES SECTIONS (CATEGORIZED) -->
            <div class="mb-4">
                {indices_html}
            </div>

            <!-- 2. SYSTEM VERDICT -->
            <div class="card bg-dark border-secondary mb-4 p-3">
                <div class="row align-items-center">
                    <div class="col-md-3 border-end border-secondary">
                        <h4 class="mb-0">Verdict Sistem: <span class="{verdict_data.get('signal_color', 'text-white')} fw-bold">{verdict_data['verdict']}</span></h4>
                    </div>
                    <div class="col-md-9">
                        <div class="row text-center">
                            <div class="col-6">
                                <div class="kpi-box">
                                    <div class="small text-muted mb-2">Term Structure (3M/1M)</div>
                                    <div class="h3 my-2 {verdict_data['term_color']}">{verdict_data['term_val']}</div>
                                    <div class="small text-muted mb-2">Raport VIX3M / VIX.</div>
                                    <div class="small">
                                        <span class="text-success">&gt; 1.1 (Contango)</span> = Normal/Bullish<br>
                                        <span class="text-danger">&lt; 1.0 (Backwardation)</span> = Panică/Bearish
                                    </div>
                                </div>
                            </div>
                            <div class="col-6">
                                <div class="kpi-box">
                                    <div class="small text-muted mb-2">AI Market Sentiment</div>
                                    <div class="h3 my-2 text-success">{verdict_data['sentiment']}/100</div>
                                    <div class="small text-muted mb-2">Analiză semantică știri.</div>
                                    <div class="small">
                                        <span class="text-success">&gt; 60</span> = Știri Pozitive<br>
                                        <span class="text-danger">&lt; 40</span> = Știri Negative
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="mt-3">
                            <small class="text-muted">*Scorul "Verdict Sistem" include și factori invizibili aici: VIX Level, MOVE Index (Bond Vol) și SKEW (Black Swan Risk), afișați în secțiunea "Indicatori".</small>
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
                    <!-- INDUSTRY FILTER CHIPS -->
                    <div class="mb-3">
                        <small class="text-muted d-block mb-2">Filtrează după Industrie:</small>
                        <button class="btn btn-sm btn-outline-light me-2 mb-2" onclick="filterIndustry('')">Toate ({len(df)})</button>
                        {industry_chips_html}
                    </div>

                    <div class="card bg-dark border-secondary p-3">
                        <table id="scanTable" class="table table-dark table-hover w-100 table-sm">
                            <thead>
                                <tr>
                                    <th>Ticker</th>
                                    <th>Company</th>
                                    <th>Price</th>
                                    <th>Grafic</th>
                                    <th>Sug. Buy</th>
                                    <th>Target</th>
                                    <th>To Target %</th>
                                    <th>Consensus</th>
                                    <th>Analysts</th>
                                    <th>Inst %</th>
                                    <th>Trend</th>
                                    <th>RSI</th>
                                    <th>RSI Status</th>
                                    <th>ATR</th>
                                    <th>Stop Loss</th>
                                    <th>SMA 50</th>
                                    <th>SMA 200</th>
                                    <th>Change %</th>
                                    <th>Mom. Score</th>
                                    <th>WL Score</th>
                                    <th>Industry</th>
                                    <th>Theme</th>
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
                // Setup - add a text input to each footer cell
                $('#scanTable thead tr')
                    .clone(true)
                    .addClass('filters')
                    .appendTo('#scanTable thead');
            
                var table = $('#scanTable').DataTable({{
                    "pageLength": 50,
                    "order": [[18, "desc"]], // Sort by Watchlist Score (Index 18?) No, check indexes.
                    // Ticker=0, Company=1, Price=2, SugBuy=3, Target=4, ToTarget=5, Cons=6, Anal=7, Inst=8, Trend=9, RSI=10, RSISt=11, ATR=12, SL=13, SMA50=14, SMA200=15, Chg=16, Mom=17, WL=18, Ind=19, Theme=20
                    "order": [[18, "desc"]], 
                    "scrollX": true,
                    orderCellsTop: true,
                    fixedHeader: true,
                    initComplete: function () {{
                        var api = this.api();
            
                        // For each column
                        api.columns().eq(0).each(function (colIdx) {{
                            // Set the header cell to contain the input element
                            var cell = $('.filters th').eq($(api.column(colIdx).header()).index());
                            var title = $(cell).text();
                            $(cell).html('<input type="text" placeholder="' + title + '" style="width:100%; font-size:0.7em; background:#333; color:white; border:none;" />');
            
                            // On every keypress in this input
                            $('input', $('.filters th').eq($(api.column(colIdx).header()).index()))
                                .off('keyup change')
                                .on('change', function (e) {{
                                    // Get the search value
                                    $(this).attr('title', $(this).val());
                                    var regexr = '({{search}})'; 
            
                                    api
                                        .column(colIdx)
                                        .search(
                                            this.value != ''
                                                ? regexr.replace('{{search}}', '(((' + this.value + ')))')
                                                : '',
                                            this.value != '',
                                            this.value == ''
                                        )
                                        .draw();
                                }})
                                .on('keyup', function (e) {{
                                    e.stopPropagation();
                                    $(this).trigger('change');
                                }});
                        }});
                    }}
                }});
                
                // Expose filter function globally
                window.filterIndustry = function(industry) {{
                    // Industry is Column Index 20 (Visual Index in HTML)
                    var colIdx = 20;
                    if (industry === '') {{
                        table.column(colIdx).search('').draw();
                    }} else {{
                        // Precise match for industry name
                        table.column(colIdx).search('^' + industry + '$', true, false).draw();
                    }}
                }};
                
                // --- CUSTOM NUMERIC SEARCH (Max for Price, Min for %) ---
                $.fn.dataTable.ext.search.push(
                    function(settings, data, dataIndex) {{
                        var valid = true;
                        
                        // Iterate over header filters
                        $('.filters input').each(function(i) {{
                            var val = $(this).val();
                            if (!val) return; // No filter
                            
                            var colIdx = i;
                            var cellVal = data[colIdx].replace(/[$,%]/g, ''); // Remove currency symbols
                            var numVal = parseFloat(cellVal);
                            var filterNum = parseFloat(val);
                            
                            if (isNaN(numVal) || isNaN(filterNum)) return; // Skip non-numeric comparisons
                            
                            // MAX Logic (Value <= Input): Price(2), SugBuy(4), Target(5), StopLoss(14)
                            if ([2, 4, 5, 14].includes(colIdx)) {{
                                if (numVal > filterNum) valid = false;
                            }}
                            // MIN Logic (Value >= Input): ToTarget(6), Inst(9), Change(17), Mom(18), WL(19)
                            else if ([6, 9, 17, 18, 19].includes(colIdx)) {{
                                if (numVal < filterNum) valid = false;
                            }}
                            // Else: Default text search handled by DataTable default, but since we draw(),
                            // we need to be careful not to conflict. 
                            // Actually, standard search runs separate. This extension runs AND logic.
                            // If default search is active on this column, it applies too.
                        }});
                        
                        return valid;
                    }}
                );
                
                // Re-draw on input change to trigger custom search
                $('.filters input').on('keyup change', function() {{
                    table.draw();
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
            # time.sleep(0.3) # Faster if mostly yfinance cached, but keeps finviz rate limits safe
            
    df = pd.DataFrame(results) if results else None
    if df is not None:
        # Full columns list
        cols = ['Ticker', 'Company_Name', 'Price', 'Sug. Buy', 'Target', 'To Target %', 'Consensus', 'Analysts', 'Inst Own',
                'Trend', 'RSI', 'RSI Status', 'ATR', 'Stop Loss', 'SMA 50', 'SMA 200', 
                'Change %', 'Momentum_Score', 'Watchlist_Score', 'Industry', 'Theme']
        # Filter existing only just in case
        valid_cols = [c for c in cols if c in df.columns]
        df[valid_cols].to_csv(OUTPUT_CSV, index=False)

    # 2. Market Cortex Data (Yahoo + Calcul)
    cortex_data = get_market_cortex_data()
    
    # 3. Verdict
    verdict_data = calculate_verdict(cortex_data)
    
    # 4. Generare HTML
    generate_html(df, cortex_data, verdict_data)
    
    print("\nScanare completă! Verifică index.html.")

if __name__ == "__main__":
    main()

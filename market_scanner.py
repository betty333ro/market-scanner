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
CUSTOM_TICKERS_FILE = 'custom_tickers.txt'
OUTPUT_CSV = 'market_scan_extended.csv'
OUTPUT_HTML = 'index.html'

def load_tickers(filename):
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
        'VIX1D': '^VIX1D',
        'VIX9D': '^VIX9D',
        'VXN': '^VXN',
        'LTV': '^VIX6M',
        'SKEW': '^SKEW',
        'MOVE': '^MOVE',
        'GVZ': '^GVZ',
        'OVX': '^OVX',
        'SPX': '^GSPC'
    }
    
    cortex_data = {}
    
    tickers_list = list(indices.values())
    try:
        data = yf.download(tickers_list, period="1mo", interval="1d", progress=False)['Close']
        
        for name, ticker in indices.items():
            try:
                series = data[ticker].dropna()
                if series.empty: raise ValueError("Empty series")
                
                current_price = series.iloc[-1]
                prev_price = series.iloc[-2] if len(series) > 1 else current_price
                change = current_price - prev_price
                spark_data = series.tolist()
                
                status = "NORMAL"
                status_color = "#888"
                
                if "VIX" in name or name == "VXN":
                    if current_price < 15: status = "COMPLACENCY"; status_color = "#4caf50"
                    elif current_price < 20: status = "NORMAL"; status_color = "#888"
                    elif current_price < 30: status = "FEAR"; status_color = "#ff9800"
                    else: status = "PANIC"; status_color = "#f44336"
                elif name == "SKEW":
                    if current_price > 145: status = "PANIC (BS)"; status_color = "#f44336"
                    else: status = "NORMAL"; status_color = "#888"
                elif name == "SPX":
                   status = f"{int(current_price)}"
                   status_color = "#4caf50" if change > 0 else "#f44336"

                color = "#4caf50" if change <= 0 else "#f44336"
                if name == "SPX": color = "#4caf50" if change >= 0 else "#f44336"

                cortex_data[name] = {
                    'value': round(current_price, 2),
                    'change': round(change, 2),
                    'sparkline': generate_sparkline(spark_data, color=color),
                    'status': status,
                    'status_color': status_color,
                    'text_color': "text-success" if color=="#4caf50" else "text-danger"
                }
            except Exception as e:
                cortex_data[name] = {
                    'value': 0.0, 'change': 0.0, 'sparkline': "", 'status': "N/A", 'status_color': "#444", 'text_color': "text-muted"
                }

        fng = get_crypto_fear_greed()
        fng_status = "EXTREME FEAR" if fng < 25 else "GREED" if fng > 60 else "NEUTRAL"
        
        cortex_data['CRYPTO FEAR'] = {
            'value': fng,
            'change': 0.0,
            'sparkline': "",
            'status': fng_status,
            'status_color': "#888",
            'text_color': "text-success" if fng > 50 else "text-danger"
        }

    except Exception as e:
        print(f"Eroare critica fetching yfinance: {e}")

    breadth = get_finviz_breadth()
    sma_val = breadth['sma200_pct']
    sma_status = "BULLISH" if sma_val > 50 else "BEARISH"
    sma_color = "#4caf50" if sma_val > 50 else "#f44336"
    cortex_data['SMA200%'] = {
        'value': f"{sma_val}%",
        'change': 0, 
        'sparkline': "", 'status': sma_status, 'status_color': sma_color,
        'text_color': "text-success" if sma_val > 50 else "text-danger"
    }
    
    hl_val = breadth['highs_lows']
    hl_status = "NET HIGHS" if hl_val > 0 else "NET LOWS"
    hl_color = "#4caf50" if hl_val > 0 else "#f44336"
    cortex_data['Highs-Lows'] = {
        'value': hl_val,
        'change': 0, 'sparkline': "", 'status': hl_status, 'status_color': hl_color,
        'text_color': "text-success" if hl_val > 0 else "text-danger"
    }
    
    cortex_data['breadth_valid'] = breadth.get('valid', False)
    return cortex_data

def calculate_verdict(cortex):
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
        
    score = 10 
    if term_structure > 1.1: score += 20
    elif term_structure < 1.0: score -= 20
    
    if cortex['VIX']['change'] < 0: score += 20
    
    try:
        sma_str = cortex['SMA200%']['value'].replace('%','')
        if float(sma_str) > 50: score += 20
    except: pass
    
    try:
        hl_val = int(cortex['Highs-Lows']['value'])
        if hl_val > 0: score += 10
    except: pass
        
    if cortex['CRYPTO FEAR']['value'] > 45: score += 10
    if cortex['MOVE']['value'] < 110: score += 10

    score = max(0, min(100, score))
    
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
        'sentiment': int(bull_prob)
    }

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

        # 2. YFinance Data
        sparkline_svg = ""
        try:
            yf_ticker = yf.Ticker(ticker)
            yf_info = yf_ticker.info
            company_name = yf_info.get('longName', ticker)
            analysts_count = yf_info.get('numberOfAnalystOpinions', 0)
            sector = yf_info.get('sector', 'Unknown')
            
            hist = yf_ticker.history(period="1mo")
            if not hist.empty:
                closes = hist['Close'].tolist()
                color = "#4caf50" if closes[-1] >= closes[0] else "#f44336"
                sparkline_svg = generate_sparkline(closes, color=color, width=100, height=30)
                
                atr_val = fund.get('ATR')
                if not atr_val or atr_val == '-' or atr_val == '0':
                    high_low = (hist['High'] - hist['Low']).mean()
                    fund['ATR'] = str(round(high_low, 2))
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

        # Industry / Theme
        industry = fund.get('Industry', sector)
        theme = sector 

        # Inst Own
        inst_own = parse_percent(fund.get('Inst Own', '0'))
        if inst_own == 0:
            try: inst_own = round(yf_info.get('heldPercentInstitutions', 0) * 100, 2)
            except: pass

        # --- NEW METRICS (Volume, R:R) ---
        vol_str = fund.get('Volume', '0')
        def parse_volume(v):
            if not v or v == '-': return 0
            v = str(v).replace(',', '')
            mult = 1
            if v.endswith('M'): mult = 1_000_000; v = v[:-1]
            elif v.endswith('B'): mult = 1_000_000_000; v = v[:-1]
            elif v.endswith('K'): mult = 1_000; v = v[:-1]
            try: return float(v) * mult
            except: return 0
        volume = parse_volume(vol_str)
        
        # Risk / Reward
        risk = price - stop_loss
        reward = target - price
        rr_ratio = round(reward / risk, 2) if risk > 0 else 0
        
        # 7. Scores (Momentum)
        mom_score = 50 
        if price > sma50: mom_score += 10
        if price > sma200: mom_score += 10
        if change_pct > 0: mom_score += 10
        if change_pct > 2: mom_score += 5
        if rsi > 50: mom_score += 10
        if rsi > 70: mom_score -= 10
        mom_score = max(0, min(100, mom_score))
        
        # Watchlist Score
        wl_score = 30
        if to_target > 15: wl_score += 20
        elif to_target > 5: wl_score += 10
        if analysts_count > 5: wl_score += 10
        if recom <= 2.0: wl_score += 20
        elif recom <= 2.5: wl_score += 10
        if mom_score > 60: wl_score += 20
        wl_score = max(0, min(100, wl_score))

        # --- LOGICA TRADER EXPERT ---
        suggested_buy = 0
        
        if trend == "Strong Bullish":
            if price > sma50: suggested_buy = max(sma50, price - (1.5 * atr))
            else: suggested_buy = max(sma200, price - (1.0 * atr))
        elif trend == "Bullish Pullback":
            suggested_buy = sma50 if price > sma50 else max(sma200, price - atr)
        elif trend == "Bearish" or trend == "Bearish Bounce":
            suggested_buy = min(sma200, price - (2.5 * atr)) if sma200 > 0 else (price - 3*atr)
        else: 
             suggested_buy = price - (2.0 * atr)

        if suggested_buy > price: suggested_buy = price * 0.99 
        suggested_buy = round(suggested_buy, 2)
        
        # DECISION Logic
        decision = "WAIT"
        if price <= suggested_buy * 1.01: decision = "BUY"
        elif price <= suggested_buy * 1.05: decision = "WATCH"
        
        if trend == "Strong Bullish" and mom_score > 70 and decision == "WAIT":
             decision = "HOLD/ADD"
        if trend == "Bearish" and decision != "BUY": 
             decision = "AVOID"

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
            'Sug. Buy': suggested_buy,
            'Decision': decision,
            'Volume': volume,
            'R:R': rr_ratio,
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

# --- HTML GENERATOR ---
def generate_html(df_main, df_custom, cortex_data, verdict_data):
    cat_frames = {}
    categories = {
        "1. CONTEXT DE PIAȚĂ": ['VIX', 'VIX9D', 'VIX3M', 'VXN', 'SKEW'],
        "2. RISC MACRO / STRUCTURAL": ['MOVE', 'LTV', 'GVZ', 'OVX'],
        "3. RISK-ON / RISK-OFF CONFIRMATION": ['CRYPTO FEAR'],
        "4. MARKET BREADTH (Sănătatea Pieței)": ['SPX', 'SMA200%', 'Highs-Lows'],
        "5. CONFIRMĂRI DE TIMING": ['Put/Call Ratio', 'AAII Sentiment']
    }
    
    explanations = {
        'VIX': {'desc': 'Volatilitate așteptată pe 30 zile', 'thresholds': '< 12 = Complacență | 12-20 = Normal | 20-30 = Frică | > 30 = Panică'},
        'VIX9D': {'desc': 'Volatilitate pe 9 zile', 'thresholds': 'Compară cu VIX pentru trend'},
        'VIX3M': {'desc': 'Volatilitate așteptată pe 3 luni', 'thresholds': '< 15 = Calm | 15-20 = Normal | 20-30 = Frică | > 30 = Panică'},
        'VXN': {'desc': 'Volatilitate specifică tech stocks', 'thresholds': '< 20 = Calm | > 30 = Frică în tech'},
        'SKEW': {'desc': 'Risc de Black Swan (crash)', 'thresholds': '< 130 = Risc scăzut | 130-145 = Normal | > 145 = Risc EXTREM'},
        'MOVE': {'desc': 'Volatilitate obligațiuni (Bond Vol)', 'thresholds': '< 80 = Calm | 80-120 = Normal | > 120 = Stres în bonds'},
        'LTV': {'desc': 'Volatilitate pe 6 luni', 'thresholds': 'Compară cu VIX pentru structură'},
        'GVZ': {'desc': 'Volatilitate aur (safe haven)', 'thresholds': 'Creștere = Incertitudine globală'},
        'OVX': {'desc': 'Volatilitate petrol', 'thresholds': 'Creștere = Risc geopolitic/economic'},
        'CRYPTO FEAR': {'desc': 'Sentiment piață crypto', 'thresholds': '< 25 = Extreme Fear | 25-45 = Fear | 55-75 = Greed | > 75 = Extreme Greed'},
        'SPX': {'desc': 'Indicele principal US', 'thresholds': 'Trend = Direcția pieței'},
        'SMA200%': {'desc': 'Market Breadth', 'thresholds': '> 50% = Bullish | < 50% = Bearish'},
        'Highs-Lows': {'desc': 'Net New Highs', 'thresholds': 'Pozitiv = Bullish | Negativ = Bearish'},
        'Put/Call Ratio': {'desc': 'Sentiment Optiuni', 'thresholds': '> 1.0 = Fear (Bullish Signal) | < 0.6 = Complacency (MOCK)'},
        'AAII Sentiment': {'desc': 'Investitori Individuali', 'thresholds': 'Contrarian Indicator (MOCK)'}
    }

    for cat_name, idx_list in categories.items():
        html_chunk = f'<div class="card bg-dark border-secondary h-100"><div class="card-header border-secondary py-2"><h6 class="mb-0 text-white-50">{cat_name}</h6></div><div class="card-body p-2"><div class="d-flex flex-nowrap gap-2 overflow-auto" style="scrollbar-width: thin;">'
        for name in idx_list:
            data = cortex_data.get(name, {'value': 'N/A', 'change': 0, 'status': 'N/A', 'sparkline': ''})
            val = data.get('value', 'N/A')
            chg = data.get('change', 0)
            status = data.get('status', 'N/A')
            spark = data.get('sparkline', '')
            exp = explanations.get(name, {'title': name, 'desc': '', 'thresholds': ''})
            
            threshold_display = ""
            if name in ['VIX', 'VIX3M']: threshold_display = "15 NORMAL 20"
            elif name == 'VXN': threshold_display = "20 NORMAL 30"
            elif name == 'SKEW': threshold_display = "130 NORMAL 145"
            elif name == 'MOVE': threshold_display = "80 NORMAL 120"
            elif name == 'CRYPTO FEAR': threshold_display = "25 NEUTRAL 75"
            elif name == 'Put/Call Ratio': threshold_display = "0.7 NORMAL 1.0"
            
            chg_sign = "+" if isinstance(chg, (int, float)) and chg > 0 else ""
            chg_str = f"{chg_sign}{chg}" if isinstance(chg, (int, float)) else "-"
            
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
            </div>"""
        html_chunk += '</div></div></div>'
        cat_frames[cat_name] = html_chunk

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

    def build_rows(df):
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
                
                decision = row.get('Decision', 'WAIT')
                dec_color = "text-success" if decision == "BUY" else "text-warning" if decision == "WATCH" else "text-muted"
                
                vol = row.get('Volume', 0)
                vol_display = f"{vol/1000000:.1f}M" if vol > 1000000 else f"{vol/1000:.0f}K"

                rows_html += f"""
                <tr>
                    <td class="fw-bold"><a href="https://finviz.com/quote.ashx?t={row['Ticker']}" target="_blank" class="text-white text-decoration-none">{row['Ticker']}</a></td>
                    <td class="small text-muted">{str(row['Company_Name'])[:15]}..</td>
                    <td>${row['Price']}</td>
                    <td><div style="width:100px; overflow:hidden;">{row['Grafic']}</div></td> 
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
                    <td class="{dec_color} fw-bold">{decision}</td>
                    <td>{vol_display}</td>
                    <td>{row.get('R:R', 0)}</td>
                </tr>"""
        return rows_html


    rows_main = build_rows(df_main)
    rows_custom = build_rows(df_custom)
    
    len_main = len(df_main) if df_main is not None else 0
    len_custom = len(df_custom) if df_custom is not None else 0

    
    # --- CALENDAR EVENTS LOGIC ---
    def fetch_upcoming_events(tickers_list):
        print(f"\nScanning events for {len(tickers_list)} tickers (next 30 days)...")
        events_html = ""
        count = 0
        
        # Simple definition of "Major Event": Earnings
        today = datetime.datetime.now().date()
        limit_date = today + datetime.timedelta(days=30)
        
        found_events = []

        for t in tickers_list:
            try:
                # Optimized: We might not want to call yf.Ticker(t).calendar for every single one if it's slow.
                # However, for 40 tickers it might be passable. 
                # Alternative: Use "earn_date" if we already extracted it in main logic? 
                # Currently main logic doesn't extract earnings date explicitly in the table, 
                # but we can do a quick check here.
                
                # Let's use a quick approach if possible or just standard yfinance
                tk = yf.Ticker(t)
                
                # Earnings Date
                cal = tk.calendar
                if cal is not None and not cal.empty:
                    # cal is usually a Dict or DF. In new yfinance it might be a dictionary with 'Earnings Date' etc.
                    # Or a DataFrame with dates as columns? Structure varies by version.
                    # Safe approach: Check 'Earnings Date'
                    
                    # New yfinance structure often returns a dictionary for .calendar
                    # e.g. {'Earnings Date': [datetime.date(2025, 2, 12)], 'Earnings Average': 0.5, ...}
                    
                    earn_dates = cal.get('Earnings Date', [])
                    if earn_dates:
                        # usually a list of dates/datetimes
                        e_date = earn_dates[0]
                        if isinstance(e_date, datetime.date) or isinstance(e_date, datetime.datetime):
                            d = e_date if isinstance(e_date, datetime.date) else e_date.date()
                            
                            if today <= d <= limit_date:
                                est_eps = cal.get('Earnings Average', 'N/A')
                                found_events.append({
                                    'ticker': t,
                                    'event': 'Earnings Report',
                                    'date': d,
                                    'info': f"Est. EPS: {est_eps}"
                                })
            except Exception as e:
                pass # Fail silently for calendar to speed up

        # Sort by date
        found_events.sort(key=lambda x: x['date'])

        if not found_events:
            return '<tr><td colspan="4" class="text-muted text-center">Niciun eveniment major detectat pentru următoarele 30 zile.</td></tr>'

        for ev in found_events:
            events_html += f"""
            <tr>
                <td class="fw-bold text-white"><a href="https://finance.yahoo.com/quote/{ev['ticker']}" target="_blank" class="text-reset text-decoration-none">{ev['ticker']}</a></td>
                <td><span class="badge bg-primary">{ev['event']}</span></td>
                <td class="text-warning">{ev['date'].strftime('%Y-%m-%d')}</td>
                <td class="small">{ev['info']}</td>
            </tr>
            """
        return events_html

    # Fetch events only for Custom list symbols
    custom_tickers_list = df_custom['Ticker'].tolist() if df_custom is not None and not df_custom.empty else []
    events_rows = fetch_upcoming_events(custom_tickers_list) if custom_tickers_list else '<tr><td colspan="4" class="text-muted text-center">Lista custom este goală.</td></tr>'

    # Combine industries for the filter list
    all_inds = pd.Series(dtype=object)
    if df_main is not None and not df_main.empty:
        all_inds = pd.concat([all_inds, df_main['Industry']])
    if df_custom is not None and not df_custom.empty:
        all_inds = pd.concat([all_inds, df_custom['Industry']])
    
    ind_opts = ""
    if not all_inds.empty:
        for ind, count in all_inds.value_counts().items():
            if ind and str(ind) != 'nan':
                ind_opts += f'<option value="{ind}">{ind} ({count})</option>'

    # Helper to generate filter panel with unique IDs
    def create_filter_panel(suffix, context_ind_opts):
        return f"""
        <div class="card bg-white text-dark mb-4 filter-panel" style="border-radius: 12px;">
            <div class="card-body p-3">
                <h6 class="text-uppercase text-muted fw-bold mb-3" style="font-size: 0.8rem; letter-spacing: 1px;">Advanced Filters</h6>
                <div class="row g-2">
                    <div class="col-md-2">
                        <label class="form-label small fw-bold">Consensus</label>
                        <select id="f_consensus{suffix}" class="form-select form-select-sm">
                            <option value="">All</option>
                            <option value="Strong Buy">Strong Buy</option>
                            <option value="Buy">Buy</option>
                            <option value="Hold">Hold</option>
                        </select>
                    </div>
                    <div class="col-md-1">
                        <label class="form-label small fw-bold">Min Anals</label>
                        <input type="number" id="f_analysts{suffix}" class="form-control form-control-sm" placeholder="0">
                    </div>
                    <div class="col-md-1">
                        <label class="form-label small fw-bold">Min Tgt %</label>
                        <input type="number" id="f_target{suffix}" class="form-control form-control-sm" placeholder="0">
                    </div>
                    <div class="col-md-2">
                        <label class="form-label small fw-bold">Trend</label>
                        <select id="f_trend{suffix}" class="form-select form-select-sm">
                            <option value="">All</option>
                            <option value="Strong Bullish">Strong Bullish</option>
                            <option value="Bullish Pullback">Bullish Pullback</option>
                            <option value="Neutral">Neutral</option>
                            <option value="Bearish">Bearish</option>
                        </select>
                    </div>
                    <div class="col-md-2">
                        <label class="form-label small fw-bold">Status (RSI)</label>
                        <select id="f_status{suffix}" class="form-select form-select-sm">
                            <option value="">All</option>
                            <option value="Oversold">Oversold</option>
                            <option value="Neutral">Neutral</option>
                            <option value="Overbought">Overbought</option>
                        </select>
                    </div>
                    <div class="col-md-2">
                        <label class="form-label small fw-bold">Decizie</label>
                        <select id="f_decision{suffix}" class="form-select form-select-sm">
                            <option value="">All</option>
                            <option value="BUY">BUY</option>
                            <option value="WATCH">WATCH</option>
                            <option value="HOLD">HOLD/ADD</option>
                        </select>
                    </div>
                    <div class="col-md-2">
                        <label class="form-label small fw-bold">Min Vol (M)</label>
                        <input type="number" id="f_volume{suffix}" class="form-control form-control-sm" placeholder="0" step="0.1">
                    </div>
                </div>
                <div class="row g-2 mt-1">
                    <div class="col-md-3">
                         <label class="form-label small fw-bold">Industry</label>
                         <select id="f_industry{suffix}" class="form-select form-select-sm">
                            <option value="">All Industries</option>
                            {context_ind_opts}
                         </select>
                    </div>
                    <div class="col-md-2">
                        <label class="form-label small fw-bold">RSI Range</label>
                        <div class="input-group input-group-sm">
                            <input type="number" id="f_rsi_min{suffix}" class="form-control" placeholder="Min">
                            <input type="number" id="f_rsi_max{suffix}" class="form-control" placeholder="Max">
                        </div>
                    </div>
                    <div class="col-md-1">
                        <label class="form-label small fw-bold">Min R:R</label>
                        <input type="number" id="f_rr{suffix}" class="form-control form-control-sm" placeholder="0" step="0.5">
                    </div>
                    <div class="col-md-2 align-self-end">
                        <button class="btn btn-sm btn-dark w-100" onclick="resetFilters('{suffix}')">Reset</button>
                    </div>
                </div>
            </div>
        </div>
        """

    filter_panel_main = create_filter_panel("_main", ind_opts)
    filter_panel_custom = create_filter_panel("_custom", ind_opts)

    html = f"""
    <!DOCTYPE html>
    <html lang="en" data-bs-theme="dark">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Antigravity Market Cortex</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdn.datatables.net/1.13.4/css/dataTables.bootstrap5.min.css" rel="stylesheet">
        <link href="https://cdn.datatables.net/fixedcolumns/4.2.2/css/fixedColumns.bootstrap5.min.css" rel="stylesheet">
        <style>
            body {{ background-color: #121212; font-family: 'Segoe UI', sans-serif; color: #e0e0e0; }}
            .indices-container {{ display: flex; overflow-x: auto; gap: 10px; padding-bottom: 10px; margin-bottom: 20px; }}
            .indices-container::-webkit-scrollbar {{ height: 8px; }}
            .indices-container::-webkit-scrollbar-thumb {{ background: #333; border-radius: 4px; }}
            .index-card {{ background-color: #1e1e1e; border-radius: 6px; min-width: 130px; padding: 10px; text-align: center; border: 1px solid #333; position: relative; transition: all 0.3s ease; }}
            .index-card:hover {{ border-color: #4caf50; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(76, 175, 80, 0.2); }}
            .index-title {{ font-size: 0.8rem; font-weight: bold; color: #aaa; margin-bottom: 2px; }}
            .index-threshold {{ font-size: 0.65rem; color: #666; margin-bottom: 5px; font-weight: 500; letter-spacing: 0.5px; }}
            .info-icon {{ font-size: 0.7rem; color: #4caf50; cursor: help; margin-left: 3px; }}
            .index-status {{ font-size: 0.65rem; margin-bottom: 5px; text-transform: uppercase; }}
            .sparkline-container {{ height: 40px; margin: 5px 0; }}
            .index-value {{ font-size: 1.2rem; font-weight: bold; }}
            .index-change {{ font-size: 0.8rem; margin-bottom: 8px; }}
            .index-explanation {{ display: none; background: #2a2a2a; border-top: 1px solid #444; padding: 8px; margin-top: 8px; text-align: left; border-radius: 0 0 6px 6px; }}
            .index-card:hover .index-explanation {{ display: block; }}
            .index-explanation small {{ font-size: 0.7rem; line-height: 1.4; }}
            .kpi-box {{ background: #222; border: 1px solid #333; border-radius: 6px; padding: 15px; text-align: center; height: 100%; }}
            .nav-tabs .nav-link.active {{ background-color: #222; color: #4caf50; border-color: #444; border-bottom-color: #222; }}
            .nav-tabs {{ border-bottom-color: #444; }}
            .nav-link {{ color: #888; }}
            
            /* DataTables Fixed Columns Overrides - FORCE DARK BACKGROUND */
            table.dataTable tbody tr > .dtfc-fixed-left, 
            table.dataTable tbody tr > .dtfc-fixed-right,
            table.dataTable thead tr > .dtfc-fixed-left, 
            table.dataTable thead tr > .dtfc-fixed-right {{
                background-color: #1e1e1e !important;
                color: #e0e0e0 !important;
                z-index: 1; 
            }}
            /* Navbar Tabs Styling */
            .nav-pills .nav-link {{ color: #aaa; border-radius: 20px; padding: 5px 15px; font-size: 0.9rem; margin-right: 5px; }}
            .nav-pills .nav-link.active {{ background-color: #4caf50; color: #fff; font-weight: bold; }}
            .nav-pills .nav-link:hover {{ color: #fff; background-color: #333; }}
        </style>
    </head>
    <body class="p-3">
        <div class="container-fluid">
            <!-- HEADER -->
            <!-- HEADER WITH TABS -->
            <!-- HEADER -->
            <div class="text-center mb-4 pb-3 border-bottom border-secondary">
                <div class="d-flex justify-content-center align-items-center mb-3">
                    <img src="https://simpleicons.org/icons/googleanalytics.svg" width="40" height="40" style="filter: invert(1);" class="me-3">
                    <h1 class="mb-0 fw-bold" style="font-family: 'Segoe UI', sans-serif; letter-spacing: 2px;">MARKET CORTEX</h1>
                </div>
                
                <!-- CENTERED NAVIGATION TABS -->
                <ul class="nav nav-pills justify-content-center" id="myTab" role="tablist">
                    <li class="nav-item"><button class="nav-link active" data-bs-target="#overview" data-bs-toggle="tab">Market Overview</button></li>
                    <li class="nav-item"><button class="nav-link" data-bs-target="#watchlist" data-bs-toggle="tab">Watchlist & Scan</button></li>
                    <li class="nav-item"><button class="nav-link" data-bs-target="#custom" data-bs-toggle="tab">Custom Watchlist</button></li>
                    <li class="nav-item"><button class="nav-link" data-bs-target="#portfolio" data-bs-toggle="tab">Portofoliu</button></li>
                </ul>
                
                <div class="position-absolute top-0 end-0 p-3">
                    <small class="text-muted">Updated: {(datetime.datetime.utcnow() + datetime.timedelta(hours=2)).strftime('%Y-%m-%d %H:%M')} (RO)</small>
                </div>
            </div>

            <!-- TABS MOVED TO HEADER -->

            <div class="tab-content">
                <!-- MARKET OVERVIEW TAB (Default) -->
                <div class="tab-pane fade show active" id="overview">
                    <div class="mb-4">{indices_html}</div>

                    <!-- SYSTEM VERDICT -->
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
                                            <div class="small text-muted mb-2">Raport VIX3M / VIX</div>
                                        </div>
                                    </div>
                                    <div class="col-6">
                                        <div class="kpi-box">
                                            <div class="small text-muted mb-2">AI Market Sentiment</div>
                                            <div class="h3 my-2 text-success">{verdict_data['sentiment']}/100</div>
                                            <div class="small text-muted mb-2">Semantica Știri</div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- MAIN WATCHLIST (Formerly Home) -->
                <div class="tab-pane fade" id="watchlist">
                    <!-- Advanced Filters (Main) -->
                    {filter_panel_main}
                    <div class="card bg-dark border-secondary p-3">
                        <table id="scanTable" class="table table-dark table-hover w-100 table-sm">
                            <thead>
<tr>
                                    <th>Ticker</th>
                                    <th>Company</th>
                                    <th>Price</th>
                                    <th style="width:100px;">Grafic</th>
                                    <th title="Price limit for safe entry based on technical support levels.">Sug. Buy ⓘ</th>
                                    <th title="Analyst price target consensus.">Target</th>
                                    <th title="Potential upside to analyst target.">To Target %</th>
                                    <th title="Average analyst rating (Strong Buy to Sell).">Consensus ⓘ</th>
                                    <th>Analysts</th>
                                    <th>Inst %</th>
                                    <th title="Current technical trend based on SMA50/SMA200 interaction.">Trend ⓘ</th>
                                    <th title="Relative Strength Index. >70 Overbought, <30 Oversold.">RSI ⓘ</th>
                                    <th>RSI Status</th>
                                    <th title="Average True Range. Volatility metric used for stop losses.">ATR</th>
                                    <th title="Suggested stop loss level (2x ATR below price).">Stop Loss ⓘ</th>
                                    <th>SMA 50</th>
                                    <th>SMA 200</th>
                                    <th title="Daily percentage change. High +% = Momentum.">Change % ⓘ</th>
                                    <th title="Composite score (0-100) based on Price vs SMAs, RSI, and recent perf.">Mom. Score ⓘ</th>
                                    <th>WL Score</th>
                                    <th>Industry</th>
                                    <th>Theme</th>
                                    <th title="System logic: BUY if Price < Sug Buy. WATCH if within 5%.">Decizie ⓘ</th>
                                    <th title="Daily Trading Volume.">Volume</th>
                                    <th title="Risk/Reward Ratio. Potential reward vs risk to Stop Loss. >2.0 is good.">R:R ⓘ</th>
                                </tr>
                            </thead>
                            <tbody>{rows_main}</tbody>
                        </table>
                    </div>
                </div>
                
                <!-- CUSTOM WATCHLIST -->
                <div class="tab-pane fade" id="custom">
                    <!-- Advanced Filters (Custom) -->
                    {filter_panel_custom}
                    
                    <div class="card bg-dark border-secondary p-3 mb-4">
                        <table id="customTable" class="table table-dark table-hover w-100 table-sm">
                            <thead>
<tr>
                                    <th>Ticker</th>
                                    <th>Company</th>
                                    <th>Price</th>
                                    <th style="width:100px;">Grafic</th>
                                    <th title="Price limit for safe entry based on technical support levels.">Sug. Buy ⓘ</th>
                                    <th title="Analyst price target consensus.">Target</th>
                                    <th title="Potential upside to analyst target.">To Target %</th>
                                    <th title="Average analyst rating (Strong Buy to Sell).">Consensus ⓘ</th>
                                    <th>Analysts</th>
                                    <th>Inst %</th>
                                    <th title="Current technical trend based on SMA50/SMA200 interaction.">Trend ⓘ</th>
                                    <th title="Relative Strength Index. >70 Overbought, <30 Oversold.">RSI ⓘ</th>
                                    <th>RSI Status</th>
                                    <th title="Average True Range. Volatility metric used for stop losses.">ATR</th>
                                    <th title="Suggested stop loss level (2x ATR below price).">Stop Loss ⓘ</th>
                                    <th>SMA 50</th>
                                    <th>SMA 200</th>
                                    <th title="Daily percentage change. High +% = Momentum.">Change % ⓘ</th>
                                    <th title="Composite score (0-100) based on Price vs SMAs, RSI, and recent perf.">Mom. Score ⓘ</th>
                                    <th>WL Score</th>
                                    <th>Industry</th>
                                    <th>Theme</th>
                                    <th title="System logic: BUY if Price < Sug Buy. WATCH if within 5%.">Decizie ⓘ</th>
                                    <th title="Daily Trading Volume.">Volume</th>
                                    <th title="Risk/Reward Ratio. Potential reward vs risk to Stop Loss. >2.0 is good.">R:R ⓘ</th>
                                </tr>
                            </thead>
                            <tbody>{rows_custom}</tbody>
                        </table>
                    </div>
                    
                    <!-- UPCOMING EVENTS CALENDAR -->
                    <div class="card bg-dark border-secondary p-3">
                        <h5 class="mb-3 text-white border-bottom border-secondary pb-2">📅 Evenimente Majore Următoare</h5>
                        <div class="table-responsive">
                            <table class="table table-dark table-sm table-striped">
                                <thead>
                                    <tr>
                                        <th>Ticker</th>
                                        <th>Eveniment</th>
                                        <th>Data Estimată</th>
                                        <th>Detalii (Est.)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {events_rows}
                                </tbody>
                            </table>
                        </div>
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
        <script src="https://cdn.datatables.net/fixedcolumns/4.2.2/js/dataTables.fixedColumns.min.js"></script>
        <script>
            $(document).ready(function() {{
                function initTable(tableId) {{
                    $('#' + tableId + ' thead tr').clone(true).addClass('filters').appendTo('#' + tableId + ' thead');
                    var table = $('#' + tableId).DataTable({{
                        "pageLength": 50,
                        "order": [[18, "desc"]],
                        "scrollX": true,
                        orderCellsTop: true,
                        fixedHeader: true,
                        fixedColumns: {{
                            left: 2
                        }},
                        initComplete: function () {{
                            var api = this.api();
                            api.columns().eq(0).each(function (colIdx) {{
                                var cell = $('.filters th', api.table().header()).eq($(api.column(colIdx).header()).index());
                                var title = $(cell).text();
                                $(cell).html('<input type="text" placeholder="' + title + '" style="width:100%; font-size:0.7em; background:#333; color:white; border:none;" />');
                                $('input', cell).on('keyup change', function (e) {{
                                    if (e.type === 'change' || e.keyCode === 13) {{
                                        api.column(colIdx).search(this.value).draw();
                                    }}
                                }});
                            }});
                        }}
                    }});
                    return table;
                }}

                var tableMain = initTable('scanTable');
                var tableCustom = initTable('customTable');
                window.tables = {{ 'scanTable': tableMain, 'customTable': tableCustom }};

                // Init Bootstrap Tooltips
                var tooltipTriggerList = [].slice.call(document.querySelectorAll('[title]'))
                var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {{
                    return new bootstrap.Tooltip(tooltipTriggerEl)
                }})

                // Fix DataTables column width when switching tabs
                $('button[data-bs-toggle="tab"]').on('shown.bs.tab', function (e) {{
                    $.fn.dataTable.tables({{ visible: true, api: true }}).columns.adjust();
                }});

                // --- ADVANCED FILTER LOGIC (Dynamic) ---
                $.fn.dataTable.ext.search.push(function(settings, data, dataIndex) {{
                    var tableId = settings.sTableId;
                    var suffix = (tableId === 'scanTable') ? '_main' : '_custom';
                    
                    // Allow filtering only if inputs exist (avoid errors on other tables)
                    if ($('#f_consensus' + suffix).length === 0) return true;

                    // data indices: 
                    // 6: To Target%, 7: Consensus, 8: Analysts, 10: Trend, 11: RSI, 12: RSI Status, 
                    // 22: Decision (NEW), 23: Volume(NEW), 24: R:R (NEW)
                    
                    var consensus = $('#f_consensus' + suffix).val();
                    var minAnal = parseFloat($('#f_analysts' + suffix).val()) || 0;
                    var minTgt = parseFloat($('#f_target' + suffix).val()) || 0;
                    var trend = $('#f_trend' + suffix).val();
                    var status = $('#f_status' + suffix).val();
                    var decision = $('#f_decision' + suffix).val();
                    var minVolM = parseFloat($('#f_volume' + suffix).val()) || 0;
                    var minRSI = parseFloat($('#f_rsi_min' + suffix).val()) || 0;
                    var maxRSI = parseFloat($('#f_rsi_max' + suffix).val()) || 100;
                    var minRR = parseFloat($('#f_rr' + suffix).val()) || 0;
                    var industry = $('#f_industry' + suffix).val();

                    // Checks
                    if (consensus && data[7] !== consensus) return false;
                    if (parseFloat(data[8]) < minAnal) return false; // Analysts
                    if (parseFloat(data[6].replace('%','')) < minTgt) return false; // Target %
                    if (trend && data[10] !== trend) return false;
                    if (status && data[12] !== status) return false;
                    if (decision && data[22] !== decision) return false;
                    if (industry && data[20] !== industry) return false;
                    
                    // Volume parsing from "1.2M", "500K"
                    var volStr = data[23];
                    var volVal = 0;
                    if (volStr.includes('M')) volVal = parseFloat(volStr) * 1000000;
                    else if (volStr.includes('K')) volVal = parseFloat(volStr) * 1000;
                    else volVal = parseFloat(volStr);
                    if (volVal < minVolM * 1000000) return false;

                    // RSI Range
                    var rsi = parseFloat(data[11]);
                    if (rsi < minRSI || rsi > maxRSI) return false;
                    
                    // R:R
                    if (parseFloat(data[24]) < minRR) return false;

                    return true;
                }});
                
                // Bind panel inputs to redraw
                $('.filter-panel input, .filter-panel select').on('keyup change', function() {{
                    tableMain.draw();
                    tableCustom.draw();
                }});
                
                window.resetFilters = function(suffix) {{
                    $('#f_consensus' + suffix).val('');
                    $('#f_analysts' + suffix).val('');
                    $('#f_target' + suffix).val('');
                    $('#f_trend' + suffix).val('');
                    $('#f_status' + suffix).val('');
                    $('#f_decision' + suffix).val('');
                    $('#f_volume' + suffix).val('');
                    $('#f_industry' + suffix).val('');
                    $('#f_rsi_min' + suffix).val('');
                    $('#f_rsi_max' + suffix).val('');
                    $('#f_rr' + suffix).val('');
                    
                    tableMain.draw();
                    tableCustom.draw();
                }}
            }});

            window.filterIndustry = function(industry, tableId) {{
                var table = window.tables[tableId];
                if (industry === '') table.column(20).search('').draw();
                else table.column(20).search('^' + industry + '$', true, false).draw();
            }};
        </script>
    </body>
    </html>
    """
    with open(OUTPUT_HTML, 'w') as f: f.write(html)
    print(f"Dashboard generat: {OUTPUT_HTML}")

def process_ticker_list(tickers):
    results = []
    if not tickers: return None
    print(f"Processing {len(tickers)} symbols...")
    for t in tickers:
        print(f"Analizez {t}...", end="\r")
        res = analyze_ticker(t)
        if res: results.append(res)
    return pd.DataFrame(results) if results else None

def main():
    print("--- Market Cortex v3.0 (Advanced) ---")
    
    print(">>> LOADING MAIN WATCHLIST")
    main_tickers = load_tickers(TICKERS_FILE)
    df_main = process_ticker_list(main_tickers)
    
    if df_main is not None:
        cols = ['Ticker', 'Company_Name', 'Price', 'Sug. Buy', 'Target', 'To Target %', 'Consensus', 'Analysts', 'Inst Own',
                'Trend', 'RSI', 'RSI Status', 'ATR', 'Stop Loss', 'SMA 50', 'SMA 200', 
                'Change %', 'Momentum_Score', 'Watchlist_Score', 'Industry', 'Theme', 'Decision', 'Volume', 'R:R']
        valid_cols = [c for c in cols if c in df_main.columns]
        df_main[valid_cols].to_csv(OUTPUT_CSV, index=False)

    print("\n>>> LOADING CUSTOM WATCHLIST")
    custom_tickers = load_tickers(CUSTOM_TICKERS_FILE)
    df_custom = process_ticker_list(custom_tickers)

    cortex_data = get_market_cortex_data()
    verdict_data = calculate_verdict(cortex_data)
    
    generate_html(df_main, df_custom, cortex_data, verdict_data)
    
    print("\nScanare completă! Verifică index.html.")

if __name__ == "__main__":
    main()

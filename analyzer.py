# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
from data_loader import get_sector_cached

# 🌟 Global Cache to avoid Rate Limits
_GLOBAL_BULK_KLINE_CACHE = None

def calculate_sctr_ranks(tickers, lookback=20):
    """
    Calculates current and historical SCTR ranks to measure momentum acceleration.
    Based on the shared philosophy of O'Neil and Minervini (Relative Strength).
    """
    global _GLOBAL_BULK_KLINE_CACHE
    try:
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        _GLOBAL_BULK_KLINE_CACHE = raw_data
        data = raw_data['Close'] if 'Close' in raw_data else raw_data

        sctr_current = []
        sctr_historical = []

        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) < 200 + lookback: continue

                def get_sctr_raw(sub_series):
                    # Momentum components: Distance from MAs, Rate of Change, and RSI
                    sma200 = sub_series.rolling(200).mean().iloc[-1]
                    sma50 = sub_series.rolling(50).mean().iloc[-1]
                    
                    dist_200 = (sub_series.iloc[-1] / sma200 - 1) * 100 if sma200 else 0
                    dist_50 = (sub_series.iloc[-1] / sma50 - 1) * 100 if sma50 else 0
                    roc125 = (sub_series.iloc[-1] / sub_series.iloc[-125] - 1) * 100 if len(sub_series) >= 125 else 0
                    roc20 = (sub_series.iloc[-1] / sub_series.iloc[-20] - 1) * 100 if len(sub_series) >= 20 else 0
                    rsi = ta.rsi(sub_series, length=14).iloc[-1] if not pd.isna(ta.rsi(sub_series, length=14).iloc[-1]) else 50
                    
                    # Weighted score for Relative Strength
                    return (dist_200 * 0.3 + roc125 * 0.3) + (dist_50 * 0.15 + roc20 * 0.15) + (rsi * 0.1)

                raw_curr = get_sctr_raw(series)
                raw_hist = get_sctr_raw(series.iloc[:-lookback])

                sctr_current.append({'ticker': ticker, 'raw': raw_curr})
                sctr_historical.append({'ticker': ticker, 'raw': raw_hist})
            except:
                continue

        if not sctr_current: return {}, {}

        df_curr = pd.DataFrame(sctr_current)
        df_curr['rank'] = df_curr['raw'].rank(pct=True) * 99.9
        dict_curr = df_curr.set_index('ticker')['rank'].to_dict()

        df_hist = pd.DataFrame(sctr_historical)
        df_hist['rank'] = df_hist['raw'].rank(pct=True) * 99.9
        dict_hist = df_hist.set_index('ticker')['rank'].to_dict()

        return dict_curr, dict_hist
    except:
        return {}, {}

def check_trend_template(curr_p, sma50, sma150, sma200, low52, high52):
    """
    Implementation of Minervini's Trend Template.
    A stock must be in a confirmed uptrend before considering VCP.
    """
    cond = [
        curr_p > sma150 and curr_p > sma200,                      # Price above 150 & 200 SMA
        sma150 > sma200,                                          # 150 SMA above 200 SMA
        sma50 > sma150,                                           # 50 SMA above 150 SMA
        curr_p > sma50,                                           # Price above 50 SMA
        curr_p >= low52 * 1.3,                                    # Price at least 30% above 52-week low
        curr_p >= high52 * 0.75                                   # Price within 25% of 52-week high
    ]
    return sum(cond) >= 6

def analyze_vcp_contraction(close):
    """
    Analyze Volatility Contraction Pattern (VCP).
    Identifies if the stock is tightening (amplitude decreasing).
    """
    # Split data into 3 potential contraction waves
    # Simplified wave detection using rolling max-min
    # Wave 1: 60-30 days ago, Wave 2: 30-10 days ago, Wave 3: 10-0 days ago
    w1 = close.iloc[-60:-30]
    w2 = close.iloc[-30:-10]
    w3 = close.iloc[-10:]
    
    amp1 = (w1.max() - w1.min()) / w1.min()
    amp2 = (w2.max() - w2.min()) / w2.min()
    amp3 = (w3.max() - w3.min()) / w3.min()
    
    # VCP Core: Amplitudes must decrease (T1 > T2 > T3)
    is_contracting = (amp1 >= amp2) and (amp2 >= amp3)
    # Final wave must be tight (usually < 10-15%)
    is_tight = amp3 < 0.12
    
    return is_contracting, is_tight, amp3

def check_volume_dryup(vol, vol_ma20):
    """
    Checks for 'Quiet Point' - volume must dry up before a breakout.
    """
    # Average volume of the last 5 days should be significantly lower than 20-day average
    recent_vol = vol.iloc[-5:].mean()
    return recent_vol < vol_ma20 * 0.8

def check_vcp_advanced(ticker, sctr_map, sctr_hist_map, b_only, b_days):
    """
    Advanced VCP Detection integrating Livermore, O'Neil, and Minervini.
    """
    global _GLOBAL_BULK_KLINE_CACHE
    try:
        # 1. Data Extraction
        df = None
        if _GLOBAL_BULK_KLINE_CACHE is not None and not _GLOBAL_BULK_KLINE_CACHE.empty:
            if isinstance(_GLOBAL_BULK_KLINE_CACHE.columns, pd.MultiIndex):
                if ticker in _GLOBAL_BULK_KLINE_CACHE.columns.get_level_values(1):
                    df = _GLOBAL_BULK_KLINE_CACHE.xs(ticker, level=1, axis=1)
            else:
                df = _GLOBAL_BULK_KLINE_CACHE
        
        if df is None or df.empty:
            df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])
        if df.empty or len(df) < 200: return None

        close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']
        curr_p = float(close.iloc[-1])
        
        # Technical Indicators
        sma50 = ta.sma(close, 50).iloc[-1]
        sma150 = ta.sma(close, 150).iloc[-1]
        sma200 = ta.sma(close, 200).iloc[-1]
        low52 = float(close.tail(252).min())
        high52 = float(close.tail(252).max())
        vol_ma20 = vol.rolling(20).mean().iloc[-1]

        # ========== GATE 1: Minervini Trend Template ==========
        if not check_trend_template(curr_p, sma50, sma150, sma200, low52, high52):
            return None

        # ========== GATE 2: VCP Contraction Analysis ==========
        is_contracting, is_tight, final_amp = analyze_vcp_contraction(close)
        if not (is_contracting or is_tight): 
            return None

        # ========== GATE 3: Volume Dry-up (Quiet Point) ==========
        vol_dry_up = check_volume_dryup(vol, vol_ma20)
        # Note: Volume dry-up is critical for 'Pre-breakout', but breakout itself has high vol.
        
        # ========== GATE 4: SCTR Momentum ==========
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_hist = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 70: return None
        sctr_accelerating = (sctr_val - sctr_hist) > 1.0

        # ========== GATE 5: Pivot Point & Status ==========
        # Pivot is the highest peak of the tightest contraction area
        resistance = float(high.iloc[-b_days:].max())
        dist_to_pivot = (curr_p / resistance - 1) * 100
        
        status = ""
        if -1.5 <= dist_to_pivot <= 0.5:
            status = "⚡蓄勢待發"
        elif 0.5 < dist_to_pivot <= 5.0:
            status = "🔥 剛突破"
        elif 5.0 < dist_to_pivot <= 15.0 and (sctr_val > 90 or sctr_accelerating):
            status = "🚀 強勢續航"
        else:
            return None

        if b_only and status != "🔥 剛突破": return None
        # Require volume dry-up for pre-breakout stocks
        if status == "⚡蓄勢待發" and not vol_dry_up:
            return None

        # ========== Final Calculations: Risk & Reward ==========
        # Stop Loss: The lowest low of the tightest (last) contraction wave
        stop_loss = float(close.iloc[-10:].min()) 
        # Ensure stop loss isn't too far (max 7%)
        if (curr_p / stop_loss - 1) > 0.07:
            stop_loss = curr_p * 0.93
            
        risk = curr_p - stop_loss
        target_price = curr_p + (3.0 * risk) # 3R Reward
        
        vol_ratio = round(float(vol.iloc[-1]) / vol_ma20, 2)
        sector = get_sector_cached(ticker)
        
        tightness_label = "🎯 極緊" if final_amp < 0.05 else "✅ 緊湊" if final_amp < 0.12 else "🔸 尚可"

        return [
            ticker, round(curr_p, 2), round((1-curr_p/high52)*100, 2), sctr_val, tightness_label,
            vol_ratio, status, sector,
            round(resistance, 2), round(stop_loss, 2), round(target_price, 2)
        ]
    except Exception:
        return None

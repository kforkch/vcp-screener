# analyzer.py - 簡潔穩定版
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import logging
import time
from data_loader import get_sector_cached

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def calculate_sctr_ranks(tickers, lookback=20, batch_size=20):
    """分批下載 SCTR"""
    sctr_current = []
    sctr_hist = []
    
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            data = yf.download(
                batch, 
                period="1y", 
                interval="1d", 
                progress=False, 
                auto_adjust=True,
                threads=False,
                timeout=30
            )
            close = data['Close'] if 'Close' in data.columns else data
            
            for ticker in batch:
                try:
                    series = close[ticker].dropna() if isinstance(close, pd.DataFrame) else pd.Series(close).dropna()
                    if len(series) < 250:
                        continue
                    
                    def compute_raw_sctr(s):
                        if len(s) < 200: return 0.0
                        roc125 = (s.iloc[-1] / s.iloc[-125] - 1) * 100
                        roc20 = (s.iloc[-1] / s.iloc[-20] - 1) * 100
                        dist200 = (s.iloc[-1] / s.rolling(200).mean().iloc[-1] - 1) * 100
                        dist50 = (s.iloc[-1] / s.rolling(50).mean().iloc[-1] - 1) * 100
                        rsi = ta.rsi(s, length=14).iloc[-1]
                        return (dist200 * 0.30 + roc125 * 0.30) + (dist50 * 0.20 + roc20 * 0.15) + (rsi * 0.05)
                    
                    curr = compute_raw_sctr(series)
                    hist = compute_raw_sctr(series.iloc[:-lookback])
                    
                    sctr_current.append({'ticker': ticker, 'score': curr})
                    sctr_hist.append({'ticker': ticker, 'score': hist})
                except:
                    continue
            time.sleep(2.0)
        except Exception as e:
            logging.warning(f"Batch failed: {e}")
            time.sleep(5)
    
    if not sctr_current:
        return {}, {}
    
    df_curr = pd.DataFrame(sctr_current)
    df_curr['sctr'] = df_curr['score'].rank(pct=True) * 99.9
    df_hist = pd.DataFrame(sctr_hist)
    df_hist['sctr'] = df_hist['score'].rank(pct=True) * 99.9
    
    return (df_curr.set_index('ticker')['sctr'].to_dict(),
            df_hist.set_index('ticker')['sctr'].to_dict())


def check_vcp_advanced(ticker, sctr_map, sctr_hist_map, b_only=False, b_days=20):
    """VCP 檢測"""
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True, timeout=20)
        if df.empty or len(df) < 200:
            return None
            
        close = df['Close'].squeeze()
        high = df['High'].squeeze()
        low = df['Low'].squeeze()
        vol = df['Volume'].squeeze()
        
        curr_p = float(close.iloc[-1])
        
        sma50 = ta.sma(close, 50).iloc[-1]
        sma150 = ta.sma(close, 150).iloc[-1]
        sma200 = ta.sma(close, 200).iloc[-1]
        
        if not (curr_p > sma150 > sma200 and sma50 > sma150 and curr_p > sma50):
            return None
        
        def range_ratio(s):
            if len(s) < 5: return 1.0
            return (s.max() - s.min()) / s.min()
        
        t1 = range_ratio(close.iloc[-65:-35])
        t2 = range_ratio(close.iloc[-35:-12])
        t3 = range_ratio(close.iloc[-12:])
        recent_tight = range_ratio(close.iloc[-8:])
        
        if not (t1 > t2 > t3 and t3 < 0.11 and recent_tight < 0.095):
            return None
        
        tightness = "✅ 極緊" if recent_tight < 0.05 else "✅ 緊湊"
        
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        if float(vol.iloc[-1]) > float(vol_ma20) * 2.0:
            return None
        
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_old = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 68 or (sctr_val - sctr_old) < 0.5:
            return None
        
        recent_max = float(close.iloc[-(b_days + 1):-1].max())
        is_breakout = curr_p > recent_max * 1.005
        if b_only and not is_breakout:
            return None
        
        status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢向上"
        
        atr = ta.atr(high, low, close, length=14).iloc[-1]
        pivot = recent_max
        stop_loss = curr_p - 1.8 * float(atr) if not pd.isna(atr) else curr_p * 0.92
        target = curr_p + 3.0 * (curr_p - stop_loss)
        
        dist_high = round((1 - curr_p / float(close.max())) * 100, 2)
        vol_ratio = round(float(vol.iloc[-1]) / float(vol_ma20), 2)
        sector = get_sector_cached(ticker)
        quality = 88 if is_breakout and "極緊" in tightness else 72 if is_breakout else 55
        
        return [ticker, round(curr_p, 2), dist_high, sctr_val, tightness,
                vol_ratio, status, sector, round(pivot, 2), round(stop_loss, 2),
                round(target, 2), quality]
        
    except Exception as e:
        logging.error(f"Error on {ticker}: {e}")
        return None

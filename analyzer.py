# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from data_loader import get_sector_cached

def calculate_sctr_ranks(tickers):
    try:
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        if 'Close' not in raw_data: return {}
        data = raw_data['Close']
        sctr_data = []
        for ticker in tickers:
            try:
                series = data[ticker].dropna()
                if len(series) < 200: continue
                sma200 = series.rolling(200).mean().iloc[-1]
                sma50 = series.rolling(50).mean().iloc[-1]
                dist_200 = (series.iloc[-1] / sma200 - 1) * 100
                dist_50 = (series.iloc[-1] / sma50 - 1) * 100
                roc125 = (series.iloc[-1] / series.iloc[-125] - 1) * 100
                roc20 = (series.iloc[-1] / series.iloc[-20] - 1) * 100
                rsi = ta.rsi(series, length=14).iloc[-1]
                raw = (dist_200*0.3 + roc125*0.3) + (dist_50*0.15 + roc20*0.15) + (rsi*0.1)
                sctr_data.append({'ticker': ticker, 'raw': raw})
            except: continue
        if not sctr_data: return {}
        df_sctr = pd.DataFrame(sctr_data)
        df_sctr['rank'] = df_sctr['raw'].rank(pct=True) * 99.9
        return df_sctr.set_index('ticker')['rank'].to_dict()
    except: return {}

def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        high = df['High'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['High']
        low = df['Low'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Low']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        
        curr_p = float(close.iloc[-1])
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        
        # 【修正】嚴格執行均線對齊：50 > 150 > 200
        is_uptrend = (sma50 > sma150) and (sma150 > sma200)
        
        cond = [
            curr_p > sma150 and curr_p > sma200, 
            is_uptrend,
            curr_p > sma50,
            curr_p >= (float(close.min()) * 1.25), 
            curr_p >= (float(close.max()) * 0.75)
        ]
        
        if sum(cond) < 5: return None
        
        # 波動收縮檢測
        recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
        prev_range = (close.iloc[-25:-5].max() - close.iloc[-25:-5].min()) / close.iloc[-25:-5].min()
        is_tight = "✅ 緊湊" if recent_range < (prev_range * 0.7) else "❌ 鬆散"
        
        recent_max = float(close.iloc[-(b_days+1):-1].max())
        is_breakout = curr_p > recent_max
        if b_only and not is_breakout: return None
        
        atr_series = ta.atr(high, low, close, length=14)
        atr_val = float(atr_series.iloc[-1]) if not atr_series.isna().iloc[-1] else (float(high.iloc[-1]) - float(low.iloc[-1]))
        
        pivot_point = recent_max
        stop_loss = curr_p - (2.0 * atr_val)
        target_price = curr_p + (3.0 * (curr_p - stop_loss))
        
        return [
            ticker, round(curr_p, 2), round((1 - curr_p/float(close.max())) * 100, 2),
            round(sctr_map.get(ticker, 0), 1), is_tight, 
            round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2),
            f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢向上",
            get_sector_cached(ticker),
            round(pivot_point, 2), round(stop_loss, 2), round(target_price, 2)
        ]
    except: return None

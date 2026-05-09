# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import time
from data_loader import get_sector_cached

# 🌟 建立全局快取變數，用於儲存批量下載的 K 線
_GLOBAL_BULK_KLINE_CACHE = None

def calculate_sctr_ranks(tickers, lookback=20):
    """
    計算當前與 lookback 天前的 SCTR，用來衡量動能是否持續攀升
    """
    global _GLOBAL_BULK_KLINE_CACHE
    try:
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        _GLOBAL_BULK_KLINE_CACHE = raw_data
        
        data = raw_data['Close'] if 'Close' in raw_data else raw_data
        sctr_current, sctr_historical = [], []

        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) < 200 + lookback: continue

                def get_sctr_raw(sub_series):
                    sma200, sma50 = sub_series.rolling(200).mean().iloc[-1], sub_series.rolling(50).mean().iloc[-1]
                    dist_200, dist_50 = (sub_series.iloc[-1]/sma200-1)*100, (sub_series.iloc[-1]/sma50-1)*100
                    roc125, roc20 = (sub_series.iloc[-1]/sub_series.iloc[-125]-1)*100, (sub_series.iloc[-1]/sub_series.iloc[-20]-1)*100
                    rsi = ta.rsi(sub_series, length=14).iloc[-1]
                    return (dist_200*0.3 + roc125*0.3) + (dist_50*0.15 + roc20*0.15) + (rsi*0.1)

                raw_curr = get_sctr_raw(series)
                raw_hist = get_sctr_raw(series.iloc[:-lookback])
                sctr_current.append({'ticker': ticker, 'raw': raw_curr})
                sctr_historical.append({'ticker': ticker, 'raw': raw_hist})
            except Exception: continue

        if not sctr_current: return {}, {}
        df_curr = pd.DataFrame(sctr_current)
        df_curr['rank'] = df_curr['raw'].rank(pct=True) * 99.9
        df_hist = pd.DataFrame(sctr_historical)
        df_hist['rank'] = df_hist['raw'].rank(pct=True) * 99.9
        return df_curr.set_index('ticker')['rank'].to_dict(), df_hist.set_index('ticker')['rank'].to_dict()
    except Exception: return {}, {}

def check_vcp_advanced(ticker, sctr_map, sctr_hist_map, b_only, b_days):
    """
    整合 Minervini SEPA 標準與多段波動收縮判定[cite: 3, 10]
    """
    global _GLOBAL_BULK_KLINE_CACHE
    try:
        df = None
        if _GLOBAL_BULK_KLINE_CACHE is not None and not _GLOBAL_BULK_KLINE_CACHE.empty:
            if isinstance(_GLOBAL_BULK_KLINE_CACHE.columns, pd.MultiIndex):
                if ticker in _GLOBAL_BULK_KLINE_CACHE.columns.get_level_values(1):
                    df = _GLOBAL_BULK_KLINE_CACHE.xs(ticker, level=1, axis=1)
        
        if df is None or df.empty:
            df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        
        df = df.dropna(subset=['Close', 'High', 'Low', 'Volume'])
        if df.empty or len(df) < 200 or df['Volume'].iloc[-1] == 0: return None

        close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']
        curr_p = float(close.iloc[-1])
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.tail(252).min()), float(close.tail(252).max())

        # SEPA 趨勢模板[cite: 10]
        cond = [curr_p > sma150, curr_p > sma200, sma150 > sma200, sma50 > sma150, curr_p > sma50*0.98, curr_p >= low52*1.25, curr_p >= high52*0.70]
        if sum(cond) < 6: return None

        # VCP 判定與成交量枯竭
        vol_ma50, vol_ma20 = vol.rolling(50).mean().iloc[-1], vol.rolling(20).mean().iloc[-1]
        has_quiet_point = vol.iloc[-max(10, b_days):-1].min() < (vol_ma50 * 0.85)
        v1 = (close.iloc[-40:-20].max() - close.iloc[-40:-20].min()) / close.iloc[-40:-20].min()
        v3 = (close.iloc[-10:].max() - close.iloc[-10:].min()) / close.iloc[-10:].min()
        is_contracting = v3 < 0.15 and v3 <= v1 * 1.25

        # 緊湊度 (ATR 基準)
        atr = ta.atr(high, low, close, length=14).iloc[-1]
        w1_range = close.iloc[-5:].max() - close.iloc[-5:].min()
        if w1_range <= 1.5 * atr: contraction_status = "🎯 極度緊湊"
        elif w1_range <= 3.0 * atr: contraction_status = "✅ 緊湊"
        else: return None

        sctr_val, sctr_hist = round(sctr_map.get(ticker, 0), 1), round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 65: return None

        resistance = float(high.iloc[-(b_days+2):-2].max())
        dist_to_pivot = (curr_p / resistance - 1) * 100
        status = ""
        if -1.8 <= dist_to_pivot <= 0.3: status = "⚡蓄勢待發"
        elif 0.3 < dist_to_pivot <= 6.0: status = "🔥 剛突破"
        elif 6.0 < dist_to_pivot <= 15.0 and (sctr_val > 90 or sctr_val > sctr_hist): status = "🚀 強勢續航"
        else: return None

        if b_only and status != "🔥 剛突破": return None
        if not (has_quiet_point or is_contracting): return None

        stop_loss = curr_p - (1.5 * atr)
        target_price = curr_p + (3.0 * (curr_p - stop_loss))
        return [ticker, round(curr_p, 2), round((1-curr_p/high52)*100, 2), sctr_val, contraction_status, 
                round(float(vol.iloc[-1])/vol_ma20, 2), status, get_sector_cached(ticker), 
                round(resistance, 2), round(stop_loss, 2), round(target_price, 2)]
    except Exception: return None

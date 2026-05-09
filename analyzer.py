# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import time
from data_loader import get_sector_cached

# 🌟 建立全局快取變數，用於儲存批量下載的 K 線，徹底迴避 Rate Limit[cite: 3]
_GLOBAL_BULK_KLINE_CACHE = None

def calculate_sctr_ranks(tickers, lookback=20):
    """
    計算當前與 lookback 天前的 SCTR，用來衡量動能是否持續攀升[cite: 3]
    """
    global _GLOBAL_BULK_KLINE_CACHE
    try:
        # 🌟 透過 Bulk Download 一次性抓取所有股票資料，避免被 Yahoo Finance 暫時封鎖[cite: 3]
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        _GLOBAL_BULK_KLINE_CACHE = raw_data
        
        data = raw_data['Close'] if 'Close' in raw_data else raw_data

        sctr_current = []
        sctr_historical = []

        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                # 嚴格檢查：需要滿足 200日均線 + lookback[cite: 3]
                if len(series) < 200 + lookback: continue

                # 輔助計算函數 (SEPA 核心邏輯)[cite: 3]
                def get_sctr_raw(sub_series):
                    sma200, sma50 = sub_series.rolling(200).mean().iloc[-1], sub_series.rolling(50).mean().iloc[-1]
                    dist_200, dist_50 = (sub_series.iloc[-1]/sma200-1)*100, (sub_series.iloc[-1]/sma50-1)*100
                    roc125, roc20 = (sub_series.iloc[-1]/sub_series.iloc[-125]-1)*100, (sub_series.iloc[-1]/sub_series.iloc[-20]-1)*100
                    rsi = ta.rsi(sub_series, length=14).iloc[-1]
                    return (dist_200*0.3 + roc125*0.3) + (dist_50*0.15 + roc20*0.15) + (rsi*0.1)

                # 計算最新與歷史的原始分數[cite: 3]
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


def check_vcp_advanced(ticker, sctr_map, sctr_hist_map, b_only, b_days):
    """
    優化版 VCP 偵測：同步保留蓄勢待發與剛突破標的
    """
    global _GLOBAL_BULK_KLINE_CACHE
    try:
        # ------------------ 數據檢索優化 ------------------
        df = None
        from_cache = False
        
        if _GLOBAL_BULK_KLINE_CACHE is not None and not _GLOBAL_BULK_KLINE_CACHE.empty:
            if isinstance(_GLOBAL_BULK_KLINE_CACHE.columns, pd.MultiIndex):
                if ticker in _GLOBAL_BULK_KLINE_CACHE.columns.get_level_values(1):
                    df = _GLOBAL_BULK_KLINE_CACHE.xs(ticker, level=1, axis=1).dropna(how='all')
                    from_cache = True
            else:
                df = _GLOBAL_BULK_KLINE_CACHE.dropna(how='all')
                from_cache = True
        
        if not from_cache or df is None or df.empty:
            time.sleep(0.5) 
            df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        
        if df.empty or len(df) < 200: return None

        # ---------- 指標計算 ----------
        close = df['Close']
        high, low, vol = df['High'], df['Low'], df['Volume']
        curr_p = float(close.iloc[-1])

        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())

        # ========== 1. 趨勢模板過濾[cite: 3] ==========
        cond = [
            curr_p > sma150 and curr_p > sma200,                      # 中期趨勢向上[cite: 3]
            sma150 > sma200,                                          # 長線多頭排列[cite: 3]
            sma50 > sma150,                                           # 中期多頭排列[cite: 3]
            curr_p > sma50 * 0.98,                                    # 容錯範圍內的均線支撐[cite: 3]
            curr_p >= low52 * 1.25,                                   # 脫離底部區[cite: 3]
            curr_p >= high52 * 0.75                                   # 處於高位震盪[cite: 3]
        ]
        if sum(cond) < 6: return None

        # ========== 2. VUD 成交量枯竭分析[cite: 3] ==========
        vol_ma50 = vol.rolling(50).mean().iloc[-1]
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        
        # 尋找近期（15日內）是否出現過極度縮量（安靜點）[cite: 3]
        has_quiet_point = vol.iloc[-15:].min() < (vol_ma50 * 0.5)

        # ========== 3. 波幅收縮判定[cite: 3] ==========
        def get_v(series): return (series.max() - series.min()) / series.min()
        v1 = get_v(close.iloc[-40:-20]) 
        v3 = get_v(close.iloc[-10:])    
        
        # 核心 VCP 特徵：波幅顯著收縮且近期極為緊湊[cite: 3]
        is_contracting = v1 > v3 and v3 < 0.12 

        # ========== 4. 緊湊度與 ATR 停損[cite: 3] ==========
        atr = ta.atr(high, low, close, length=14).iloc[-1]
        w1_range = float(close.iloc[-5:].max() - close.iloc[-5:].min())
        
        # 緊湊度評級[cite: 3]
        if w1_range <= 1.6 * atr: is_tight = "✅✅ 極緊"
        elif w1_range <= 2.2 * atr: is_tight = "✅ 緊湊"
        else: return None # 波動過大不符合 VCP[cite: 3]

        # ========== 5. SCTR 動能核心[cite: 3] ==========
        sctr_val = sctr_map.get(ticker, 0)
        sctr_hist = sctr_hist_map.get(ticker, 0)
        if sctr_val < 75: return None # 只看最強標的[cite: 3]

        # ========== 6. 突破狀態與保留邏輯[cite: 3, 4] ==========
        resistance = float(high.iloc[-20:-1].max())
        dist_to_pivot = (curr_p / resistance - 1) * 100

        # 分類邏輯：兼顧伏擊與追蹤[cite: 3, 4]
        if -1.5 <= dist_to_pivot <= 0.5:
            status = "⚡蓄勢待發(即將爆發)"
        elif 0.5 < dist_to_pivot <= 6.0:
            status = "🔥 剛突破(仍具3R空間)"
        elif 6.0 < dist_to_pivot <= 12.0 and sctr_val > sctr_hist:
            status = "🚀 強勢續航(動能領先)"
        else:
            return None

        # 只要有一項 VCP 特徵（縮量或收縮）即可[cite: 3]
        if not (has_quiet_point or is_contracting): return None

        # ========== 7. 風險報酬與輸出 ==========
        stop_loss = curr_p - (1.5 * atr)
        target_3r = curr_p + (3.0 * (curr_p - stop_loss))

        vol_ratio = round(float(vol.iloc[-1]) / vol_ma20, 2)
        sector = get_sector_cached(ticker)

        return [
            ticker, round(curr_p, 2), round((1 - curr_p/high52)*100, 2), 
            round(sctr_val, 1), is_tight, vol_ratio, status, sector,
            round(resistance, 2), round(stop_loss, 2), round(target_3r, 2)
        ]

    except Exception:
        return None

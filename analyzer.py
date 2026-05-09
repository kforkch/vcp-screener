# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import time
from data_loader import get_sector_cached

# 🌟 建立全局快取變數，用於儲存批量下載的 K 線，徹底迴避 Rate Limit
_GLOBAL_BULK_KLINE_CACHE = None

def calculate_sctr_ranks(tickers, lookback=20):
    """
    計算當前與 lookback 天前的 SCTR，用來衡量動能是否持續攀升
    """
    global _GLOBAL_BULK_KLINE_CACHE
    try:
        # 🌟 透過 Bulk Download 一次性抓取所有股票資料
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        _GLOBAL_BULK_KLINE_CACHE = raw_data
        
        data = raw_data['Close'] if 'Close' in raw_data else raw_data

        sctr_current = []
        sctr_historical = []

        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                # 嚴格檢查：需要滿足 200日均線 + lookback
                if len(series) < 200 + lookback: continue

                # 輔助計算函數 (核心邏輯 100% 保留)[cite: 3]
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
    global _GLOBAL_BULK_KLINE_CACHE
    try:
        # ------------------ 🌟 數據提取邏輯 (維持 0 網路請求)[cite: 3] ------------------
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
        
        if df.empty or len(df) < 200:
            return None

        close = df['Close']
        high, low, vol = df['High'], df['Low'], df['Volume']
        curr_p = float(close.iloc[-1])

        # ========== 1. 趨勢模板 (Minervini SEPA 標準)[cite: 3] ==========
        sma50  = ta.sma(close, 50).iloc[-1]
        sma150 = ta.sma(close, 150).iloc[-1]
        sma200 = ta.sma(close, 200).iloc[-1]
        low52  = float(close.min())
        high52 = float(close.max())

        cond = [
            curr_p > sma150 and curr_p > sma200,                      # 中期趨勢向上[cite: 3]
            sma150 > sma200,                                          # 長線多頭排列[cite: 3]
            sma50 > sma150,                                           # 中長線排列[cite: 3]
            curr_p > sma50,                                           # 股價位於 50 日均線上[cite: 3]
            curr_p >= low52 * 1.25,                                   # 脫離底部 25%[cite: 3]
            curr_p >= high52 * 0.75                                   # 位於高位 25% 內[cite: 3]
        ]
        if sum(cond) < 6: return None

        # ========== 2. 成交量極限枯竭偵測 (VUD)[cite: 3] ==========
        vol_ma50 = vol.rolling(50).mean().iloc[-1]
        recent_vol_5d = vol.iloc[-5:].mean()
        # 允許正在突破時量能放大，但蓄勢期必須有過縮量[cite: 3]
        has_vud_history = (vol.iloc[-15:-1].min() < vol_ma50 * 0.5) 

        if not has_vud_history: return None

        # ========== 3. VCP 波動收縮判定[cite: 3] ==========
        def get_v(series): return (series.max() - series.min()) / series.min()
        v1 = get_v(close.iloc[-40:-20]) 
        v2 = get_v(close.iloc[-20:-10]) 
        v3 = get_v(close.iloc[-10:])    
        
        is_contracting = v1 > v3 and v3 < 0.10 # 確保整體波幅在收縮且近期小於 10%[cite: 3]

        # ========== 4. 緊湊度與 ATR[cite: 3] ==========
        atr = ta.atr(high, low, close, length=14).iloc[-1]
        w1_range = close.iloc[-5:].max() - close.iloc[-5:].min()
        is_tight = w1_range <= 2.2 * atr

        if not is_tight: return None

        # ========== 5. SCTR 動能要求[cite: 3] ==========
        sctr_val = sctr_map.get(ticker, 0)
        sctr_hist = sctr_hist_map.get(ticker, 0)
        if sctr_val < 75: return None # SCTR 必須處於高位[cite: 3]

        # ========== 6. 狀態判定：保留蓄勢與剛突破 ==========
        # 尋找過去 20 天的最高價作為阻力位 (Pivot)[cite: 3]
        resistance = float(high.iloc[-20:-1].max())
        dist_to_pivot = (curr_p / resistance - 1) * 100

        # 分類邏輯：
        # 1. 預發射：股價在阻力下方 1.5% 內蓄勢[cite: 3]
        if -1.5 <= dist_to_pivot <= 0.5:
            status = "⚡預發射(即將爆發)"
        # 2. 剛突破：突破阻力但在 5% 漲幅內，仍有 2-3R 空間[cite: 3]
        elif 0.5 < dist_to_pivot <= 5.0:
            status = "🔥 剛突破(2-3R空間)"
        # 3. 強勢續航：突破超過 5%，但在 SCTR 加速中[cite: 3]
        elif 5.0 < dist_to_pivot <= 10.0 and sctr_val > sctr_hist:
            status = "🚀 強勢續航"
        else:
            return None

        # ========== 7. 風險報酬計算[cite: 3] ==========
        stop_loss = curr_p - (1.5 * atr)
        target_price = curr_p + (3.0 * (curr_p - stop_loss)) # 預設 3R 目標[cite: 3]

        vol_ratio = round(float(vol.iloc[-1]) / vol_ma50, 2)
        sector = get_sector_cached(ticker)

        return [
            ticker, round(curr_p, 2), round((1-curr_p/high52)*100,2), round(sctr_val, 1),
            "✅ 極緊" if w1_range <= 1.6*atr else "✅ 緊湊",
            vol_ratio, status, sector,
            round(resistance, 2), round(stop_loss, 2), round(target_price, 2)
        ]

    except Exception:
        return None

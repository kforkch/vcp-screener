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
        # 🌟 透過 Bulk Download 一次性抓取所有股票資料，並快取至記憶體中[cite: 3]
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
    """
    優化版 VCP 偵測：強化「強勢續航」判定，並修正阻力位參考點
    """
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
        
        if df.empty or len(df) < 200: return None

        close = df['Close']
        high, low, vol = df['High'], df['Low'], df['Volume']
        curr_p = float(close.iloc[-1])

        # ---------- 均線與趨勢模板[cite: 3] ----------
        sma50  = ta.sma(close, 50).iloc[-1]
        sma150 = ta.sma(close, 150).iloc[-1]
        sma200 = ta.sma(close, 200).iloc[-1]
        low52  = float(close.min())
        high52 = float(close.max())

        # ========== 1. 趨勢模板 (SEPA 核心標準)[cite: 3] ==========
        cond = [
            curr_p > sma150 and curr_p > sma200,                      
            sma150 > sma200,                                          
            sma50 > sma150 or (sma50 > sma200 and sma50 > sma150*0.98),  
            curr_p > sma50 * 0.98,                                    
            curr_p >= low52 * 1.25,                                   # 脫離底部 25%[cite: 3]
            curr_p >= high52 * 0.75                                   # 回調 25% 以內[cite: 3]
        ]
        if sum(cond) < 6: return None

        # ========== 2. 成交量萎縮 (VUD 深度解析，20日回溯)[cite: 3] ==========
        vol_ma50 = vol.rolling(50).mean().iloc[-1]
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        
        # 曾經出現過安靜點，確保籌碼乾淨[cite: 3]
        has_quiet_point = vol.iloc[-20:-1].min() < (vol_ma50 * 0.55)

        # ========== 3. VCP 波動收縮 (波幅遞減邏輯)[cite: 3] ==========
        def get_v(series): return (series.max() - series.min()) / series.min()
        v1 = get_v(close.iloc[-40:-20]) 
        v3 = get_v(close.iloc[-10:])    
        is_contracting = v1 > v3 and v3 < 0.12 # 確保近期波幅收窄[cite: 3]

        # ========== 4. ATR 與緊密度[cite: 3] ==========
        atr = ta.atr(high, low, close, length=14).iloc[-1]
        w1_range = close.iloc[-5:].max() - close.iloc[-5:].min()
        
        # 強勢續航中波幅會略大，放寬至 2.3*ATR[cite: 3]
        if w1_range <= 2.3 * atr:
            is_tight = "✅ 緊湊" if w1_range > 1.6 * atr else "✅✅ 極緊"
        else:
            return None

        # ========== 5. SCTR 動能核心[cite: 3] ==========
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_hist = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 75: return None # SCTR 必須在領先群[cite: 3]

        # ========== 6. 狀態判定 (修正阻力位與續航邏輯) ==========
        # 阻力位回溯，避開爆發當日的影響[cite: 3]
        resistance = float(high.iloc[-22:-2].max())
        dist_to_pivot = (curr_p / resistance - 1) * 100
        
        # 短期均線支撐檢查[cite: 3]
        sma20 = ta.sma(close, 20).iloc[-1]
        is_on_trend = curr_p > sma20 * 0.99

        if -1.5 <= dist_to_pivot <= 0.2:
            status = "⚡蓄勢待發(即將爆發)"
        elif 0.2 < dist_to_pivot <= 6.0:
            status = "🔥 剛突破(仍具3R空間)"
        # 🚀 強勢續航：漲幅 6-15%，且 SCTR 維持超強 (>90) 或正在加速，且未破 20日線
        elif 6.0 < dist_to_pivot <= 15.0 and (sctr_val > 90 or sctr_val > sctr_hist) and is_on_trend:
            status = "🚀 強勢續航(動能領先)"
        else:
            return None

        # 核心 VCP 過濾：必須有縮量歷史或正在收縮[cite: 3]
        if not (has_quiet_point or is_contracting): return None

        # ========== 7. 風險報酬[cite: 3] ==========
        stop_loss = curr_p - (1.5 * atr)
        target_price = curr_p + (3.0 * (curr_p - stop_loss))

        vol_ratio = round(float(vol.iloc[-1]) / vol_ma20, 2)
        sector = get_sector_cached(ticker)

        return [
            ticker, round(curr_p, 2), round((1-curr_p/high52)*100, 2), sctr_val, is_tight,
            vol_ratio, status, sector,
            round(resistance, 2), round(stop_loss, 2), round(target_price, 2)
        ]

    except Exception:
        return None

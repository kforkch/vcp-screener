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
        # 🌟 透過 Bulk Download 一次性抓取所有股票資料，避免頻繁請求
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        _GLOBAL_BULK_KLINE_CACHE = raw_data
        
        data = raw_data['Close'] if 'Close' in raw_data else raw_data

        sctr_current = []
        sctr_historical = []

        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                # 嚴格檢查：需要滿足 200 日均線 + lookback
                if len(series) < 200 + lookback: continue

                # 輔助計算函數 (核心邏輯：SEPA 趨勢排名)
                def get_sctr_raw(sub_series):
                    sma200, sma50 = sub_series.rolling(200).mean().iloc[-1], sub_series.rolling(50).mean().iloc[-1]
                    dist_200, dist_50 = (sub_series.iloc[-1]/sma200-1)*100, (sub_series.iloc[-1]/sma50-1)*100
                    roc125, roc20 = (sub_series.iloc[-1]/sub_series.iloc[-125]-1)*100, (sub_series.iloc[-1]/sub_series.iloc[-20]-1)*100
                    rsi = ta.rsi(sub_series, length=14).iloc[-1]
                    return (dist_200*0.3 + roc125*0.3) + (dist_50*0.15 + roc20*0.15) + (rsi*0.1)

                # 計算最新與歷史的原始分數
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
    優化版 VCP 偵測：針對 NVDA 等超強動能股優化過濾條件
    """
    global _GLOBAL_BULK_KLINE_CACHE
    try:
        # ------------------ 🌟 數據提取邏輯 (RAM 快取分片) ------------------
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

        sma50  = ta.sma(close, 50).iloc[-1]
        sma150 = ta.sma(close, 150).iloc[-1]
        sma200 = ta.sma(close, 200).iloc[-1]
        low52  = float(close.min())
        high52 = float(close.max())

        # ========== 1. 趨勢模板 (SEPA 核心標準，適度放寬) ==========
        cond = [
            curr_p > sma150 and curr_p > sma200,                      
            sma150 > sma200,                                          
            sma50 > sma150 or (sma50 > sma200 and sma50 > sma150*0.98),
            curr_p > sma50 * 0.98,                                    
            curr_p >= low52 * 1.25,                                   # 脫離底部 25%
            curr_p >= high52 * 0.70                                   # 回調放寬至 30% 以容納大波動領頭羊
        ]
        if sum(cond) < 6: return None

        # ========== 2. 成交量枯竭 (針對 NVDA 權值股微調) ==========
        vol_ma50 = vol.rolling(50).mean().iloc[-1]
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        # 安靜點回溯 20 日，比例放寬至 60%，以應對活躍標的
        has_quiet_point = vol.iloc[-20:-1].min() < (vol_ma50 * 0.60)

        # ========== 3. VCP 波動收縮判定 ==========
        def get_v(series): return (series.max() - series.min()) / series.min()
        v1 = get_v(close.iloc[-40:-20]) 
        v3 = get_v(close.iloc[-10:])    
        # 核心收縮特徵：近期波幅 < 12% 且整體未擴張
        is_contracting = v3 < 0.12 and v3 <= v1 * 1.1

        # ========== 4. 緊湊度與 ATR ==========
        atr = ta.atr(high, low, close, length=14).iloc[-1]
        w1_range = close.iloc[-5:].max() - close.iloc[-5:].min()
        is_tight = w1_range <= 2.3 * atr # 適度容納強勢續航中的震盪

        if not is_tight: return None

        # ========== 5. SCTR 動能核心 ==========
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_hist = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 70: return None # 放寬至 70，避免在板塊輪動中誤刪龍頭

        # ========== 6. 狀態判定 ==========
        # 阻力位取爆發前 b_days 區間 (動態應用 UI 參數)
        resistance = float(high.iloc[-(b_days+2):-2].max())
        dist_to_pivot = (curr_p / resistance - 1) * 100
        
        sma20 = ta.sma(close, 20).iloc[-1]
        is_on_trend = curr_p > sma20 * 0.99

        if -1.5 <= dist_to_pivot <= 0.2:
            status = "⚡蓄勢待發(即將爆發)"
        elif 0.2 < dist_to_pivot <= 6.0:
            status = "🔥 剛突破(仍具3R空間)"
        # 🚀 強勢續航：針對 NVDA 這種超級龍頭，只要 SCTR > 90 或持續攀升，且股價貼合 20日線
        elif 6.0 < dist_to_pivot <= 15.0 and (sctr_val > 90 or sctr_val > sctr_hist) and is_on_trend:
            status = "🚀 強勢續航(動能領先)"
        else:
            return None

        # 核心 VCP 要求：必須有過沈澱或波幅收縮
        if not (has_quiet_point or is_contracting): return None

        # 如果開啟「僅看突破」過濾器，排除其他狀態
        if b_only and status != "🔥 剛突破(仍具3R空間)":
            return None

        # ========== 7. 風險報酬與輸出 ==========
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

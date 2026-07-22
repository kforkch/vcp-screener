# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import threading
from data_loader import get_sector_cached

# 🌟 機構級線程安全快取機制
_GLOBAL_BULK_KLINE_CACHE = None
_CACHE_LOCK = threading.Lock()

def calculate_sctr_ranks(tickers, lookback=20):
    """
    計算當前與 lookback 天前的 SCTR，用來衡量動態動能攀升
    並建立全局 Safe Bulk K-Line 快取
    """
    global _GLOBAL_BULK_KLINE_CACHE
    try:
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        
        with _CACHE_LOCK:
            _GLOBAL_BULK_KLINE_CACHE = raw_data
        
        if raw_data.empty:
            return {}, {}

        # 安全處理 MultiIndex 結構 (yfinance 版本相容性增強)
        if isinstance(raw_data.columns, pd.MultiIndex):
            if 'Close' in raw_data.columns.get_level_values(0):
                data = raw_data['Close']
            elif 'Close' in raw_data.columns.get_level_values(1):
                data = raw_data.xs('Close', axis=1, level=1)
            else:
                data = raw_data
        else:
            data = raw_data['Close'] if 'Close' in raw_data else raw_data

        sctr_current = []
        sctr_historical = []

        for ticker in tickers:
            try:
                if isinstance(data, pd.DataFrame):
                    if ticker not in data.columns:
                        continue
                    series = data[ticker].dropna()
                else:
                    series = data.dropna()

                if len(series) < 200 + lookback: 
                    continue

                # SEPA 趨勢排名核心算法
                def get_sctr_raw(sub_series):
                    sma200 = sub_series.rolling(200).mean().iloc[-1]
                    sma50 = sub_series.rolling(50).mean().iloc[-1]
                    
                    if sma200 == 0 or sma50 == 0 or pd.isna(sma200) or pd.isna(sma50):
                        return 0.0

                    dist_200 = (sub_series.iloc[-1] / sma200 - 1) * 100
                    dist_50 = (sub_series.iloc[-1] / sma50 - 1) * 100

                    p_125 = sub_series.iloc[-125] if len(sub_series) >= 125 else sub_series.iloc[0]
                    p_20 = sub_series.iloc[-20] if len(sub_series) >= 20 else sub_series.iloc[0]

                    roc125 = (sub_series.iloc[-1] / p_125 - 1) * 100 if p_125 != 0 else 0
                    roc20 = (sub_series.iloc[-1] / p_20 - 1) * 100 if p_20 != 0 else 0

                    rsi_series = ta.rsi(sub_series, length=14)
                    rsi = rsi_series.iloc[-1] if rsi_series is not None and not rsi_series.empty else 50.0

                    return (dist_200 * 0.3 + roc125 * 0.3) + (dist_50 * 0.15 + roc20 * 0.15) + (rsi * 0.1)

                raw_curr = get_sctr_raw(series)
                raw_hist = get_sctr_raw(series.iloc[:-lookback])

                sctr_current.append({'ticker': ticker, 'raw': raw_curr})
                sctr_historical.append({'ticker': ticker, 'raw': raw_hist})
            except Exception:
                continue

        if not sctr_current: 
            return {}, {}

        df_curr = pd.DataFrame(sctr_current)
        df_curr['rank'] = df_curr['raw'].rank(pct=True) * 99.9
        dict_curr = df_curr.set_index('ticker')['rank'].to_dict()

        df_hist = pd.DataFrame(sctr_historical)
        df_hist['rank'] = df_hist['raw'].rank(pct=True) * 99.9
        dict_hist = df_hist.set_index('ticker')['rank'].to_dict()

        return dict_curr, dict_hist
    except Exception:
        return {}, {}


def check_pocket_pivot(df):
    """
    機構級口袋買點 (Pocket Pivot) 檢測：
    當日陽線成交量 > 過去 10 個交易日內的最大陰線成交量
    """
    if len(df) < 11:
        return False
    
    close = df['Close'].values
    open_p = df['Open'].values
    vol = df['Volume'].values

    # 今日是否為陽線
    is_up_day = close[-1] > open_p[-1]
    if not is_up_day:
        return False

    # 找出過去 10 日 (不含今日) 的最大陰線成交量
    down_day_volumes = [
        vol[-i] for i in range(2, 12) 
        if close[-i] < open_p[-i]
    ]
    
    max_down_vol = max(down_day_volumes) if down_day_volumes else 0
    return vol[-1] > max_down_vol


def detect_vcp_waves_and_higher_lows(df_sub, p_len=3):
    """
    動態波浪與樞紐分析引擎 (復刻 Pine Script Pivots 與嚴格底底高邏輯)
    """
    highs = df_sub['High'].values
    lows = df_sub['Low'].values
    n = len(df_sub)
    
    pivot_highs = [] # (index, price)
    pivot_lows = []  # (index, price)
    
    # 搜尋區域 Pivot High / Pivot Low
    for i in range(p_len, n - p_len):
        if highs[i] == max(highs[i - p_len : i + p_len + 1]):
            pivot_highs.append((i, highs[i]))
        if lows[i] == min(lows[i - p_len : i + p_len + 1]):
            pivot_lows.append((i, lows[i]))
            
    if len(pivot_lows) < 2:
        return False, False, df_sub['High'].iloc[-20:].max(), 0.0

    # 1. 驗證嚴格「底底高 (Higher Lows)」(取最新 3 個低點)
    recent_low_prices = [p[1] for p in pivot_lows[-3:]]
    is_higher_lows = True
    for k in range(len(recent_low_prices) - 1):
        if recent_low_prices[k+1] <= recent_low_prices[k]:
            is_higher_lows = False
            break

    # 2. 驗證波動收縮 (Contraction Amplitudes T1 > T2)
    contractions = []
    for ph_idx, ph_val in reversed(pivot_highs):
        matching_lows = [pl for pl in pivot_lows if pl[0] > ph_idx]
        if matching_lows:
            pl_idx, pl_val = matching_lows[0] # 取得 High 隨後的第一個 Low
            if ph_val > pl_val:
                contractions.append((ph_val - pl_val) / ph_val)

    is_contracting = False
    if len(contractions) >= 2:
        # 最新一次收縮幅度必須小於前一次，且最新收縮幅度 <= 15%
        if contractions[0] < contractions[1] and contractions[0] <= 0.15:
            is_contracting = True
    elif len(contractions) == 1 and contractions[0] <= 0.12:
        is_contracting = True

    # 最新樞紐阻力位 (Pivot Price)
    pivot_price = pivot_highs[-1][1] if pivot_highs else float(df_sub['High'].iloc[-10:].max())

    return is_higher_lows, is_contracting, pivot_price, (contractions[0] if contractions else 0.0)


def check_vcp_advanced(ticker, sctr_map, sctr_hist_map, b_only, b_days):
    """
    機構級 VCP 偵測核心：整合 SEPA 趨勢模板、機構流動性門檻、口袋買點與嚴格 VCP 波浪
    """
    global _GLOBAL_BULK_KLINE_CACHE
    try:
        df = None
        from_cache = False
        
        with _CACHE_LOCK:
            if _GLOBAL_BULK_KLINE_CACHE is not None and not _GLOBAL_BULK_KLINE_CACHE.empty:
                try:
                    if isinstance(_GLOBAL_BULK_KLINE_CACHE.columns, pd.MultiIndex):
                        if ticker in _GLOBAL_BULK_KLINE_CACHE.columns.get_level_values(1):
                            df = _GLOBAL_BULK_KLINE_CACHE.xs(ticker, level=1, axis=1)
                            from_cache = True
                        elif ticker in _GLOBAL_BULK_KLINE_CACHE.columns.get_level_values(0):
                            df = _GLOBAL_BULK_KLINE_CACHE.xs(ticker, level=0, axis=1)
                            from_cache = True
                    else:
                        df = _GLOBAL_BULK_KLINE_CACHE
                        from_cache = True
                except Exception:
                    from_cache = False
        
        if not from_cache or df is None or df.empty:
            df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        
        df = df.dropna(subset=['Open', 'Close', 'High', 'Low', 'Volume'])
        if df.empty or len(df) < 200 or df['Volume'].iloc[-1] == 0: 
            return None

        # ========== 0. 機構級流動性過濾 (ADV20 流動性門檻) ==========
        curr_p = float(df['Close'].iloc[-1])
        adv20_turnover = (df['Volume'] * df['Close']).tail(20).mean()
        # 港股/A股 至少 1000萬，美股至少 200萬美元日均成交額，避開無流動性莊股
        min_adv = 10000000 if (".HK" in ticker or ".SS" in ticker or ".SZ" in ticker) else 2000000
        if adv20_turnover < min_adv:
            return None

        # 指標計算
        close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']
        sma50_series = ta.sma(close, 50)
        sma150_series = ta.sma(close, 150)
        sma200_series = ta.sma(close, 200)

        if sma50_series is None or sma150_series is None or sma200_series is None:
            return None

        sma50 = sma50_series.iloc[-1]
        sma150 = sma150_series.iloc[-1]
        sma200 = sma200_series.iloc[-1]
        sma200_20d_ago = sma200_series.iloc[-20] if len(sma200_series) >= 20 else sma200

        low52, high52 = float(close.tail(252).min()), float(close.tail(252).max())

        # ========== 1. 嚴格 SEPA 趨勢模板 (Trend Template) ==========
        cond = [
            curr_p > sma150 and curr_p > sma200,                        # 1. 價格高於 150/200 日線
            sma150 > sma200,                                            # 2. 150日線高於 200日線
            sma200 > sma200_20d_ago,                                    # 3. 200日線呈現上揚趨勢
            sma50 > sma150 or (sma50 > sma200 and sma50 > sma150*0.98), # 4. 50日線多頭排列
            curr_p > sma50 * 0.98,                                      # 5. 價格站穩 50日線
            curr_p >= low52 * 1.25,                                     # 6. 較 52 週低點上漲至少 25%
            curr_p >= high52 * 0.70                                     # 7. 距離 52 週高點 30% 以內
        ]
        if sum(cond) < 7: 
            return None

        # ========== 2. 嚴格 VCP 成交量枯竭 (VDU) + 口袋買點 (Pocket Pivot) ==========
        vol_ma50 = vol.rolling(50).mean().iloc[-1]
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        
        has_quiet_point = (vol.iloc[-max(10, b_days):-1].min() < (vol_ma50 * 0.55)) or (vol.iloc[-1] < vol_ma20 * 0.50)
        has_pocket_pivot = check_pocket_pivot(df)

        # 必須滿足 VDU 成交量極度乾涸，或是觸發口袋買點
        if not (has_quiet_point or has_pocket_pivot):
            return None

        # ========== 3. 動態波浪與底底高 (Higher Lows) 驗證 ==========
        df_recent = df.tail(63) 
        is_higher_lows, is_contracting, dynamic_pivot, last_amplitude = detect_vcp_waves_and_higher_lows(df_recent, p_len=3)

        if not (is_higher_lows and is_contracting):
            return None

        # ========== 4. 緊湊度評級 (ATR 基準) ==========
        atr_series = ta.atr(high, low, close, length=14)
        if atr_series is None or atr_series.empty:
            return None
        atr = atr_series.iloc[-1]
        w1_range = close.iloc[-5:].max() - close.iloc[-5:].min()
        
        if w1_range <= 1.5 * atr:
            contraction_status = "🎯 極度緊湊"
        elif w1_range <= 3.0 * atr:
            contraction_status = "✅ 緊湊"
        else:
            return None

        # ========== 5. SCTR 動能要求 ==========
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_hist = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 65: 
            return None

        # ========== 6. 狀態判定 (Pivot 樞軸點) ==========
        resistance = float(dynamic_pivot)
        dist_to_pivot = (curr_p / resistance - 1) * 100
        sma20 = ta.sma(close, 20).iloc[-1]
        is_on_trend = curr_p > sma20 * 0.99

        status = ""
        if -1.8 <= dist_to_pivot <= 0.3:
            status = "⚡蓄勢待發"
        elif 0.3 < dist_to_pivot <= 6.0:
            status = "🔥 剛突破"
            if has_pocket_pivot:
                status = "🔥 剛突破 (Pocket Pivot)"
        elif 6.0 < dist_to_pivot <= 15.0 and (sctr_val > 90 or sctr_val > sctr_hist) and is_on_trend:
            status = "🚀 強勢續航"
        else:
            return None

        if b_only and "剛突破" not in status: 
            return None

        # ========== 7. 風險報酬 (3R) ==========
        stop_loss = curr_p - (1.5 * atr)
        target_price = curr_p + (3.0 * (curr_p - stop_loss))
        vol_ratio = round(float(vol.iloc[-1]) / vol_ma20, 2) if vol_ma20 > 0 else 1.0
        sector = get_sector_cached(ticker)

        return [
            ticker, round(curr_p, 2), round((1-curr_p/high52)*100, 2), sctr_val, contraction_status,
            vol_ratio, status, sector,
            round(resistance, 2), round(stop_loss, 2), round(target_price, 2)
        ]
    except Exception:
        return None

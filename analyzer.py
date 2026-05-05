# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
# 從 data_loader 匯入行業抓取函式
from data_loader import get_sector_cached

def calculate_sctr_ranks(tickers, lookback=20):
    """
    計算當前與 lookback 天前的 SCTR，用來衡量動能是否持續攀升
    """
    try:
        # 下載 1 年 + lookback 天的數據
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        data = raw_data['Close'] if 'Close' in raw_data else raw_data
        
        sctr_current = []
        sctr_historical = []
        
        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) < 200 + lookback: continue
                
                # 輔助計算函數
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
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        high = df['High'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['High']
        low = df['Low'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Low']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        
        curr_p = float(close.iloc[-1])
        
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        
        # 1. 趨勢模板過濾 (Trend Template)
        cond = [
            curr_p > sma150 and curr_p > sma200, sma150 > sma200, 
            sma50 > sma150 and sma50 > sma200, curr_p > sma50,
            curr_p >= (low52 * 1.25), curr_p >= (high52 * 0.75)
        ]
        if sum(cond) < 6: return None
        
        # 2. VCP 彈性多段波動收縮判斷（推薦版）
        # 改用更多窗口，允許 2~5 段收縮，不強求固定4段
        windows = [
            close.iloc[-75:-50],   # 更早一段
            close.iloc[-60:-40],
            close.iloc[-45:-25],
            close.iloc[-30:-15],
            close.iloc[-20:-5],    # 接近最新但避開最後幾天
            close.iloc[-15:]       # 最近15天
        ]
        
        ranges = []
        for w in windows:
            if len(w) >= 5:  # 至少要有5根K線才計算
                r = (w.max() - w.min()) / w.min()
                ranges.append(r)
            else:
                ranges.append(0.25)
        
        # 移除前面幾個可能不完整的區間，只取有效的 ranges
        valid_ranges = [r for r in ranges if r > 0]
        
        if len(valid_ranges) < 2:
            return None  # 至少要有2段才能判斷收縮
        
        # 計算整體趨勢斜率（越往後應該越小 = 負斜率越好）
        x = np.arange(len(valid_ranges))
        y = np.array(valid_ranges)
        slope, _ = np.polyfit(x, y, 1)
        
        # 【大幅放寬】允許輕微正斜率，只要不是明顯擴張即可
        if slope > 0.025:  
            return None
            
        # 計算 ATR(14)
        atr_series = ta.atr(high, low, close, length=14)
        atr_val = float(atr_series.iloc[-1]) if not atr_series.isna().iloc[-1] else (float(high.iloc[-1]) - float(low.iloc[-1]))
        
        # 最近 15 天 (w1) 的絕對價格震幅空間與百分比
        w1_max = float(w1.max())
        w1_min = float(w1.min())
        w1_abs_range = w1_max - w1_min
        w1_pct = ranges[-1]  # w1 震幅百分比
        
        # 3. 緊湊程度分級邏輯 (Fuzzy Logic Grading)
        if w1_abs_range <= 1.4 * atr_val and w1_pct <= 0.10:
            is_tight = "✅✅ 極緊"
        elif w1_abs_range <= 1.8 * atr_val and w1_pct <= 0.13:
            is_tight = "✅ 緊湊"
        elif w1_abs_range <= 2.0 * atr_val and w1_pct <= 0.15:
            is_tight = "🔸 尚可"
        else:
            # 超過 15% 震幅或 2.0 倍 ATR 則判定不符合收縮標準，直接排除
            return None
            
        # 4. 成交量萎縮檢查 (尋找量能乾枯 VUD)
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        if vol.iloc[-1] > vol_ma20 * 1.1: return None
            
        # 5. SCTR 持續攀升檢查
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_hist = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 80.0 or sctr_val <= sctr_hist: return None
        
        # 6. 突破檢測
        recent_max = float(close.iloc[-(b_days+1):-1].max())
        is_breakout = curr_p > recent_max
        if b_only and not is_breakout: return None
        
        # 狀態轉換
        status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢向上"
        
        # 7. 計算風險報酬
        pivot_point = recent_max
        stop_loss = curr_p - (1.5 * atr_val)
        target_price = curr_p + (3.0 * (curr_p - stop_loss))
        
        dist_high = round((1 - curr_p/high52) * 100, 2)
        vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
        
        sector = get_sector_cached(ticker)
        
        return [
            ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, status, sector,
            round(pivot_point, 2), round(stop_loss, 2), round(target_price, 2)
        ]
    except:
        return None

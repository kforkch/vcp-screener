# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
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
        
        # 1. 趨勢模板過濾
        cond = [
            curr_p > sma150 and curr_p > sma200, sma150 > sma200, 
            sma50 > sma150 and sma50 > sma200, curr_p > sma50,
            curr_p >= (low52 * 1.25), curr_p >= (high52 * 0.75)
        ]
        if sum(cond) < 6: return None
        
        # 2. VCP 三段式收縮辨識 (T1 -> T2 -> T3)
        # T1: 過去 40-60 天前的波動範圍
        t1_series = close.iloc[-60:-40]
        t1_contraction = (t1_series.max() - t1_series.min()) / t1_series.min() if len(t1_series) > 0 else 0.3
        
        # T2: 過去 20-40 天前的波動範圍
        t2_series = close.iloc[-40:-20]
        t2_contraction = (t2_series.max() - t2_series.min()) / t2_series.min() if len(t2_series) > 0 else 0.2
        
        # T3: 過去 5-20 天前的波動範圍
        t3_series = close.iloc[-20:-5]
        t3_contraction = (t3_series.max() - t3_series.min()) / t3_series.min() if len(t3_series) > 0 else 0.1
        
        # 實戰收縮型態確認 (T1 > T2 > T3 且 T3 需夠窄)
        if not (t1_contraction > t2_contraction > t3_contraction and t3_contraction < 0.12):
            return None
            
        # 過去 5 天極窄收縮確認 (安靜點)
        recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
        is_tight = "✅ 緊湊" if recent_range < 0.05 else "❌ 鬆散"

        # 3. 成交量萎縮檢查
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        if vol.iloc[-1] > vol_ma20 * 1.1: return None 
            
        # 4. SCTR 持續攀升檢查
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_hist = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 80.0 or sctr_val <= sctr_hist: return None
        
        # 5. 突破檢測
        recent_max = float(close.iloc[-(b_days+1):-1].max())
        is_breakout = curr_p > recent_max
        if b_only and not is_breakout: return None
        
        # 狀態轉換邏輯：若突破則升級為 20D突破，否則為強勢向上
        status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢向上"
        
        # 6. 計算風險報酬
        atr_series = ta.atr(high, low, close, length=14)
        atr_val = float(atr_series.iloc[-1]) if not atr_series.isna().iloc[-1] else (float(high.iloc[-1]) - float(low.iloc[-1]))
        
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

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
    """
    實戰進階 VCP 掃描器
    - 採用滾動區間定位法 (Rolling Local Extremes) 來動態找出近期的波段收縮結構。
    - 結合 ATR 動態波動門檻，防止牛熊市參數失效，精確捕捉 VUD (成交量乾涸) 的安靜點。
    """
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
        
        # 1. 經典馬克趨勢模板過濾 (Trend Template)
        cond = [
            curr_p > sma150 and curr_p > sma200, sma150 > sma200, 
            sma50 > sma150 and sma50 > sma200, curr_p > sma50,
            curr_p >= (low52 * 1.25), curr_p >= (high52 * 0.75)
        ]
        if sum(cond) < 6: return None
        
        # 2. ATR 動態計算與波動基準
        atr_series = ta.atr(high, low, close, length=14)
        atr_val = float(atr_series.iloc[-1]) if not atr_series.isna().iloc[-1] else (float(high.iloc[-1]) - float(low.iloc[-1]))
        atr_pct = atr_val / curr_p  # ATR 佔股價百分比 (最新波動度)
        
        # 3. 滾動區間波動收縮演算法 (Rolling Window Extremes)
        # 用滾動最大與最小值，尋找過去 60 天內真實存在的波段高低落差 (不採用死板的固定區間切割)
        roll_high = high.rolling(window=15, min_periods=1)
        roll_low = low.rolling(window=15, min_periods=1)
        
        # 取出近期不同延遲窗口的收縮特徵
        t1_high = float(roll_high.max().iloc[-45])
        t1_low  = float(roll_low.min().iloc[-45])
        t1_contraction = (t1_high - t1_low) / t1_low if t1_low > 0 else 0.3
        
        t2_high = float(roll_high.max().iloc[-20])
        t2_low  = float(roll_low.min().iloc[-20])
        t2_contraction = (t2_high - t2_low) / t2_low if t2_low > 0 else 0.2
        
        t3_high = float(roll_high.max().iloc[-5])
        t3_low  = float(roll_low.min().iloc[-5])
        t3_contraction = (t3_high - t3_low) / t3_low if t3_low > 0 else 0.1
        
        # VCP 收縮演算法核心：
        # 1. 波動幅度必須遞減 (T1 > T2 > T3)
        # 2. 最終 T3 的收縮幅度必須「動態小於」 1.5 倍的 ATR% 波動門檻 (或極值 8% 限制，取較小者)，以確保波動極度收緊
        dynamic_t3_threshold = min(0.08, atr_pct * 1.5)
        
        if not (t1_contraction > t2_contraction > t3_contraction and t3_contraction < dynamic_t3_threshold):
            return None
            
        # 過去 5 天極窄收縮確認 (尋找最緊湊的 Pivot Area)
        recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
        is_tight = "✅ 緊湊" if recent_range < dynamic_t3_threshold else "❌ 鬆散"

        # 4. 成交量乾涸度檢查 (馬克 VUD 邏輯：成交量必須萎縮至 20 日均量的 80% 以下)
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        if vol.iloc[-1] > vol_ma20 * 0.8: return None 
            
        # 5. SCTR 持續攀升檢查
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_hist = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 80.0 or sctr_val <= sctr_hist: return None
        
        # 6. 突破檢測
        recent_max = float(close.iloc[-(b_days+1):-1].max())
        is_breakout = curr_p > recent_max
        if b_only and not is_breakout: return None
        
        # 狀態轉換邏輯
        status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢向上"
        
        # 7. 風險報酬計算 (以 Pivot Point 和動態 ATR 為停損)
        pivot_point = recent_max  
        stop_loss = curr_p - (1.5 * atr_val)  
        target_price = curr_p + (3.0 * (curr_p - stop_loss)) 
        
        dist_high = round((1 - curr_p/high52) * 100, 2)
        vol_ratio = round(float(vol.iloc[-1]) / vol_ma20, 2)
        
        sector = get_sector_cached(ticker)
        
        return [
            ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, status, sector,
            round(pivot_point, 2), round(stop_loss, 2), round(target_price, 2)
        ]
    except Exception as e:
        # 實戰不因單檔股票錯誤而中斷掃描
        return None

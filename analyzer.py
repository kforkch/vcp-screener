# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
# 從 data_loader 匯入行業抓取函式
from data_loader import get_sector_cached

def calculate_sctr_ranks(tickers):
    try:
        # 使用多執行緒下載通常更快，但這裡維持穩定性
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        # 處理單一或多個 tickers 的結構差異
        data = raw_data['Close'] if isinstance(raw_data, pd.DataFrame) and 'Close' in raw_data else raw_data
        
        sctr_data = []
        for ticker in tickers:
            try:
                # 確保 series 為 Series 物件
                series = data[ticker] if isinstance(data, pd.DataFrame) else data
                series = series.dropna()
                if len(series) < 200: continue
                
                sma200, sma50 = series.rolling(200).mean().iloc[-1], series.rolling(50).mean().iloc[-1]
                # 調整 SCTR 權重，確保動能指標具有參考價值
                dist_200, dist_50 = (series.iloc[-1]/sma200-1)*100, (series.iloc[-1]/sma50-1)*100
                roc125, roc20 = (series.iloc[-1]/series.iloc[-125]-1)*100, (series.iloc[-1]/series.iloc[-20]-1)*100
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
        
        # 統一處理數據格式 (確保不會因為多層索引報錯)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        close, high, low, vol = df['Close'], df['High'], df['Low'], df['Volume']
        curr_p = float(close.iloc[-1])
        
        # 趨勢模板嚴格檢查
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        
        # 嚴格執行 8 大條件中的核心趨勢檢查
        cond = [
            curr_p > sma150 and curr_p > sma200, 
            sma150 > sma200, 
            sma50 > sma150 and sma50 > sma200, 
            curr_p > sma50,
            curr_p >= (low52 * 1.25), 
            curr_p >= (high52 * 0.75)
        ]
        
        if sum(cond) < 6: return None
        
        # 波動收縮邏輯優化：加入成交量萎縮檢測 (VUD)
        recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
        prev_range = (close.iloc[-25:-5].max() - close.iloc[-25:-5].min()) / close.iloc[-25:-5].min()
        
        # 判斷是否為緊湊型態 (VCP)
        is_tight = (recent_range < (prev_range * 0.7))
        
        # 成交量萎縮：確保近期量能小於 20 日平均，這是「安靜點」的關鍵
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        vol_is_low = vol.iloc[-1] < vol_ma20 * 1.2
        
        if not is_tight or not vol_is_low: return None
        
        recent_max = float(close.iloc[-(b_days+1):-1].max())
        is_breakout = curr_p > recent_max
        if b_only and not is_breakout: return None
        
        # 風險控管：ATR 停損
        atr_series = ta.atr(high, low, close, length=14)
        atr_val = float(atr_series.iloc[-1]) if not atr_series.isna().iloc[-1] else (float(high.iloc[-1]) - float(low.iloc[-1]))
        
        pivot_point = recent_max
        stop_loss = curr_p - (1.5 * atr_val)
        target_price = curr_p + (3.0 * (curr_p - stop_loss))
        
        dist_high = round((1 - curr_p/high52) * 100, 2)
        vol_ratio = round(float(vol.iloc[-1]) / vol_ma20, 2)
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        
        sector = get_sector_cached(ticker)
        status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢整理中"
        
        return [
            ticker, round(curr_p, 2), dist_high, sctr_val, "✅ 緊湊/安靜" if is_tight else "❌", vol_ratio, status, sector,
            round(pivot_point, 2), round(stop_loss, 2), round(target_price, 2)
        ]
    except: return None
    return None

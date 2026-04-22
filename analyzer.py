# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
# 從 data_loader 匯入行業抓取函式
from data_loader import get_sector_cached

def calculate_sctr_ranks(tickers):
    try:
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        data = raw_data['Close'] if 'Close' in raw_data else raw_data
        
        sctr_data = []
        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) < 200: continue
                
                sma200, sma50 = series.rolling(200).mean().iloc[-1], series.rolling(50).mean().iloc[-1]
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
        
        # 提取高、低、收、量以計算 ATR
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        high = df['High'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['High']
        low = df['Low'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Low']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        
        curr_p = float(close.iloc[-1])
        
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        
        cond = [
            curr_p > sma150 and curr_p > sma200, sma150 > sma200, 
            sma50 > sma150 and sma50 > sma200, curr_p > sma50,
            curr_p >= (low52 * 1.25), curr_p >= (high52 * 0.75)
        ]
        
        if sum(cond) == 6:
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            prev_range = (close.iloc[-25:-5].max() - close.iloc[-25:-5].min()) / close.iloc[-25:-5].min()
            is_tight = "✅ 緊湊" if recent_range < (prev_range * 0.7) else "❌ 鬆散"
            
            recent_max = float(close.iloc[-(b_days+1):-1].max())
            is_breakout = curr_p > recent_max
            if b_only and not is_breakout: return None
            
            # 計算 ATR (Average True Range)
            atr_series = ta.atr(high, low, close, length=14)
            atr_val = float(atr_series.iloc[-1]) if not atr_series.isna().iloc[-1] else (float(high.iloc[-1]) - float(low.iloc[-1]))
            
            # 建立交易決策點位
            pivot_point = recent_max  # 樞軸點(Pivot)為近期高點
            stop_loss = curr_p - (1.5 * atr_val)  # 停損設為當下價格減去 1.5 倍 ATR
            target_price = curr_p + (3.0 * (curr_p - stop_loss)) # 風險報酬比 1:3 目標價
            
            dist_high = round((1 - curr_p/high52) * 100, 2)
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            sctr_val = round(sctr_map.get(ticker, 0), 1)
            
            # 取得行業資訊
            sector = get_sector_cached(ticker)
            status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢向上"
            
            # 回傳新增 Pivot, Stop Loss, Target
            return [
                ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, status, sector,
                round(pivot_point, 2), round(stop_loss, 2), round(target_price, 2)
            ]
    except: return None
    return None

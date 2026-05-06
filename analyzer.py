# analyzer.py
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
from data_loader import get_sector_cached

# ==================== 🛠️ 數據中台無痛代理代理器 ====================
def get_klines_from_supabase(tickers):
    """
    優先從 Supabase 中台的 stock_klines 資料表高速載入 K 線。
    若載入失敗或無資料，會直接回傳 None，自動降級調用 yfinance。
    """
    try:
        from data_loader import supabase
        if supabase is None:
            return None
        
        # 批次向 Supabase 查詢這群股票的 K 線資料
        res = supabase.table("stock_klines")\
            .select("ticker, date, open, high, low, close, volume")\
            .in_("ticker", tickers)\
            .order("date", desc=False)\
            .execute()
        
        if not res.data:
            return None
            
        df_all = pd.DataFrame(res.data)
        df_all['date'] = pd.to_datetime(df_all['date'])
        
        # 重構為相容 yf.download(group_by='column') 格式的 MultiIndex 結構，確保後面完全不用改程式
        pivoted_close = df_all.pivot(index='date', columns='ticker', values='close')
        pivoted_open = df_all.pivot(index='date', columns='ticker', values='open')
        pivoted_high = df_all.pivot(index='date', columns='ticker', values='high')
        pivoted_low = df_all.pivot(index='date', columns='ticker', values='low')
        pivoted_volume = df_all.pivot(index='date', columns='ticker', values='volume')
        
        # 建立 MultiIndex 欄位
        pivoted_close.columns = pd.MultiIndex.from_product([['Close'], pivoted_close.columns])
        pivoted_open.columns = pd.MultiIndex.from_product([['Open'], pivoted_open.columns])
        pivoted_high.columns = pd.MultiIndex.from_product([['High'], pivoted_high.columns])
        pivoted_low.columns = pd.MultiIndex.from_product([['Low'], pivoted_low.columns])
        pivoted_volume.columns = pd.MultiIndex.from_product([['Volume'], pivoted_volume.columns])
        
        combined = pd.concat([pivoted_open, pivoted_high, pivoted_low, pivoted_close, pivoted_volume], axis=1)
        combined.index.name = 'Date'
        return combined
    except Exception as e:
        print(f"⚠️ 從中台讀取 K 線失敗，將自動降級採用原 yf.download: {e}")
        return None
# =======================================================================================


def calculate_sctr_ranks(tickers, lookback=20):
    """
    計算當前與 lookback 天前的 SCTR，用來衡量動能是否持續攀升
    """
    try:
        # ------------------ 🌟 劫持點：優先讀取 Supabase，失敗則使用 yf.download ------------------
        raw_data = get_klines_from_supabase(tickers)
        if raw_data is None or raw_data.empty:
            # ⬇️ 這是你原本的下載代碼，完全保留 ⬇️
            raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        # --------------------------------------------------------------------------------------
        
        data = raw_data['Close'] if 'Close' in raw_data else raw_data

        sctr_current = []
        sctr_historical = []

        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) < 200 + lookback: continue

                # 輔助計算函數 (你原本的邏輯，完全保留)
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
        # ------------------ 🌟 劫持點：優先讀取 Supabase，失敗則使用 yf.download ------------------
        df = get_klines_from_supabase([ticker])
        if df is None or df.empty:
            # ⬇️ 這是你原本的下載代碼，完全保留 ⬇️
            df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        # --------------------------------------------------------------------------------------
        
        if df.empty or len(df) < 200:
            return None

        # ---------- 資料解析 (完全保留你原本的邏輯) ----------
        if isinstance(df.columns, pd.MultiIndex):
            close = df['Close'][ticker]
            high  = df['High'][ticker]
            low   = df['Low'][ticker]
            vol   = df['Volume'][ticker]
        else:
            close = df['Close']
            high  = df['High']
            low   = df['Low']
            vol   = df['Volume']

        curr_p = float(close.iloc[-1])

        # ---------- 均線 ----------
        sma50  = ta.sma(close, 50).iloc[-1]
        sma150 = ta.sma(close, 150).iloc[-1]
        sma200 = ta.sma(close, 200).iloc[-1]
        low52  = float(close.min())
        high52 = float(close.max())

        # ========== 1. 趨勢模板（放寬至 5 項及格） ==========
        cond = [
            curr_p > sma150 and curr_p > sma200,                      # 中期趨勢向上
            sma150 > sma200,                                          # 長線多頭排列
            sma50 > sma150 or (sma50 > sma200 and sma50 > sma150*0.98),  # 剛金叉可接受
            curr_p > sma50 or curr_p > sma50*0.98,                    # 容錯
            curr_p >= low52 * 1.2,                                    # 底部放寬
            curr_p >= high52 * 0.65                                   # 回調 35% 以內接受
        ]
        if sum(cond) < 6:
            return None

        # ========== 2. 成交量萎縮（檢查醞釀期，非單日） ==========
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        vol_ma50 = vol.rolling(50).mean().iloc[-1] if len(vol) >= 50 else vol_ma20
        recent_vol_avg = vol.iloc[-10:].mean()

        # 近期均量明顯低於中期均量，代表籌碼沉澱
        vol_dry_up = (recent_vol_avg < vol_ma20 * 0.85) or (vol_ma20 < vol_ma50 * 0.9)
        if not vol_dry_up:
            return None

        # ========== 3. VCP 波動收縮（改用區間低點邏輯） ==========
        windows = [
            close.iloc[-100:-70],
            close.iloc[-85:-55],
            close.iloc[-70:-40],
            close.iloc[-55:-25],
            close.iloc[-40:-15]
        ]

        ranges = []
        for w in windows:
            if len(w) >= 4:
                r = (w.max() - w.min()) / w.min()
                ranges.append(r)
            else:
                ranges.append(ranges[-1] if ranges else 0.25)

        valid_ranges = [r for r in ranges if r > 0]
        if len(valid_ranges) < 2:
            return None

        # 檢查最後一段波動率是否仍處於低檔（未顯著反彈）
        if len(valid_ranges) >= 3:
            last_three = valid_ranges[-3:]
            if valid_ranges[-1] > min(last_three) * 1.1 and valid_ranges[-1] > 0.03:
                return None

        # ---------- ATR 與緊密度 ----------
        atr_series = ta.atr(high, low, close, length=14)
        atr_val = float(atr_series.iloc[-1]) if not atr_series.isna().iloc[-1] else (float(high.iloc[-1]) - float(low.iloc[-1]))

        w1 = close.iloc[-5:]
        w1_abs_range = float(w1.max() - w1.min())
        w1_pct = (w1.max() - w1.min()) / w1.min() if w1.min() > 0 else 1

        if w1_abs_range <= 1.6 * atr_val and w1_pct <= 0.12:
            is_tight = "✅✅ 極緊"
        elif w1_abs_range <= 2.0 * atr_val and w1_pct <= 0.15:
            is_tight = "✅ 緊湊"
        elif w1_abs_range <= 2.3 * atr_val and w1_pct <= 0.18:
            is_tight = "🔸 尚可"
        else:
            return None

        # ========== 4. SCTR 動能 ==========
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_hist = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 70:
            return None
        sctr_accelerating = (sctr_val - sctr_hist) > 1.5
        if not sctr_accelerating and sctr_val < 80:
            return None

        # ========== 5. 突破／預突破狀態 ==========
        recent_max = float(close.iloc[-(b_days+1):-1].max())
        is_breakout = curr_p > recent_max

        resistance = float(high.iloc[-16:-1].max())
        distance_to_res = round((resistance / curr_p - 1) * 100, 2)

        pre_breakout = (not is_breakout) and (distance_to_res < 1.5) and ("極緊" in is_tight)

        if b_only and not (is_breakout or pre_breakout):
            return None

        if is_breakout:
            status = f"🔥 {b_days}D突破"
        elif pre_breakout:
            status = f"⚡蓄勢待發(距突破{distance_to_res}%)"
        else:
            status = "🚀 強勢向上"

        # ========== 6. 風險報酬 ==========
        pivot_point = recent_max
        atr_val = ta.atr(high, low, close, length=14).iloc[-1]
        stop_loss = curr_p - (1.5 * atr_val)
        target_price = curr_p + (3.0 * atr_val)
        
        industry = get_sector_cached(ticker)
        dist_from_high = round(((h_52w - curr_p) / h_52w) * 100, 2)

        return [
            ticker, round(curr_p, 2), dist_high, sctr_val, is_tight,
            vol_ratio, status, sector,
            round(pivot_point, 2), round(stop_loss, 2), round(target_price, 2)
        ]

    except Exception:
        return None

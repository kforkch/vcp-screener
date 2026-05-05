def check_vcp_advanced(ticker, sctr_map, sctr_hist_map, b_only, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200:
            return None

        # ---------- 資料解析 ----------
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
        if sum(cond) < 5:
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
                # 資料不足時沿用上一段數值
                ranges.append(ranges[-1] if ranges else 0.25)

        valid_ranges = [r for r in ranges if r > 0]
        if len(valid_ranges) < 2:
            return None

        # 檢查最後一段波動率是否仍處於低檔（未顯著反彈）
        if len(valid_ranges) >= 3:
            last_three = valid_ranges[-3:]
            # 若最後一段不是近三段最低，且數值仍偏高，則排除
            if valid_ranges[-1] > min(last_three) * 1.1 and valid_ranges[-1] > 0.03:
                return None

        # ---------- ATR 與緊密度 ----------
        atr_series = ta.atr(high, low, close, length=14)
        atr_val = float(atr_series.iloc[-1]) if not atr_series.isna().iloc[-1] else (float(high.iloc[-1]) - float(low.iloc[-1]))

        w1 = close.iloc[-5:]                 # 最近 5 天
        w1_abs_range = float(w1.max() - w1.min())
        w1_pct = (w1.max() - w1.min()) / w1.min() if w1.min() > 0 else 1

        # 三段式緊湊度判定
        if w1_abs_range <= 1.6 * atr_val and w1_pct <= 0.12:
            is_tight = "✅✅ 極緊"
        elif w1_abs_range <= 2.0 * atr_val and w1_pct <= 0.15:
            is_tight = "✅ 緊湊"
        elif w1_abs_range <= 2.3 * atr_val and w1_pct <= 0.18:
            is_tight = "🔸 尚可"
        else:
            return None

        # ========== 4. SCTR 動能（門檻降至 70，加入加速判斷） ==========
        sctr_val = round(sctr_map.get(ticker, 0), 1)
        sctr_hist = round(sctr_hist_map.get(ticker, 0), 1)
        if sctr_val < 70:
            return None
        # 必須是動能加速中（進步超過 1.5 個百分點），或是已達 80 分以上
        sctr_accelerating = (sctr_val - sctr_hist) > 1.5
        if not sctr_accelerating and sctr_val < 80:
            return None

        # ========== 5. 突破／預突破狀態判定 ==========
        recent_max = float(close.iloc[-(b_days+1):-1].max())
        is_breakout = curr_p > recent_max

        # 預突破：距近期阻力 < 1.5% 且為極緊狀態
        resistance = float(high.iloc[-16:-1].max())  # 近 15 天最高價（不含今日）
        distance_to_res = round((resistance / curr_p - 1) * 100, 2)

        pre_breakout = (not is_breakout) and (distance_to_res < 1.5) and ("極緊" in is_tight)

        # b_only 篩選原則：若要求只看突破，則保留突破或預突破候選
        if b_only and not (is_breakout or pre_breakout):
            return None

        # 狀態文字
        if is_breakout:
            status = f"🔥 {b_days}D突破"
        elif pre_breakout:
            status = f"⚡蓄勢待發(距突破{distance_to_res}%)"
        else:
            status = "🚀 強勢向上"

        # ========== 6. 風險報酬與其他欄位 ==========
        pivot_point = recent_max
        stop_loss = curr_p - (1.5 * atr_val)
        target_price = curr_p + (3.0 * (curr_p - stop_loss))

        dist_high = round((1 - curr_p / high52) * 100, 2)
        vol_ratio = round(float(vol.iloc[-1]) / vol_ma20, 2)

        sector = get_sector_cached(ticker)

        return [
            ticker, round(curr_p, 2), dist_high, sctr_val, is_tight,
            vol_ratio, status, sector,
            round(pivot_point, 2), round(stop_loss, 2), round(target_price, 2)
        ]

    except Exception:
        return None
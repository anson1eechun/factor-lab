# SIM-2026-09-23-003 — FSIM_Volume_Volatility_Discount(辯論模擬 · v3)

**裁決:REJECT**(獨立 Arbiter)· 家族 `xs.liquidity_risk`(新開)· 類型 cross · 80 幣 universe_1d · 2019-12-25 ~ 2026-07-04(6.53 年)

## 1. Proposer
- 假設:成交額呈脈衝式的幣由注意力交易者定價、在賣空受限下被高估 → 成交額波動越高後續報酬越低(Chordia–Subrahmanyam–Anshuman 2001 crypto 版)。
- 公式:`SIG = std_60(Δlog(close×volume))`,shift(1),`direction −1`;hold 20、q 5、10 bps、含 funding;非複合訊號;planned_trials 1。
- 必死條款 K1–K6(LOYO、殘差化保留、多頭腿須有超額、打平成本 ≥20 bps、延遲進場、OOS>0)。

## 2. Builder
- `core/signals/FSIM_Volume_Volatility_Discount.py`;smoke 通過、lint 乾淨。
- 指出 prereg §2「不得在模組內 shift(1)」與 pack `entry_lag=0` 語意矛盾(照字面會前視 1 期);主代理於 Stage 0 前、未看任何數字時勘誤,prereg 內留有勘誤註記。

## 3. Stage 0 — PASS
lint 乾淨、截斷 40 日逐位一致、無家族封線衝突。控制變數自身 IC(NW t):mom20 −0.0210(−4.80)適格、sig20 −0.0621(−13.22)不適格、max21 −0.0517(−13.07)不適格、ladv20 +0.0024(+0.59)適格。
噪音通過率(K=20):S2 5%、S3 0%、T1 0%、T2 0%、T3 25% → 全部計入。複製鎖 PASS。

## 4. Empiricist 套餐(`empiricist_pack.py run`)
| 閘門 | 結果 | | 指標 | 值 |
|---|---|---|---|---|
| S1 \|IC\|>0.02 | PASS | | rank IC(h1) | +0.0277 |
| S2 IC NW t≥2 | PASS | | IC NW t | 8.22 |
| S3 IC-IR≥0.3 | FAIL | | IC-IR | 0.171 |
| T1 淨Sh≥1 或 Mono≥0.7 | FAIL | | 淨 / 毛 Sharpe | −0.764 / −0.575 |
| T2 淨 NW t≥2 | FAIL | | 淨 NW t | −1.92 |
| T3 MaxDD>−30% | FAIL | | MaxDD | −98.8% |
| R1 LOYO t≥1.5 | FAIL | | loyo_min | −2.37 |
| R2 延遲進場 | PASS | | Mono | −0.6 |
| R3 成分 | — | | 換手/日 · 成本拖累 · funding | 0.079 · −2.9%/年 · −6.6%/年 |
| D1 Bonferroni | PASS | | IS / OOS(2024+)淨 Sharpe | −1.39 / +1.15 |
| D2 DSR | FAIL | | 非重疊 IC t h1/h5/h10/h20 | 8.36 / 3.48 / 2.82 / 1.68 |

計入閘門 4/10。五分位淨均報酬(宣告方向 Q1→Q5):2.52e-3, 1.86e-3, 1.22e-3, 1.31e-3, 1.54e-3 — 空頭腿最高。

## 5. Risk
殘差化(適格控制 mom20、ladv20):IC 0.0224(t 6.8)、淨 Sharpe 0.086。與控制的淨報酬相關 mom20 −0.34、sig20 −0.27、max21 −0.37、ladv20 +0.30。book Sharpe −0.215、50/50 混合 −0.850、**邊際 Sharpe −0.635**、打平成本 −100 bps。

## 6. Skeptic(10 點,主代理以 `/tmp/skeptic_003.py` 全數重現)
- [高] 虧損在空頭腿右尾:空頭腿超額 Sharpe −0.85、偏態 −2.23;最差 1% 日子占總和 −2.37/−1.98,剔除後 +0.39。多頭腿超額 −0.23。毛層已虧。
- [高] K3 命中:Q5 淨均 1.539e-3 < 五分位平均 1.690e-3。
- [高] 集中度:最高成交額波動組 20 日報酬均值 +4.2%、中位數 −3.0%、偏態 5.8;前 1% 觀測占 59%,前 5 幣(DOGE/CHZ/AXS/MANA/WAVES)占 55%,事後剔除後淨 Sharpe 仍僅 0.21。
- [高] IS/OOS 反差非排序層驅動:rank IC IS 0.040 → OOS 0.009;淨 Sharpe 反向,beta 調整後不變。
- [中] 2019 僅 7 天;IC t 8.2 為 h1,hold 20 對應非重疊 t 1.68。
- [中] 與低波動部分重疊:rank 相關 sig20 −0.20、sig60 −0.25、max21 −0.19;⊥sig20 IC 0.0154(t 5.1)淨 Sh −0.67;⊥四控制 IC 0.0139 淨 Sh 0.12。
- [中] sig20/max21「不適格」是符號慣例假象(見 §9)。
- [低] N 記法不影響閘門;前視/記帳無問題(固定權重 −0.77 ≈ 漂移 −0.76)。

## 7. Arbiter(獨立子代理)— REJECT
- 美元層不可收割:淨 −0.764、毛 −0.575、MaxDD −98.8%,T1/T2/T3 全 FAIL。
- 必死條款命中 K1(loyo −2.37)、K3、K4(打平 −100 bps);K5/K6 未命中 = 無資訊;K2 前提不成立作廢。
- 偽陽性型態:IC 顯著僅在 h1,IC-IR 0.171、h20 非重疊 t 1.68。OOS +1.15 與 IC≈0 脫鉤,不構成救援。
- 可保留事實:排序層(中位數)方向為真 —— §11.2「排序層真、美元層死」第 5 次出現。
- 多重比較:N=11、Bonferroni 2.838、DSR 0.857;觀測 IC t 8.22(D1 PASS)、淨 Sharpe −0.764(D2 FAIL);N=1/3/11 皆同結論。

## 8. 多重比較 / ledger
家族 `xs.liquidity_risk` N=11(stage0 1 + 主規格 1 + 殘差化 1 + Skeptic 診斷 8,皆記 `kind: trial`);實質獨立預註冊規格 1。

## 9. 流程缺陷(本輪發現,未改規則)
1. **控制變數適格判斷只比 IC 符號**:pack 未考慮控制與候選的相關符號。本輪 −sig20 與候選同向且更強,殘差化應為有效檢定(v2.4 §4 要防的 >100% artifact 不適用)。Arbiter 建議改為「乘過方向後比較」。
2. **診斷列灌水家族 N**:stage0 篩檢、殘差化、Skeptic 診斷皆記 trial,同一假設 N 從 1 變 11。
3. **summary 抬頭 N(3)未與 `ledger.py n`(11)同步**。
4. **hold>1 時 S2 用 h1 IC t**,應以持有期 horizon 的非重疊 t 為主口徑。
5. `pack noise` 在 pandas CoW 下陣列唯讀而崩潰,已修(`np.array(S.values, dtype=float)`)。

## 10. v3.1 追溯(2026-09-24,§9 第 1–4 項已修;正式 results.json 未重寫)
隔離環境以 v3.1 pack 重跑同一凍結規格:回測數字逐位一致;S2/D1 閘門 t = min(h1 8.22, h20 NW 2.65, h20 非重疊 1.68) = 1.68 → **FAIL**;
sig20/max21 對齊後適格,四控制殘差化淨 Sharpe 0.122、IC t 4.53(與 Skeptic all4 獨立結果一致);家族 N 依新計數規則 = 1。
新口徑下 D2 FAIL 且 S2/D1 FAIL → 屬機械判死;**裁決 REJECT 不變**。

## 產物
`SIM-2026-09-23-003_{prereg.md,spec.json,stage0.json,noise.json,lock.json,results.json,summary.md,archive.json}`、`core/signals/FSIM_Volume_Volatility_Discount.py`、`deprecated/FSIM_Volume_Volatility_Discount.md`。

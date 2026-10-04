# SIM-2026-07-04-001 — FSIM_HollowLeverage(空心槓桿)辯論報告

> kind: 辯論模擬 · 裁決:**REJECT** · 歸檔:`deprecated/FSIM_HollowLeverage.md`
> 來源:Obsidian 知識庫驅動(`08-加密貨幣/01-永續合約與資金費率.md` §素材D「funding×價格背離」未試方向)
> 資料:`universe_1d.pkl`(80幣) + `funding_1d.pkl`(79幣),2023-03-11 ~ 2026-06-07

## 一、七階段摘要

| 階段 | 執行者 | 要點 |
|---|---|---|
| Proposer | 子代理 | 假設:資費相對同儕加速上升但價格未跟漲=槓桿多頭堆積無現貨支撐(「付費維持的空心擁擠」)→ 橫截面後續相對弱。每日 rank-OLS:u(dF7) 對 {u(r7), u(r7lag), u(f3)} 取殘差 ε,S=−ε。預註冊:smooth3/dF7/minN40/hold1,零掃描 |
| Builder | 子代理 | `core/signals/FSIM_HollowLeverage.py`;smoke 全過:無前視不變性 PASS(截斷重算 1871 日全等)、殘差正交 <1e-15、S 對同日報酬 pooled \|ρ\|=0.006 |
| Empiricist | 主代理 | 標準套餐全跑(下表);3 筆試驗入 ledger(主規格+hold7/10 診斷) |
| Risk | 主代理 | 預註冊方向 gross 為負→邊際貢獻<0;翻號版與 Funding-Carry corr +0.266 且 gross 0.68 < carry 1.14,被支配 |
| Skeptic | 子代理 | 負面結論四個翻案通道(符號/時序/對齊/資料)逐一查閉;倖存宇宙限定措辭;翻號=事後假設不值得追;警告 funding 家族規格漂移(已 4+ 筆) |
| Arbiter | 獨立子代理 | **REJECT**(六門檻全敗+雙閘門皆敗+翻號經 64 筆家族 Bonferroni 校正 p≈3.0 不顯著) |
| Librarian | 主代理 | 本報告+deprecated 筆記+index.db+factors+ledger |

## 二、Empiricist 標準套餐(全真實,`scripts/hollow_leverage_eval.py`)

主規格(預註冊 hold=1, cost 10bps),n=1184 日:

| 指標 | 門檻 | 實測 | 判定 |
|---|---|---|---|
| Rank IC mean | \|IC\|>0.02 | **−0.0075**(方向相反) | ✗ |
| IC-IR | >0.3 | −0.058 | ✗ |
| ic_t(日頻非重疊) | ≥2 | −1.99 | ✗ |
| LS Sharpe(quintile) | >0.5 | gross −0.68 / net −2.82 | ✗ |
| MaxDD | <30% | −91.7%(net) | ✗ |
| Mono | ≥0.7 | **−0.9** | ✗ |

- 五分位日均 fwd(Q0→Q4):5.3 / 3.2 / 1.8 / 2.8 / 0.5 bps——**被 short 的 Q0(空心槓桿幣)是最強分位**
- rank 權重組合(預註冊):gross −0.55 / net −2.88,年換手 **449x**(成本拖累 ≈2.2 Sharpe)
- 年度(rankw net):2023 −2.49 / 2024 −2.94 / 2025 −4.13 / 2026 −0.75;年度 IC 全負(2026 +0.0025, t 0.24 → 訊號歸零)
- IS/OOS 對半 IC:−0.0055 / −0.0096(兩半一致反向)
- 剔 \|LS\| top5% 日:−3.14(更負,非尾部事件驅動)
- 市場中性:對等權市場 corr 0.047 / beta 0.012(中性化成功,非 beta 汙染)
- hold=7 / 10 診斷:gross −0.31 / −0.17(拉長持有無救援)
- 資料合法性:funding lead-lag k=−1 最強(BTC .135/ETH .189/SOL .231/DOGE .294)、k≥+1 近零 → 無錯位

## 三、裁決(Arbiter 獨立)

**REJECT**。六項門檻全敗且為「穩健反向」而非「不顯著」;雙閘門(Gate1 IC-IR、Gate2 Sharpe/Mono)皆敗。唯一可談顯著性的是事後翻號讀法:|t|=1.99 單次 p≈0.047,×64(全 ledger 試驗數)≈3.0,徹底不顯著,且 2026 年已歸零、與 Funding-Carry 重疊(corr +0.266)且更弱、449x 換手下淨值無論如何深負。不給 REWORK:保留名額只會誘發 funding 家族第 5、6 筆規格漂移。

**範圍限定**:證偽的是「79 幣倖存宇宙+此預註冊 timing 下的空心槓桿假設」,不得外推為「爆倉機制不存在」——該 payoff 可能集中於已下架幣,倖存宇宙先天測不到(「機制住在被差掉的成分」的宇宙版)。

## 四、機制教訓(本輪真正產出)

1. **第二次獨立佐證:日頻上「funding 上升→續漲而非崩盤」**(第一次=aggregate-funding overlay REJECT)。資費是槓桿需求的即時價格;資費加速而價格未動=衍生品走在現貨前面=**待補漲名單**,不是脆弱名單。原假設把因果方向弄反。
2. **funding 的 horizon 結構浮現**:變化維(dF,日級)=需求衝擊後數日續動,做空=逆著 flow;水位維(level,週級)=慢速均值回歸+被付錢做空,hold10 的 carry 才收得到。兩維並存不矛盾。
3. **擁擠爆倉是事件性、叢集式 payoff**,日頻平滑殘差抓不到;疊加倖存宇宙(爆掉的幣已下架),此類假設在本資料上結構性測不到。
4. funding 家族累計 4+ 筆(carry REWORK / momentum REWORK / overlay REJECT / 本輪 REJECT):後續任何複合/降頻/翻號變體須**全新預註冊+揭露家族試驗計數**,否則即規格漂移。

## 五、Ledger

本輪 3 筆(#62-64):主規格 REJECT(假設證偽,錯方向)、hold7 診斷、hold10 診斷。全 ledger 64 筆,crypto XS 0 validated。

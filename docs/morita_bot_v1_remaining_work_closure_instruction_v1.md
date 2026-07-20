# 送付先：新規統合室

## 対象テーマ：森田bot v1 残件一括閉鎖（3優先バックテスト／Short／Absorption Buy the Dip／Forward通知／Unified Flow）

以下を、このリポジトリに対する一括実行指示として扱ってください。質問待ちで止まらず、リポジトリ内の既存コード・設定・レポート・テスト・ログを先に調査し、安全に実行可能な範囲を最後まで進めてください。

---

# 森田bot v1 残件一括閉鎖指示書 v1

## 0. 今回の最終目的

森田bot v1を、次の3系統を「通知・記録・手動執行できる」状態まで持っていく。

1. `BREAKOUT`
2. `BREAKDOWN_SHORT`
3. `ABSORPTION_BUY_THE_DIP`

3系統のどれにも該当しない場合は、必ず`NO_TRADE`を明示する。

今回の完成条件は自動売買ではない。ブローカーへの自動注文、オプション自動発注、資金移動は実装・有効化しない。人間が通知内容を確認して手動執行できるところまでをv1とする。

新機能を無制限に追加する作業ではない。既存の設計・実装・研究成果を棚卸しし、未完了部分を実データ、テスト、ログ、レポートで閉じることを優先する。

## 1. 作業原則

### 1.1 正本の優先順位

矛盾がある場合は、次の順で正本を決める。

1. 現在のリポジトリ内で実際に動くコードとテスト
2. 実データから生成された再現可能な結果・ログ
3. 最新のstatus handoff／review bundle
4. 古い指示書・会話上の仮説

古い報告をそのまま現在状態とみなさない。既に実装済みのものを重複実装しない。

### 1.2 最初に必ず行うこと

- `AGENTS.md`およびリポジトリ固有の指示を読む。
- `git status`を確認し、ユーザーの既存変更を保持する。
- 破壊的なreset、checkout、cleanを行わない。
- 関連ファイルを`rg`で検索し、既存実装と未完了TODOを把握する。
- APIキー、Secret、トークン、口座情報をログや成果物に出力しない。
- 実データがない箇所に合成データを混ぜて「実証済み」としない。
- 欠損を0、未発火を敗北、取引0件をPF=0と勝手に変換しない。

### 1.3 最初に探す既存成果物

少なくとも以下を検索し、存在・最新版・内容・現在のコードとの整合を確認する。ファイル名にコピー番号が付いている場合は内容ハッシュまたはdiffで重複を判定する。

- `morita_three_priority_backtests_v1_chatgpt_review_bundle.md`
- `morita_wfe_forward_seed_activation_v1_3_chatgpt_review_bundle.md`
- `morita_wfe_forward_seed_activation_v1_3_report.md`
- `morita_overnight_relief_rejection_weak_s_put_v1_1_chatgpt_review_bundle*.md`
- `morita_databento_4x4_matched_pilot_v1_2_chatgpt_review_bundle.md`
- `morita_s_option_flow_attribution_v1*`
- `morita_option_flow_attribution_pilot*`
- `morita_current_conditions_sa_rebuild_v1*`
- `morita_unified_flow_v3_7*`
- `morita_unified_flow_v3_8*`
- `morita_historical_pit_m15_autonomous_recovery_v1_2*`
- `morita_historical_s_aplus_replay_v1_3*`
- `morita_dip_failure_regime_transition_short_research_instructions_v1.md`

最初に「既存／完了／部分完了／未着手／データ待ち／重複」の棚卸し表を作る。ただし、棚卸しだけで作業を終了せず、その後の実装・検証を続ける。

## 2. 固定する既存仕様

既存コードまたは最新正本で明確に変更されていない限り、以下を勝手に再最適化しない。

- Long Sの基本条件：`RS >= 98`、終値ブレイク、出来高条件、既存Gap/Biotech/価格フィルター
- Dispersion閾値：`D = 0.1076297441`
- Narrow Leadership閾値：`L = 0.02116006335`
- Long Sの通常サイズ：現行正本を維持
- High Dispersion／NLR時のサイズ抑制：既存overlayを維持
- S通知日以外は買わないという運用原則
- Shortは当面、研究・通知・手動執行。自動注文しない
- Buy the Dipは独立した常時買いbotではなく、売り圧吸収とShort終了を確認する反転モジュールとして扱う

閾値再推定を行う場合は、既存固定閾値を使った主結果と完全に分離し、感度分析としてのみ報告する。

## 3. PITと検証範囲

### 3.1 期間・対象

主検証は、全銘柄・全期間へ拡張せず、次に限定する。

- 2024年から2026年までの主要調整局面
- 各時点で実際にActiveだったS／A+／アンカー銘柄
- 半導体・AI関連を優先
- 2026年7月の直近調整を必ず1イベントとして含める

利用可能なら2025年4月、2026年6月から7月、既存レポートが指定する代表イベントを含める。イベント選択は後から成績を見て恣意的に変更しない。

### 3.2 PIT厳守

- 銘柄ランクはその日時点で利用可能だったランクを使用する。
- 会社ガイダンス、決算、マルチプル、価格、出来高、オプション情報もその時点までの情報だけを使用する。
- 修正済みデータや現在の分類を過去へ遡及利用した場合は、PIT主結果から分離する。
- シグナル計算時刻より後の足を、当該シグナルの特徴量に含めない。
- 同一日のCloseを使ってClose約定を仮定する場合は、シグナル確定可能時刻と約定可能性を明記する。

## 4. Phase A：3つの優先バックテスト

既存の`morita_three_priority_backtests`に最新版の定義がある場合は、その受入条件を保持する。ファイル名が同じで異なる3本を指している場合は上書きせず、内容を識別して差分を報告する。

今回、最低限完了させる3本は以下とする。

### A1. 状態遷移バックテスト

以下の状態間の遷移が、将来リターンと損失回避に意味を持つか検証する。

- `BREAKOUT`
- `BREAKDOWN_SHORT_WATCH`
- `BREAKDOWN_SHORT_CONFIRMED`
- `ABSORPTION_WATCH`
- `ABSORPTION_CONFIRMED`
- `NO_TRADE`

検証項目：

- Long継続とShort移行の比較
- Short継続とAbsorptionでの利確・停止の比較
- 状態遷移の先行日数・遅行日数
- false switch率
- missed rebound率
- missed decline率
- MFE／MAE
- 最大DD
- 状態別の翌日、2日、5日、10日リターン
- 状態別のS群、SOXX／SMH、アンカー群の差

最低限、イベント単位、日単位、銘柄単位の3階層で結果を出す。同一イベント内の観測を独立標本として水増ししない。

### A2. S群＋アンカー吸収シグナル

次の特徴が「絶対資金帯／吸収」を示すか検証する。

- 出来高が高いのに下落率が縮小する
- 単位出来高当たりの下落効率が悪化する
- 寄りから引けのリターンが改善する
- 最強Sが寄り引けプラスへ転換する
- 弱Sの下落率が縮小する
- 複数Sとアンカーが同日に下げ止まる
- LRCX／AMAT／KLAC／MKSI等のアンカーが安値更新を止める
- 翌日または2日連続で陽線・高値切り上げが発生する

少なくとも以下を比較する。

1. 最強S単独
2. アンカー単独
3. 最強S＋アンカー同期
4. S群全体のbreadth改善
5. 上記の組合せ

出力：

- 翌日、2日、5日、10日反発率
- MFE／MAE
- 反発までの日数
- 一時停止のみで再下落した割合
- アンカー割れ後の下落継続率
- Short利確シグナルとして使った場合の効果
- Buy the Dipエントリーとして使った場合の効果

### A3. Short対象選択バックテスト

同一イベント・同一エントリー時刻・同一Exit条件で、以下を比較する。

1. 当日時点の最弱S
2. それまで最強だったが崩れたFormer Leader S
3. S群の中央値銘柄
4. SOXX／SMH等の指数・ETF

主仮説は「すでに売られ過ぎた最弱Sより、買い手が残っていたFormer Leaderが崩れた初期の方がShortの値幅を取りやすい」である。ただし、結論を先に固定しない。

比較指標：

- 勝率、平均、中央値、PF
- MFE／MAE
- ギャップリスク
- 寄り30分、60分、引け、翌日寄りまでの損益
- 月曜除外の有無
- Strong-S崩壊確認の有無
- S複数同時下落条件の有無
- 下落前に既に売られていた距離・RS劣化度
- 実オプション価格があるケースと原資産proxyの分離

オプション実価格がない場合、原資産リターンだけから架空のPut収益率を生成して主結果にしない。

## 5. Phase B：Short bot正式検証

### 5.1 現行仮説

最低限、次のルールセットを再現する。

- 最強Sを含む複数Sが同日大きく崩れる
- 半導体・AIの構造的なリスク削減フローを優先
- 翌日の弱いOvernight reliefまたは寄り後の再下落を確認して入る
- 寄りから30分および60分で仮説検証する
- 寄りから60分以内に売り継続が確認できなければ撤退
- 月曜は原則除外し、月曜込みを感度分析として分離
- Exitは当日引けを主とし、翌日寄りを副比較とする
- アンカー吸収・最強S下げ止まり・ニュース好転で停止または利確する

「S複数下落」の閾値は既存正本を優先する。複数候補がある場合、主仕様を1つ固定し、例えば`-5%`、`-8%`等は感度分析として分離する。

### 5.2 必要データ

可能な範囲で以下の15分足を取得・正規化し、必要なら30分足を生成する。

- SOXX、SMH
- NVDA、AVGO
- AMAT、LRCX、KLAC、MKSI、TER
- MU、WDC
- 当時のActive S／A+

価格調整、タイムゾーン、通常取引時間、時間外取引の有無を明記する。時間外データがない場合は`STRATEGY_NOT_EVALUATED_OVERNIGHT_DATA_MISSING`等の明確なstatusを返し、0件を不採用成績として扱わない。

### 5.3 検証ゲート

以下を満たすまで`execution_allowed=true`にしない。

- 実トリガーが1件以上存在する
- エントリーとExit価格が再現可能
- 未来情報混入がない
- イベントごとの結果が確認できる
- 原資産proxyと実オプション成績が混同されていない
- 欠損データの影響が明示されている
- 少数標本の場合、`RESEARCH_ONLY`または`SHADOW_ONLY`を維持する

3イベント程度ならshadow、5イベント以上でも独立局面が不足するならrobustと断定しない。

## 6. Phase C：Absorption Buy the Dip／PIT Guidance Multiple

### 6.1 位置づけ

Buy the Dipは、単なる値下がり買いではない。

1. ファンダ仮説が維持されている
2. 理論価格または資金帯まで十分な距離を調整した
3. 売り効率が低下した
4. 強Sまたはアンカーで実際の買いが観測された

この4段階を満たす場合のみ候補とする。

### 6.2 PIT Guidance Multiple Pilot

2024年から2026年の調整局面＋当時Active Sに限定し、以下を計算する。

- その時点の会社ガイダンスに基づく利益・売上・FCF等の基準値`V_t`
- その時点で利用可能な比較マルチプルまたは妥当な`A`
- 現在価格の理論価格からのDiscount
- 20%、30%等のDiscount帯別の反発確率
- 到達後の反発日数、MFE、MAE
- ガイダンス更新またはCAPEX仮説崩壊時の再計算

`V_t`または`A`を作れないケースは、無理にValid PIT Bandへ入れず、理由コードを付ける。

例：

- `GUIDANCE_MISSING`
- `MULTIPLE_UNSTABLE`
- `PIT_SOURCE_UNVERIFIED`
- `FUNDAMENTAL_THESIS_CHANGED`
- `VALID_PIT_BAND`

### 6.3 反転確認の比較

最低限、次を比較する。

1. 資金帯到達だけでエントリー
2. 強Sの寄り引けプラス確認後
3. アンカー＋強S同期確認後
4. 2日連続陽線確認後

現物、Deep ITM Call、OTM Callを扱う場合はデータのある範囲で完全に分離する。実オプション価格がない場合、Call成績を確定値として報告しない。

## 7. Phase D：Databento／Option Flow／Forward Seed

### 7.1 既存結論を維持

既存pilotでは、2026年7月13日から17日にSOXX／SMH／MU／DRAM系でNegative GEXが観測され、「既存構造が下落を増幅した可能性」はあるが、「新規Put買いが下落原因」とは証明されていない。

この因果関係を勝手に強く言い換えない。

### 7.2 残作業

- `morita_databento_4x4_matched_pilot_v1_2`の実行証拠を確認
- 契約、原資産、時刻、出来高、IV、Delta/Gamma、GEXの対応を監査
- `contractで吹いた`外れ値を除外する場合、除外前後を両方報告
- 市場状態、Dispersion、NLRごとに結果を分ける
- Forward collectionを安全に起動できるところまで修復
- PREOPEN／寄り後90分／引け後の証拠を保存
- LRCXだけでなくAMAT／KLAC／MKSI等の入力可否を確認
- 取得不能、権限不足、endpoint未確認をそれぞれ別理由コードにする

APIキーは既存`.env`またはSecret管理を使用し、表示しない。認証情報がなければコード・dry-run・schema・テストまで進め、最後にユーザーが本当に行う必要がある最小操作だけをまとめる。

## 8. Phase E：通知・記録の実運転証拠

Webull API接続や分足取得が既に成功している場合は再接続作業を繰り返さず、通知パイプラインへ進む。

### 8.1 必須通知

- Breakout候補／S／A+判定
- 指定時刻までに該当なしの場合の`NO_SIGNAL`
- 遅れて条件成立した銘柄の再通知／起床用通知
- Short Watch／Confirmed
- Absorption Watch／Confirmed
- データ欠損、ジョブ失敗、通知失敗
- 当日の最終状態`NO_TRADE`を含む日次summary

既存設定に10:00、11:30、12:00、22:00、翌4:30等が混在している場合、推測で時刻を変更しない。リポジトリの正本と既存運用ルールを確認し、各時刻に必ず`ET`または`JST`を付け、夏時間／冬時間を安全に処理する。

### 8.2 証拠

実市場の到来待ちだけで止まらない。可能なら過去日replay、fixture、dry-runを使って以下を証明する。

- 条件成立通知が1回だけ届く
- 重複実行しても二重通知しない
- 該当なし通知が届く
- 遅延ブレイクを拾える
- データ欠損時に売買シグナルを出さずエラー通知する
- Short／Absorptionの相互排他または優先順位が守られる
- ログから入力、判定理由、時刻、出力を再現できる

GitHub Actions／scheduler／Pushover等の既存経路を尊重し、Secretを成果物に含めない。

## 9. Phase F：Unified Flow統合

### 9.1 状態機械

既存`morita_unified_flow_v3_7`またはv3.8を基礎に、各日・各判定時刻で状態を一意に返す。

最低限の状態：

- `BREAKOUT`
- `BREAKDOWN_SHORT_WATCH`
- `BREAKDOWN_SHORT_CONFIRMED`
- `ABSORPTION_WATCH`
- `ABSORPTION_CONFIRMED`
- `NO_TRADE`
- `DATA_BLOCKED`

同時成立時の優先順位を明文化する。少なくともデータ欠損時は`DATA_BLOCKED`を最優先し、売買可能通知を出さない。

### 9.2 各通知に必要な内容

- 判定時刻とタイムゾーン
- 状態
- 対象銘柄／対象群
- 使用した根拠
- 反証条件・仮説棄却帯
- 想定Exitまたは再評価時刻
- `execution_allowed`
- データ完全性
- 研究／shadow／manual-liveの区分
- 同日すでに送信した通知ID

出力は人間向け通知だけでなく、機械可読JSONまたはCSVにも保存する。

## 10. 統計・報告上の必須ルール

- PFは総利益÷総損失で計算し、損失0の場合の表記規則を明示する。
- 取引0件は`NOT_EVALUATED_NO_TRADES`とする。
- 平均だけでなく中央値、件数、勝率、MFE、MAE、最大DDを出す。
- 重複イベント、同日複数銘柄、同一銘柄連続日によるクラスタリングを明記する。
- サンプルが少ない場合、点推定を過信せずイベント別結果を併記する。
- 手数料、スリッページ、bid-askが利用可能なら反映し、無ければ未反映と明記する。
- Underlying proxy、Mid価格、実約定可能価格を混ぜない。
- 未来情報、survivorship bias、銘柄選択バイアスを監査する。
- 仮説に不利なイベントを除外しない。

## 11. テストと安全性

最低限、以下を追加または確認する。

- PIT cutoffテスト
- タイムゾーン／DSTテスト
- 15分足から30分足への集約テスト
- 欠損足・重複足・時間外混入テスト
- 同一通知のidempotencyテスト
- 状態遷移テスト
- Short 60分損切りテスト
- 月曜除外テスト
- Absorption後のShort停止テスト
- `DATA_BLOCKED`時にexecutionを許可しないテスト
- Secretがログ／artifactへ出ないことの確認

テスト失敗を削除・skipして通したことにしない。既存の失敗が今回と無関係なら、切り分けて報告する。

## 12. 完成判定

### 12.1 `MORITA_BOT_V1_MANUAL_LIVE_READY = true`の条件

次をすべて満たした場合に限りtrueとする。

1. Breakout判定・通知・記録が再現可能
2. Shortが少なくともshadow運転可能で、Watch／Confirmed／Invalidationが出る
3. Absorptionが少なくともshadow運転可能で、Short停止とBuy候補を分離できる
4. `NO_TRADE`と`DATA_BLOCKED`が正しく通知される
5. 定時ジョブまたはreplayで通知パイプラインの証拠がある
6. 人間が通知から根拠・仮説棄却・再評価時刻を確認できる
7. 自動注文は無効
8. 既知の重大なPIT leakageがない

ShortまたはAbsorptionのサンプル不足は、通知・記録のshadow readinessと収益性の実証を分けて判定する。収益性未実証なのに`PRODUCTION_PROVEN`としない。

### 12.2 判定ラベル

各系統に以下のいずれかを付ける。

- `COMPLETE_MANUAL_LIVE`
- `COMPLETE_SHADOW_ONLY`
- `PARTIAL`
- `BLOCKED_DATA`
- `BLOCKED_AUTH`
- `NOT_EVALUATED_NO_TRADES`
- `REJECTED_BY_EVIDENCE`

## 13. 必須成果物

既存の成果物命名規則に合わせ、最低限以下を作る。

1. `morita_bot_v1_remaining_work_closure_v1_report.md`
2. `morita_bot_v1_remaining_work_closure_v1_chatgpt_review_bundle.md`
3. `morita_bot_v1_remaining_work_closure_v1_status_handoff.md`
4. バックテストの機械可読結果（CSV／Parquet／JSONのうち既存規則に合うもの）
5. 変更コードとテスト
6. 本当にユーザー操作が必要な場合のみ、`morita_bot_v1_remaining_work_closure_v1_USER_ACTION_REQUIRED.md`

`USER_ACTION_REQUIRED`には、ユーザーにしかできない操作だけを書く。Codexが実行可能なコマンド、ファイル作成、設定確認、テスト、再実行をユーザーへ丸投げしない。

### Review bundleに必ず含めるもの

- 結論の1ページ要約
- 変更ファイル一覧
- 既存成果物の棚卸し表
- 3バックテストの結果
- Shortの評価statusとイベント別結果
- Absorption／PIT bandの評価status
- Option Flow／Forward Seedのstatus
- 通知・replay証拠
- テスト結果
- 未解決ブロッカー
- `MORITA_BOT_V1_MANUAL_LIVE_READY`の最終値と理由
- 次に行う作業は最大3件まで

## 14. 実行順序

以下の順序で進める。

1. リポジトリと既存成果物の棚卸し
2. データ可用性・PIT・タイムゾーン監査
3. 3優先バックテスト
4. Short正式検証
5. Absorption／PIT Guidance Multiple検証
6. Databento／Option Flow／Forward Seed確認
7. 通知・記録パイプライン修復とreplay証拠
8. Unified Flow統合
9. 全テスト
10. Report／Review bundle／Status handoff作成

途中で1系統がデータ不足になっても、他の独立作業を継続する。認証・有料データ・市場の時間経過など、Codexでは解消不能なものだけをblockerとして残す。

## 15. 最終回答の形式

作業終了時は、長い作業日誌ではなく次だけを簡潔に回答する。

1. 完了したもの
2. 主要な検証結果
3. `MORITA_BOT_V1_MANUAL_LIVE_READY`の値
4. 残ったblocker
5. Review bundleとReportのパス
6. ユーザー操作が必要かどうか

実際に実行・検証していないことを「完了」と書かない。準備完了、shadow運転可能、収益性実証、manual-live readyを区別する。

---

以上を一括で実行してください。

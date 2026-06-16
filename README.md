# 寄付強気戦略 / 30分足切替戦略 バックテスト集計ツール

TradingView Pine Script v6 戦略のバックテスト結果を、Strategy Testerのデータウィンドウからスクレイピングし、複数銘柄分をCSVに集約するためのツール群。

## 構成ファイル

| ファイル | 役割 |
|---|---|
| `30min-session-strategy.pine` | 30分足切替前後戦略（S1〜S9セッション）。Pine Script v6。 |
| `tv_backtest_scraper_30min.py` | 上記Pineのバックテスト結果（Strategy Tester + データウィンドウ）をPlaywrightでスクレイピングし、銘柄ごとにCSV出力。 |
| `tv_backtest_scraper.py` | 別ストラテジー「ズレ手法」（contrarian-gap-strategy.pine）用のスクレイパー。GU/GD/Cont集計に対応。 |
| `aggregate_csv.py` | 銘柄ごとに出力されたCSV群を1つの横持ちCSV（1行=1銘柄）に集約。 |
| `urls.txt` | 対象銘柄コードのリスト（1行1銘柄）。 |

## 全体フロー

1. TradingViewでチャートに対象のPine Script戦略を適用し、Strategy Testerパネルとデータウィンドウを表示しておく。
2. `urls.txt` に対象銘柄コードを記載する。
3. スクレイパーを実行し、銘柄ごとに `{銘柄}_{実行日}.csv` を生成する。
4. `aggregate_csv.py` を実行し、全銘柄分を1つの横持ちCSV（`summary_{実行日}.csv`）に集約する。

## セットアップ

```bash
pip install playwright --break-system-packages
playwright install chromium
```

## 実行方法

### 1. 個別銘柄のバックテスト結果を取得

30分足切替戦略の場合：

```bash
python tv_backtest_scraper_30min.py
```

ズレ手法（寄付強気戦略系）の場合：

```bash
python tv_backtest_scraper.py
```

実行すると以下の流れになる。

1. Chromiumが起動し、TradingViewのチャートページを開く。
2. 初回のみ、ターミナルの案内に従ってログイン・戦略適用・Strategy Tester表示を手動で行い、Enterキーで進める。2回目以降はプロファイルが保存されているため、確認のみでEnter。
3. `urls.txt` の銘柄を順番にチャート上で切り替え、各銘柄のバックテスト結果をスクレイピング。
4. 銘柄ごとに `{銘柄コード}_{実行日:YYYYMMDD}.csv` を出力。

### 2. 取得したCSVを集約

```bash
python aggregate_csv.py
```

`urls.txt` の銘柄順に、同じフォルダにある `{銘柄}_*.csv`（最新のもの）を読み込み、`summary_{実行日}.csv` として横持ちCSVを出力する。

## CSVフォーマット

### 個別銘柄CSV（例: `186A_20260616.csv`）

```
186A
指標,値
S1_総数,86
S1_勝,49
S1_負,36
S1_勝率,57%
S1_PnL,+1234.00
...（S2〜S9, Sumも同様の5項目）
総損益,"+14,079.00"
最大ドローダウン,"10,168.00"
勝率,56.98%
プロフィットファクター,1.339
トレード総数,86
勝ちトレード,49
負けトレード,36
```

### 集約後CSV（例: `summary_20260616.csv`）

1行目がヘッダー、2行目以降が銘柄ごとの行。列は「銘柄」+ 各セッション（S1〜S9, Sum）の5項目 × 10 + 全体統計4項目 + トレード分布3項目。

```
銘柄,S1_総数,S1_勝,S1_負,S1_勝率,S1_PnL,...,Sum_総数,...,総損益,最大ドローダウン,勝率,プロフィットファクター,トレード総数,勝ちトレード,負けトレード
186A,86,49,36,57%,...
3103,...
```

## 設定変更が必要な箇所

`tv_backtest_scraper_30min.py` / `tv_backtest_scraper.py` 内の `USER_DATA`（Playwrightセッション保存先）と `EXCHANGE`（取引所コード、デフォルト `TSE`）は環境に応じて変更する。

`WAIT_RECALC`（バックテスト再計算待機秒数）は銘柄数やPCスペックに応じて調整する。短すぎるとバックテスト結果が更新される前にスクレイピングしてしまい、データ取得に失敗することがある。

## 注意事項

- Pine Script側の `plot(..., display=display.data_window)` のタイトル文字列と、スクレイパー側のテキストマッチングのキー文字列は完全一致させる必要がある。Pine側のセッションラベルやテーブル表記を変更した場合、スクレイパーの該当部分も合わせて修正すること。
- `plot` の `title` 引数はPine Script上コンパイル時定数文字列である必要があるため、セッション数（N）を変更する場合はループでなく個別に `plot` 文を追加・削除する。
- スクレイピングはDOMのテキストノード総当たりによる位置依存マッチングのため、TradingViewのUI仕様変更（言語設定、レイアウト変更など）で抽出に失敗する可能性がある。`DEBUG_SCRAPE = True` にすると `debug_texts.txt` に全テキストノードを出力できるので、抽出失敗時はこれで構造を確認する。

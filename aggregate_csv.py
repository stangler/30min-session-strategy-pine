# aggregate_csv.py
# tv_backtest_scraper.py が出力した {symbol}_{YYYYMMDD}.csv 群を
# 1行=1銘柄、列=指標 の横持ちCSVに集約する。

import csv
import re
from datetime import datetime
from pathlib import Path

# ========== 設定 ==========
INPUT_DIR   = Path(".")          # 個別CSVが置かれているフォルダ
URLS_FILE   = Path("urls.txt")   # 銘柄リスト（順序維持に使用）
OUTPUT_FILE = Path(f"summary_{datetime.now():%Y%m%d}.csv")

# 出力列の順序（個別CSVの「指標」名と一致させる）
_SESSIONS = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "Sum"]
COLUMNS = []
for _s in _SESSIONS:
    COLUMNS += [f"{_s}_総数", f"{_s}_勝", f"{_s}_負", f"{_s}_勝率", f"{_s}_PnL"]
COLUMNS += [
    "総損益", "最大ドローダウン", "勝率", "プロフィットファクター",
    "トレード総数", "勝ちトレード", "負けトレード",
]
# ==========================


def load_symbols() -> list[str]:
    lines = URLS_FILE.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def find_csv_for_symbol(symbol: str) -> Path | None:
    """{symbol}_YYYYMMDD.csv にマッチする最新ファイルを探す"""
    safe = re.sub(r'[\\/:*?"<>|]', "_", symbol)
    candidates = sorted(INPUT_DIR.glob(f"{safe}_*.csv"))
    return candidates[-1] if candidates else None


def read_indicator_csv(path: Path) -> dict:
    """1銘柄分のCSV（1行目=銘柄名, 2行目=ヘッダー, 以降=指標,値）を読む"""
    data = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = list(csv.reader(f))
    # reader[0] = [symbol], reader[1] = ["指標","値"], reader[2:] = データ
    for row in reader[2:]:
        if len(row) >= 2:
            key, val = row[0].strip(), row[1].strip()
            data[key] = val
    return data


def main():
    symbols = load_symbols()
    rows = []
    missing = []

    for symbol in symbols:
        csv_path = find_csv_for_symbol(symbol)
        if csv_path is None:
            print(f"  ✗ {symbol}: CSVが見つかりません")
            missing.append(symbol)
            continue

        data = read_indicator_csv(csv_path)
        row = {"銘柄": symbol}
        for col in COLUMNS:
            row[col] = data.get(col, "")
        rows.append(row)
        print(f"  ✓ {symbol} ← {csv_path.name}")

    if not rows:
        print("集約対象のデータがありません。")
        return

    fieldnames = ["銘柄"] + COLUMNS
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n完了: {len(rows)} 銘柄 → {OUTPUT_FILE}")
    if missing:
        print(f"未取得: {missing}")


if __name__ == "__main__":
    main()

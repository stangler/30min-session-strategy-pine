# tv_backtest_scraper_30min.py
# 「30分足切替前後戦略」(S1〜S10セッション) のStrategy Tester結果をスクレイピングする版

import asyncio
import csv
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# ========== 設定 ==========
URLS_FILE    = Path("urls.csv")
OUTPUT_DIR   = Path("csv")
CHART_URL    = "https://jp.tradingview.com/chart/"
USER_DATA    = r"C:\Temp\tv-profile-pw"   # セッション保存先
WAIT_RECALC  = 10      # バックテスト再計算待機（秒）
WAIT_SEARCH  = 1.5    # 検索ダイアログ安定待機（秒）
EXCHANGE     = "TSE"
SESSIONS     = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "Sum"]
# ==========================

DEBUG_SCRAPE = False  # Trueにすると全テキストノードをdebug_texts.txtに出力


def load_symbols() -> list[str]:
    lines = URLS_FILE.read_text(encoding="utf-8").splitlines()
    symbols = []
    for l in lines:
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        cols = l.split("\t")
        code = cols[1].strip() if len(cols) >= 2 else cols[0].strip()
        if code:
            symbols.append(code)
    return symbols


def save_csv(data: list, symbol: str):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]', "_", symbol)
    fn = OUTPUT_DIR / f"{safe}_{datetime.now():%Y%m%d}.csv"
    with open(fn, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([symbol])
        writer.writerow(["指標", "値"])
        writer.writerows(data)
    print(f"  ✓ 保存 → {fn}")


async def switch_symbol(page, symbol: str):
    await page.keyboard.press("Space")
    await page.wait_for_timeout(int(WAIT_SEARCH * 1000))
    query = f"{EXCHANGE}:{symbol}"
    await page.keyboard.type(query, delay=80)
    await page.wait_for_timeout(1200)
    await page.keyboard.press("ArrowDown")
    await page.wait_for_timeout(300)
    await page.keyboard.press("Enter")


async def wait_for_chart_update(page, symbol: str):
    try:
        await page.wait_for_function(
            f"document.title.includes('{symbol}')",
            timeout=12000
        )
    except Exception:
        print(f"  ⚠ タイトル変化タイムアウト → sleep継続")
    await page.wait_for_timeout(int(WAIT_RECALC * 1000))


async def scrape_backtest(page) -> list:
    """
    DOMテキスト構造:
      主要統計: 総損益→+NNN, 最大ドローダウン→NNN, 勝ちトレード→NN.NN%(勝率), プロフィットファクター→N.NNN
      トレード分布: "NN" → "トレード総数" → "勝ち" → "NNトレード" → "負け" → "NNトレード"
      データウィンドウ: "S1 総数"→値, "S1 勝"→値, "S1 負"→値, "S1 勝率%"→値, "S1 PnL"→値 ...
                       "Sum 総数"〜"Sum PnL" も同様
    """
    texts = await page.evaluate("""
    () => {
        const out = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node;
        while (node = walker.nextNode()) {
            const t = node.textContent.trim();
            if (t) out.push(t);
        }
        return out;
    }
    """)

    if DEBUG_SCRAPE:
        with open("debug_texts.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(texts))
        print(f"  [DEBUG] テキストノード {len(texts)}件 → debug_texts.txt")

    def is_num(s):
        c = s.replace(",", "").replace("\u202a", "").replace("\u202c", "").strip()
        return bool(re.match(r'^[+\-\u2212]?\d+\.?\d*%?$', c))

    def is_int(s):
        c = s.replace(",", "").replace("\u202a", "").replace("\u202c", "").strip()
        return bool(re.match(r'^[+\-\u2212]?\d+$', c))

    def next_num(i, ahead=4):
        for j in range(i + 1, min(i + 1 + ahead, len(texts))):
            if is_num(texts[j]):
                return texts[j]
        return None

    result = {}

    for i, t in enumerate(texts):
        # --- 主要統計ブロック ---
        if t == "総損益" and "総損益" not in result:
            v = next_num(i)
            if v: result["総損益"] = v

        elif t == "最大ドローダウン" and "最大ドローダウン" not in result:
            v = next_num(i)
            if v: result["最大ドローダウン"] = v

        elif t == "勝ちトレード" and "勝率" not in result:
            v = next_num(i)
            if v: result["勝率"] = v

        elif t == "プロフィットファクター" and "プロフィットファクター" not in result:
            v = next_num(i)
            if v: result["プロフィットファクター"] = v

        # --- トレード分布ブロック ---
        elif t == "トレード総数" and "トレード総数" not in result:
            if i > 0 and is_int(texts[i - 1]):
                result["トレード総数"] = texts[i - 1]

        elif t == "勝ち" and "勝ちトレード" not in result:
            if i + 1 < len(texts):
                m = re.match(r'^(\d+)トレード', texts[i + 1])
                if m: result["勝ちトレード"] = m.group(1)

        elif t == "負け" and "負けトレード" not in result:
            if i + 1 < len(texts):
                m = re.match(r'^(\d+)トレード', texts[i + 1])
                if m: result["負けトレード"] = m.group(1)

        # --- データウィンドウ: セッション別（S1〜S10, Sum） ---
        else:
            for sess in SESSIONS:
                key_total = f"{sess} 総数"
                key_win   = f"{sess} 勝"
                key_lose  = f"{sess} 負"
                key_wr    = f"{sess} 勝率%"
                key_pnl   = f"{sess} PnL"

                if t == key_total and f"{sess}_総数" not in result:
                    if i + 1 < len(texts): result[f"{sess}_総数"] = texts[i + 1].replace(".0", "")
                elif t == key_win and f"{sess}_勝" not in result:
                    if i + 1 < len(texts): result[f"{sess}_勝"] = texts[i + 1].replace(".0", "")
                elif t == key_lose and f"{sess}_負" not in result:
                    if i + 1 < len(texts): result[f"{sess}_負"] = texts[i + 1].replace(".0", "")
                elif t == key_wr and f"{sess}_勝率" not in result:
                    if i + 1 < len(texts): result[f"{sess}_勝率"] = texts[i + 1].replace(".0", "") + "%"
                elif t == key_pnl and f"{sess}_PnL" not in result:
                    if i + 1 < len(texts): result[f"{sess}_PnL"] = texts[i + 1]

    if DEBUG_SCRAPE:
        print(f"  [DEBUG] 抽出結果: {result}")

    return list(result.items())


async def main():
    symbols = load_symbols()
    print(f"対象 {len(symbols)} 銘柄: {symbols}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA,
            headless=False,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        await page.goto(CHART_URL)

        print("=" * 50)
        print("【初回のみ】ログイン + チャート設定が必要")
        print("2回目以降はそのままEnterでOK")
        print("  1. TradingViewにログイン")
        print("  2. 「30分足切替前後戦略」適用済みチャートを開く")
        print("  3. Strategy Testerパネルを表示")
        print("  4. データウィンドウでS1〜S10, Sumのplotが見える状態にする")
        print("=" * 50)
        input("準備完了 → Enter: ")

        success, failed = [], []

        for i, symbol in enumerate(symbols, 1):
            print(f"\n[{i}/{len(symbols)}] {symbol}")
            try:
                await switch_symbol(page, symbol)
                await wait_for_chart_update(page, symbol)

                data = await scrape_backtest(page)
                if data:
                    save_csv(data, symbol)
                    success.append(symbol)
                else:
                    print(f"  ✗ データ取得失敗")
                    failed.append(symbol)

            except Exception as e:
                print(f"  ✗ エラー: {e}")
                failed.append(symbol)

        print(f"\n{'='*50}")
        print(f"完了: 成功 {len(success)} / 失敗 {len(failed)}")
        if failed:
            print(f"失敗銘柄: {failed}")

        input("ブラウザを閉じる → Enter: ")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

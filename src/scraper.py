import requests
from bs4 import BeautifulSoup
import csv
import time
import re
import sys
import logging

# --- ログ設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ベースURL
LIST_URL = "https://wikiwiki.jp/llll_wiki/%E3%82%AB%E3%83%BC%E3%83%89%E4%B8%80%E8%A6%A7"

# 手順書 4-9 用のマッピング定義
TIMING_MAP = {
    "ライブ開始時": "live_start",
    "ライブ終了時": "live_end",
    "フィーバー開始時": "fever_start",
    "フィーバー終了時": "fever_end"
}

def get_soup(url):
    """URLからBeautifulSoupオブジェクトを生成"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')
    except Exception as e:
        logger.error(f"Failed to fetch URL: {url} | Error: {e}")
        return None

def clean_text(text):
    """テキストの余分な空白を除去"""
    if not text:
        return ""
    # 改行やタブをスペースに変換してstrip
    return re.sub(r'\s+', ' ', text).strip()

def get_table_by_header(soup, header_keywords):
    """
    指定したキーワードを含むヘッダーを持つテーブルを探す
    """
    for tbl in soup.find_all('table'):
        # ヘッダー行を取得 (theadまたは最初のtr)
        headers = []
        thead = tbl.find('thead')
        if thead:
            headers = [clean_text(th.get_text()) for th in thead.find_all(['th', 'td'])]
        else:
            first_row = tbl.find('tr')
            if first_row:
                headers = [clean_text(th.get_text()) for th in first_row.find_all(['th', 'td'])]
        
        # キーワードが全て含まれているか確認
        if all(k in headers for k in header_keywords):
            return tbl, headers
    return None, []

def parse_card_detail(card_url, basic_info):
    """詳細ページ解析"""
    soup = get_soup(card_url)
    if not soup:
        return None

    data = {
        "smile": "", "pure": "", "cool": "", "mental": "", 
        "cs_timing": "", "cs_text": "", 
        "skill_text": "", "skill_ap": "", 
        "center_effect": ""
    }

    try:
        # --- 2-1. ステータス表 ---
        # "スマイル", "ピュア" などが含まれる表を探す
        status_table, _ = get_table_by_header(soup, ["ステータス"])
        if not status_table:
             # ヘッダーにステータスがない場合、左端列にあるパターンを考慮して単純に探す
             for tbl in soup.find_all('table'):
                 if "スマイル" in tbl.get_text():
                     status_table = tbl
                     break

        if status_table:
            rows = status_table.find_all('tr')
            for row in rows:
                cols = row.find_all(['th', 'td'])
                row_text = [clean_text(c.get_text()) for c in cols]
                # "スマイル"などが含まれる行の、最後の値を採用
                if any("スマイル" in t for t in row_text): data["smile"] = row_text[-1]
                elif any("ピュア" in t for t in row_text): data["pure"] = row_text[-1]
                elif any("クール" in t for t in row_text): data["cool"] = row_text[-1]
                elif any("メンタル" in t for t in row_text): data["mental"] = row_text[-1]

        # --- 2-2 & 2-3. センタースキル ---
        # キーワード検索でセクションを特定し、その直後のテーブルを取得
        cs_header = soup.find(lambda tag: tag.name in ['h3', 'h4'] and "センタースキル" in tag.get_text())
        cs_table = None
        if cs_header:
            # 次の要素へ進みながらテーブルを探す
            curr = cs_header.next_element
            for _ in range(20):
                if not curr: break
                if curr.name == 'table':
                    cs_table = curr
                    break
                curr = curr.next_element

        if cs_table:
            rows = cs_table.find_all('tr')
            
            # ヘッダー列の位置特定
            header_row = rows[0]
            header_cols = [clean_text(c.get_text()) for c in header_row.find_all(['th', 'td'])]
            
            idx_cond = -1
            idx_effect = -1
            
            for i, txt in enumerate(header_cols):
                if "発動条件" in txt: idx_cond = i
                if "効果" in txt: idx_effect = i

            # 発動条件の取得 (通常 rowspan されているため、1行目(Lv1)から取得する)
            if idx_cond != -1 and len(rows) > 1:
                # rows[1] が Lv1 の行
                cols = rows[1].find_all(['td', 'th'])
                if len(cols) > idx_cond:
                    raw_val = clean_text(cols[idx_cond].get_text())
                    data["cs_timing"] = TIMING_MAP.get(raw_val, raw_val)

            # Lv14 効果の取得
            # Lv14行を探す。rowspanの影響で列数が減っているため、末尾のセル(効果)を取得する
            for row in rows[1:]:
                cols = row.find_all(['td', 'th'])
                if not cols: continue
                # 最初のカラムが "14" かどうか
                if clean_text(cols[0].get_text()) == "14":
                    # Lv14行は [Lv, Effect] の2列になっている可能性が高い (条件がrowspanのため)
                    # とにかく最後の列が効果テキスト
                    eff = clean_text(cols[-1].get_text())
                    if eff == "○○○○○○": eff = ""
                    data["cs_text"] = eff
                    break

        # --- 2-4 & 2-5. スキル ---
        skill_header = soup.find(lambda tag: tag.name in ['h3', 'h4'] and "スキル" in tag.get_text() and "センタースキル" not in tag.get_text())
        skill_table = None
        if skill_header:
            curr = skill_header.next_element
            for _ in range(20):
                if not curr: break
                if curr.name == 'table':
                    skill_table = curr
                    break
                curr = curr.next_element

        if skill_table:
            rows = skill_table.find_all('tr')
            header_row = rows[0]
            header_cols = [clean_text(c.get_text()) for c in header_row.find_all(['th', 'td'])]
            
            idx_ap = -1
            for i, txt in enumerate(header_cols):
                if "AP" in txt: idx_ap = i # "スキルAP" または "消費AP"

            # APの取得 (rowspan されているため、1行目(Lv1)から取得)
            if idx_ap != -1 and len(rows) > 1:
                cols = rows[1].find_all(['td', 'th'])
                if len(cols) > idx_ap:
                    ap_val = clean_text(cols[idx_ap].get_text())
                    if "→" in ap_val:
                        ap_val = ap_val.split("→")[-1]
                    data["skill_ap"] = ap_val

            # Lv14 効果の取得
            for row in rows[1:]:
                cols = row.find_all(['td', 'th'])
                if not cols: continue
                if clean_text(cols[0].get_text()) == "14":
                    data["skill_text"] = clean_text(cols[-1].get_text())
                    break

        # --- 2-6. センター特性 ---
        # "センター特性" ヘッダーを探し、次の ul を取得
        center_char_header = soup.find(lambda tag: tag.name in ['h3', 'h4'] and "センター特性" in tag.get_text())
        if center_char_header:
            curr = center_char_header.next_sibling
            found_ul = False
            for _ in range(10): # 兄弟要素を探索
                if not curr: break
                if curr.name == 'ul':
                    items = [clean_text(li.get_text()) for li in curr.find_all('li')]
                    data["center_effect"] = " ".join(items)
                    found_ul = True
                    break
                curr = curr.next_sibling
                
    except Exception as e:
        logger.warning(f"Error parsing details for {basic_info['card_name']}: {e}")

    return data

def main():
    logger.info("Starting Scraper Job (Fixed for Rowspan)...")
    
    soup = get_soup(LIST_URL)
    if not soup:
        logger.critical("Failed to get list page.")
        return

    # 一覧テーブルの特定
    target_table = None
    col_map = {}
    
    # "カード名"を含むテーブルを探す
    for tbl in soup.find_all('table'):
        rows = tbl.find_all('tr')
        if not rows: continue
        headers = [clean_text(c.get_text()) for c in rows[0].find_all(['th', 'td'])]
        if "カード名" in headers and "キャラクター" in headers:
            target_table = tbl
            col_map = {h: i for i, h in enumerate(headers)}
            break
            
    if not target_table:
        logger.critical("Could not find the card list table.")
        return

    rows = target_table.find_all('tr')[1:]
    logger.info(f"Found {len(rows)} rows.")

    results = []
    
    for i, row in enumerate(rows):
        cols = row.find_all(['td', 'th'])
        if len(cols) <= max(col_map.values()): continue
            
        try:
            char_name = clean_text(cols[col_map["キャラクター"]].get_text())
            rarity = clean_text(cols[col_map["レアリティ"]].get_text())
            card_col = cols[col_map["カード名"]]
            card_name_text = clean_text(card_col.get_text())
            link_tag = card_col.find('a')
            
            if not link_tag: continue
            card_url = "https://wikiwiki.jp" + link_tag.get('href')
            
            logger.info(f"[{i+1}/{len(rows)}] Processing: {card_name_text}")
            time.sleep(1)
            
            details = parse_card_detail(card_url, {"card_name": card_name_text})
            
            if details:
                row_data = {
                    "character": char_name,
                    "card_name": card_name_text,
                    "empty": "",
                    "smile": details["smile"],
                    "pure": details["pure"],
                    "cool": details["cool"],
                    "mental": details["mental"],
                    "rarity": rarity,
                    "cs_timing": details["cs_timing"],
                    "cs_text": details["cs_text"],
                    "skill_text": details["skill_text"],
                    "skill_ap": details["skill_ap"],
                    "center_effect": details["center_effect"]
                }
                results.append(row_data)
        
        except Exception as e:
            logger.error(f"Error processing row {i}: {e}")
            continue

    output_file = "output.tsv"
    fieldnames = [
        "character", "card_name", "empty", 
        "smile", "pure", "cool", "mental", 
        "rarity", "cs_timing", "cs_text", 
        "skill_text", "skill_ap", "center_effect"
    ]
    
    try:
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
            # writer.writeheader() 
            writer.writerows(results)
        logger.info(f"Done. Saved to {output_file}. Records: {len(results)}")
    except IOError as e:
        logger.error(f"Write error: {e}")

if __name__ == "__main__":
    main()

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
    """URLからBeautifulSoupオブジェクトを生成 (User-Agent偽装付き)"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')
    except Exception as e:
        logger.error(f"Failed to fetch URL: {url} | Error: {e}")
        return None

def clean_text(text):
    """テキストの余分な空白を除去"""
    if not text:
        return ""
    return text.strip()

def find_table_after_text(soup, search_text, look_ahead=20):
    """指定テキストを含む要素を探し、その直後にあるtableを探す"""
    elements = soup.find_all(string=re.compile(search_text))
    for element in elements:
        parent = element.parent
        next_node = parent
        for _ in range(look_ahead): 
            if next_node:
                next_node = next_node.find_next()
                if next_node and next_node.name == 'table':
                    return next_node
    return None

def parse_card_detail(card_url, basic_info):
    """
    手順書 2. 個別のカードページを解析する
    """
    soup = get_soup(card_url)
    if not soup:
        return None

    data = {
        "smile": "", "pure": "", "cool": "", "mental": "", # 2-1
        "cs_timing": "",       # 2-3 -> 4-9
        "cs_text": "",         # 2-2 -> 4-10
        "skill_text": "",      # 2-4 -> 4-11
        "skill_ap": "",        # 2-5 -> 4-12
        "center_effect": ""    # 2-6 -> 4-13
    }

    try:
        # --- 2-1. ステータス表の解析 ---
        # 「ステータス」という文字の後の表、またはヘッダーに「スマイル」等を含む表を探す
        status_table = find_table_after_text(soup, "ステータス")
        if not status_table:
            # 見つからない場合、thにスマイルを含む表をページから探す
            for tbl in soup.find_all('table'):
                if tbl.find('th', string=re.compile("スマイル")):
                    status_table = tbl
                    break
        
        if status_table:
            # 行ごとに解析し、右端の値を取得する
            rows = status_table.find_all('tr')
            for row in rows:
                cols = row.find_all(['th', 'td'])
                header_text = clean_text(cols[0].get_text())
                
                # 手順 2-1: 右端の数値を抽出
                if "スマイル" in header_text:
                    data["smile"] = clean_text(cols[-1].get_text())
                elif "ピュア" in header_text:
                    data["pure"] = clean_text(cols[-1].get_text())
                elif "クール" in header_text:
                    data["cool"] = clean_text(cols[-1].get_text())
                elif "メンタル" in header_text:
                    data["mental"] = clean_text(cols[-1].get_text())

        # --- 2-2 & 2-3. センタースキル ---
        cs_table = find_table_after_text(soup, "センタースキル")
        if cs_table:
            rows = cs_table.find_all('tr')
            header_map = {}
            if rows:
                headers = rows[0].find_all(['th', 'td'])
                for i, h in enumerate(headers):
                    header_map[clean_text(h.get_text())] = i
            
            # 2-3. 発動条件 (タイミング)
            # テーブル内、または直前のテキストから探す指示だが、通常表内にある
            condition_text = ""
            for row in rows:
                cols = row.find_all(['th', 'td'])
                for i, col in enumerate(cols):
                    if "発動条件" in clean_text(col.get_text()):
                         if i + 1 < len(cols):
                            condition_text = clean_text(cols[i+1].get_text())
                            break
            
            # 手順 4-9 マッピング
            data["cs_timing"] = TIMING_MAP.get(condition_text, condition_text) # マッチしなければ原文

            # 2-2. Lv14 効果
            if "Lv" in header_map and "効果" in header_map:
                for row in rows[1:]:
                    cols = row.find_all(['th', 'td'])
                    if len(cols) > max(header_map.values()):
                        lv_val = clean_text(cols[header_map["Lv"]].get_text())
                        if lv_val == "14":
                            eff = clean_text(cols[header_map["効果"]].get_text())
                            if eff == "○○○○○○": eff = ""
                            data["cs_text"] = eff
                            break

        # --- 2-4 & 2-5. スキル ---
        skill_table = find_table_after_text(soup, "スキル:")
        if not skill_table: skill_table = find_table_after_text(soup, "スキル")
        
        if skill_table:
            rows = skill_table.find_all('tr')
            header_map = {}
            if rows:
                headers = rows[0].find_all(['th', 'td'])
                for i, h in enumerate(headers):
                    header_map[clean_text(h.get_text())] = i
            
            # 2-4. Lv14 効果
            if "Lv" in header_map and "効果" in header_map:
                for row in rows[1:]:
                    cols = row.find_all(['th', 'td'])
                    if len(cols) > max(header_map.values()):
                        if clean_text(cols[header_map["Lv"]].get_text()) == "14":
                            data["skill_text"] = clean_text(cols[header_map["効果"]].get_text())
                            break
            
            # 2-5. スキルAP (A→B 対応)
            ap_text = ""
            # まず表全体から探す
            for row in rows:
                cols = row.find_all(['th', 'td'])
                for i, col in enumerate(cols):
                    if "スキルAP" in clean_text(col.get_text()):
                        if i + 1 < len(cols):
                            ap_text = clean_text(cols[i+1].get_text())
                        break
            # ヘッダーにある場合 (Lv14の行)
            if not ap_text and "スキルAP" in header_map:
                 for row in rows[1:]:
                    cols = row.find_all(['th', 'td'])
                    if len(cols) > max(header_map.values()):
                        if clean_text(cols[header_map["Lv"]].get_text()) == "14":
                            ap_text = clean_text(cols[header_map["スキルAP"]].get_text())
                            break
            
            if "→" in ap_text:
                ap_text = ap_text.split("→")[-1]
            data["skill_ap"] = clean_text(ap_text)

        # --- 2-6. センター特性 ---
        # 「センター特性:」の後の ul/li
        center_char_elements = soup.find_all(string=re.compile("センター特性"))
        for element in center_char_elements:
            parent = element.parent
            next_node = parent
            for _ in range(10):
                if next_node:
                    next_node = next_node.find_next()
                    if next_node and next_node.name == 'ul':
                        items = [clean_text(li.get_text()) for li in next_node.find_all('li')]
                        data["center_effect"] = " ".join(items) # 改行コード等を除くためjoin
                        break
            if data["center_effect"]: break

    except Exception as e:
        logger.warning(f"Error parsing details for {basic_info['card_name']}: {e}")

    return data

def main():
    logger.info("Starting Scraper Job (Updated Procedure)...")
    
    # 1. 一覧ページの取得
    soup = get_soup(LIST_URL)
    if not soup:
        logger.critical("Failed to get list page.")
        return

    # 手順 1. テーブルから情報を抽出
    cards = []
    
    # Wikiのメインコンテンツ内のテーブルを探す
    # 通常、一番大きなテーブルか、「カード名」ヘッダーを持つテーブル
    target_table = None
    for tbl in soup.find_all('table'):
        headers = [clean_text(th.get_text()) for th in tbl.find_all(['th'])]
        if "カード名" in headers and "キャラクター" in headers:
            target_table = tbl
            break
            
    if not target_table:
        logger.critical("Could not find the card list table.")
        return

    # ヘッダー解析
    headers = target_table.find_all('tr')[0].find_all(['th', 'td'])
    col_map = {clean_text(h.get_text()): i for i, h in enumerate(headers)}
    
    if not all(k in col_map for k in ["キャラクター", "レアリティ", "カード名"]):
        logger.critical("Required columns missing in table.")
        return

    rows = target_table.find_all('tr')[1:] # ヘッダー除外
    logger.info(f"Found {len(rows)} rows in the list.")

    results = []
    
    for i, row in enumerate(rows):
        cols = row.find_all(['td', 'th'])
        if len(cols) <= max(col_map.values()):
            continue
            
        # 1-1, 1-2, 1-3 取得
        char_name = clean_text(cols[col_map["キャラクター"]].get_text())
        rarity = clean_text(cols[col_map["レアリティ"]].get_text())
        
        # カード名はリンクになっている
        card_col = cols[col_map["カード名"]]
        card_name_text = clean_text(card_col.get_text())
        link_tag = card_col.find('a')
        
        if not link_tag:
            continue
            
        card_url = "https://wikiwiki.jp" + link_tag.get('href')
        
        logger.info(f"[{i+1}/{len(rows)}] Processing: {card_name_text} ({char_name})")
        time.sleep(1) # Wait
        
        # 2. 詳細取得
        basic_info = {"card_name": card_name_text}
        details = parse_card_detail(card_url, basic_info)
        
        if details:
            # 4. データ結合 (出力順序定義)
            # 4-1. キャラクター
            # 4-2. カード名称
            # 4-3. 空白
            # 4-4. smile
            # 4-5. pure
            # 4-6. cool
            # 4-7. mental
            # 4-8. レアリティ
            # 4-9. センタースキル発動タイミング
            # 4-10. センタースキルテキスト
            # 4-11. スキルテキスト
            # 4-12. 必要AP
            # 4-13. センター効果テキスト
            
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

    # TSV出力
    output_file = "output.tsv"
    # 手順4の順番通り
    fieldnames = [
        "character", "card_name", "empty", 
        "smile", "pure", "cool", "mental", 
        "rarity", "cs_timing", "cs_text", 
        "skill_text", "skill_ap", "center_effect"
    ]
    
    try:
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
            # ヘッダーは出力しない指示がなければ出力するが、通常TSVデータとしてはヘッダーありが親切
            # 手順書に「ヘッダーを含める」とは明記ないが、4で「tsvに含むデータは、順番に、以下の通りとする」
            # とあるため、ヘッダーレスが安全かもしれないが、デバッグ用にヘッダーをつける。
            # 必要なければ writer.writeheader() をコメントアウトしてください。
            # writer.writeheader() 
            writer.writerows(results)
            
        logger.info(f"Scraping completed. Saved to {output_file}. Records: {len(results)}")
        
    except IOError as e:
        logger.error(f"Failed to write output: {e}")

if __name__ == "__main__":
    main()

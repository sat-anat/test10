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
BASE_URL = "https://wikiwiki.jp/llll_wiki/"
LIST_URL = "https://wikiwiki.jp/llll_wiki/%E3%82%AB%E3%83%BC%E3%83%89%E4%B8%80%E8%A6%A7"

def get_soup(url):
    """URLからBeautifulSoupオブジェクトを生成 (User-Agent偽装付き)"""
    # 一般的なブラウザ（Chrome on Windows）のふりをするヘッダー
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
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

def find_table_after_text(soup, search_text):
    """指定テキストを含む要素を探し、その直後にあるtableを探す"""
    elements = soup.find_all(string=re.compile(search_text))
    for element in elements:
        parent = element.parent
        next_node = parent
        # 親要素から辿って次のtableを探す（探索範囲を広めに設定）
        for _ in range(20): 
            if next_node:
                next_node = next_node.find_next()
                if next_node and next_node.name == 'table':
                    return next_node
    return None

def parse_card_page(card_url, card_name):
    """
    手順書 2. 個別のカードページを解析する
    """
    soup = get_soup(card_url)
    if not soup:
        return None

    data = {
        "center_skill_effect": "",      # 2-1
        "center_skill_condition": "",   # 2-2
        "skill_effect": "",             # 2-3
        "skill_ap": "",                 # 2-4
        "center_characteristic": ""     # 2-5
    }

    try:
        # --- 2-1. 「センタースキル」後の表 ---
        cs_table = find_table_after_text(soup, "センタースキル")
        if cs_table:
            rows = cs_table.find_all('tr')
            header_map = {}
            if rows:
                headers = rows[0].find_all(['th', 'td'])
                for i, h in enumerate(headers):
                    header_map[clean_text(h.get_text())] = i
            
            # Lv 14 の行を探す
            if "Lv" in header_map and "効果" in header_map:
                found_lv14 = False
                for row in rows[1:]:
                    cols = row.find_all(['th', 'td'])
                    if len(cols) > max(header_map.values()):
                        lv_val = clean_text(cols[header_map["Lv"]].get_text())
                        if lv_val == "14":
                            effect = clean_text(cols[header_map["効果"]].get_text())
                            # 2-1-1. 空または"○○○○○○"の処理
                            if effect == "○○○○○○":
                                effect = ""
                            data["center_skill_effect"] = effect
                            found_lv14 = True
                            break
                if not found_lv14:
                    logger.debug(f"[{card_name}] Center Skill Lv14 row not found.")
        else:
            logger.debug(f"[{card_name}] 'Center Skill' table not found.")

        # --- 2-2. 「センタースキル:」後の表 (発動条件) ---
        if cs_table:
            rows = cs_table.find_all('tr')
            for row in rows:
                cols = row.find_all(['th', 'td'])
                for i, col in enumerate(cols):
                    if "発動条件" in clean_text(col.get_text()):
                        if i + 1 < len(cols):
                            data["center_skill_condition"] = clean_text(cols[i+1].get_text())
                        break

        # --- 2-3. 「スキル:」の文字の後に配置される表 (Lv14効果) ---
        skill_table = find_table_after_text(soup, "スキル:")
        if not skill_table:
            skill_table = find_table_after_text(soup, "スキル")

        if skill_table:
            rows = skill_table.find_all('tr')
            header_map = {}
            if rows:
                headers = rows[0].find_all(['th', 'td'])
                for i, h in enumerate(headers):
                    header_map[clean_text(h.get_text())] = i
            
            if "Lv" in header_map and "効果" in header_map:
                for row in rows[1:]:
                    cols = row.find_all(['th', 'td'])
                    if len(cols) > max(header_map.values()):
                        lv_val = clean_text(cols[header_map["Lv"]].get_text())
                        if lv_val == "14":
                            data["skill_effect"] = clean_text(cols[header_map["効果"]].get_text())
                            break
            
            # --- 2-4. スキルAPの取得 ---
            ap_text = ""
            for row in rows:
                cols = row.find_all(['th', 'td'])
                for i, col in enumerate(cols):
                    if "スキルAP" in clean_text(col.get_text()):
                        if i + 1 < len(cols):
                            ap_text = clean_text(cols[i+1].get_text())
                        break
            
            if not ap_text and "スキルAP" in header_map:
                 for row in rows[1:]:
                    cols = row.find_all(['th', 'td'])
                    if len(cols) > max(header_map.values()):
                        if clean_text(cols[header_map["Lv"]].get_text()) == "14":
                            ap_text = clean_text(cols[header_map["スキルAP"]].get_text())
                            break

            # 2-4-1. "A→B" の形式処理
            if "→" in ap_text:
                ap_text = ap_text.split("→")[-1]
            
            data["skill_ap"] = clean_text(ap_text)
        else:
             logger.debug(f"[{card_name}] 'Skill' table not found.")

        # --- 2-5. 「センター特性:」の後の箇条書き ---
        center_char_elements = soup.find_all(string=re.compile("センター特性"))
        for element in center_char_elements:
            parent = element.parent
            next_node = parent
            found_ul = False
            for _ in range(10):
                if next_node:
                    next_node = next_node.find_next()
                    if next_node and next_node.name == 'ul':
                        items = [clean_text(li.get_text()) for li in next_node.find_all('li')]
                        data["center_characteristic"] = " / ".join(items)
                        found_ul = True
                        break
            if found_ul:
                break
                
    except Exception as e:
        logger.warning(f"[{card_name}] Error parsing details: {e}")

    return data

def main():
    logger.info("Starting Scraper Job...")
    logger.info(f"Target List URL: {LIST_URL}")

    # 1. カード一覧の取得
    soup = get_soup(LIST_URL)
    if not soup:
        logger.critical("Failed to retrieve the card list page. Exiting.")
        return

    # リンク収集
    body = soup.find(id="body") or soup
    links = {} 
    
    for a in body.find_all('a'):
        href = a.get('href')
        text = clean_text(a.get_text())
        
        # リンクフィルタリング
        if href and not href.startswith('http') and len(text) > 1:
            if not href.startswith('#') and 'plugin' not in href:
                full_url = "https://wikiwiki.jp" + href
                links[full_url] = text

    total_links = len(links)
    logger.info(f"Found {total_links} potential card links.")

    results = []
    
    for i, (url, name) in enumerate(links.items(), 1):
        logger.info(f"[{i:3d}/{total_links}] Processing: {name}")
        
        time.sleep(1) # Wait 1 sec
        
        try:
            card_data = parse_card_page(url, name)
            
            if card_data:
                # データ有無の簡易チェック
                if not card_data["skill_effect"] and not card_data["center_skill_effect"]:
                    logger.warning(f"  -> No skill data found for {name}")
                
                row = {
                    "name": name,
                    "url": url,
                    **card_data
                }
                results.append(row)
        except Exception as e:
            logger.error(f"  -> Unexpected error processing {name}: {e}")
            continue

    # 4. TSV出力
    output_file = "output.tsv"
    fieldnames = [
        "name", "url", 
        "center_skill_effect", "center_skill_condition", 
        "skill_effect", "skill_ap", "center_characteristic"
    ]
    
    try:
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
            writer.writeheader()
            writer.writerows(results)
        
        logger.info(f"Scraping completed successfully.")
        logger.info(f"Data saved to: {output_file} (Total records: {len(results)})")
        
    except IOError as e:
        logger.error(f"Failed to write output file: {e}")

if __name__ == "__main__":
    main()

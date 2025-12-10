import requests
from bs4 import BeautifulSoup
import csv
import time
import re
import sys

# ベースURL
BASE_URL = "https://wikiwiki.jp/llll_wiki/"
LIST_URL = "https://wikiwiki.jp/llll_wiki/%E3%82%AB%E3%83%BC%E3%83%89%E4%B8%80%E8%A6%A7"

def get_soup(url):
    """URLからBeautifulSoupオブジェクトを生成"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

def clean_text(text):
    """テキストの余分な空白を除去"""
    if not text:
        return ""
    return text.strip()

def parse_card_page(card_url):
    """
    手順書 2. 個別のカードページを解析する
    """
    soup = get_soup(card_url)
    if not soup:
        return None

    # 手順 2: "#SIShow"以下のデータを取得
    # WikiWikiの構造上、#SIShowはアンカーIDであることが多いため、
    # そのIDを持つ要素、あるいはページ全体から検索します。
    # ここではページ全体から特定のヘッダーを探すロジックとします。
    
    data = {
        "center_skill_effect": "",      # 2-1
        "center_skill_condition": "",   # 2-2
        "skill_effect": "",             # 2-3
        "skill_ap": "",                 # 2-4
        "center_characteristic": ""     # 2-5
    }

    # テキスト検索用ヘルパー関数
    def find_table_after_text(soup, search_text):
        # 指定テキストを含む要素を探し、その直後にあるtableを探す
        elements = soup.find_all(string=re.compile(search_text))
        for element in elements:
            parent = element.parent
            # 親要素から辿って次のtableを探す
            next_node = parent
            for _ in range(10): # 近傍探索
                if next_node:
                    next_node = next_node.find_next()
                    if next_node and next_node.name == 'table':
                        return next_node
        return None

    # --- 2-1. 「センタースキル」後の表 ---
    cs_table = find_table_after_text(soup, "センタースキル")
    if cs_table:
        # ヘッダーを探す
        rows = cs_table.find_all('tr')
        header_map = {}
        headers = rows[0].find_all(['th', 'td'])
        for i, h in enumerate(headers):
            header_map[clean_text(h.get_text())] = i
        
        # Lv 14 の行を探す
        if "Lv" in header_map and "効果" in header_map:
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
                        break

    # --- 2-2. 「センタースキル:」後の表 (発動条件) ---
    # 注: Wikiの構造により、2-1と同じ表の場合と異なる場合がありますが、
    # 「センタースキル:」という表記を探して再取得します。
    cs_cond_table = find_table_after_text(soup, "センタースキル") # 同じ場所の可能性が高い
    if cs_cond_table:
        rows = cs_cond_table.find_all('tr')
        # 行の中から「発動条件」というヘッダーを持つセルを探す、あるいは列を探す
        # WikiWikiのスペック表は縦持ち（項目が左）か横持ち（項目が上）か可変ですが、
        # 一般的に項目名を探してその隣の値を取得します。
        for row in rows:
            cols = row.find_all(['th', 'td'])
            for i, col in enumerate(cols):
                if "発動条件" in clean_text(col.get_text()):
                    # 次のセルを取得（colspan等を考慮して単純に次の要素）
                    if i + 1 < len(cols):
                        data["center_skill_condition"] = clean_text(cols[i+1].get_text())
                    break

    # --- 2-3. 「スキル:」の文字の後に配置される表 (Lv14効果) ---
    skill_table = find_table_after_text(soup, "スキル:")
    # "スキル:"で見つからない場合、単に"スキル"でも探してみる
    if not skill_table:
        skill_table = find_table_after_text(soup, "スキル")

    if skill_table:
        rows = skill_table.find_all('tr')
        header_map = {}
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
        
        # --- 2-4. 同じ表、あるいは近くの表で「スキルAP」 ---
        # スキル表の中にAPカラムがあるか、その前の概要表にあるか確認
        # ここではskill_table内、あるいはその直前の概要を探す必要がありますが、
        # 手順書は「2-3の表の後であり...スキルAP」とあるため、同じ表内か、その表を指していると解釈します。
        # もし表内に「スキルAP」という列があればそれを取得
        ap_text = ""
        if "スキルAP" in header_map:
             # スキルAPが列として存在する場合（Lvごとに違う場合はLv14の行を見る）
             # Lv14の行はすでにループで回しているので、そこから取得すべきですが、
             # 多くのWikiではAPは固定値で別枠、あるいは列です。
             # ここではLv14行のAPを取得してみます。
             pass 
             # 構造が不明確なため、"スキルAP"という項目名を持つセルを全探索します。
        
        # 表全体から「スキルAP」を探す
        for row in rows:
            cols = row.find_all(['th', 'td'])
            for i, col in enumerate(cols):
                if "スキルAP" in clean_text(col.get_text()):
                    if i + 1 < len(cols):
                        ap_text = clean_text(cols[i+1].get_text())
                    break
        
        # まだ見つからない場合、ヘッダー列としてのスキルAPを探す（Lv14行から）
        if not ap_text and "スキルAP" in header_map:
             # 再度Lv14行を探す
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

    # --- 2-5. 「センター特性:」の後の箇条書き ---
    # "センター特性"の文字を探し、その後の ul/li を取得
    center_char_elements = soup.find_all(string=re.compile("センター特性"))
    for element in center_char_elements:
        parent = element.parent
        next_node = parent
        for _ in range(10):
            if next_node:
                next_node = next_node.find_next()
                if next_node and next_node.name == 'ul':
                    # 箇条書きテキストを結合
                    items = [clean_text(li.get_text()) for li in next_node.find_all('li')]
                    data["center_characteristic"] = " / ".join(items) # TSV用に区切り文字で結合
                    break
        if data["center_characteristic"]:
            break

    return data

def main():
    print("Fetching card list...")
    soup = get_soup(LIST_URL)
    if not soup:
        print("Failed to get list page.")
        return

    # 1. カード一覧の取得
    # WikiWikiのテーブル構造に依存しますが、通常メインコンテンツ内のtableを探します
    # ここでは記事内の全てのリンクから、カードページと思われるものを抽出します
    # ※厳密にテーブル解析を行う場合、テーブルのクラス指定等が必要ですが、
    # 汎用的に記事内のリンクを走査します。
    
    cards = []
    
    # メインコンテンツエリアを取得（WikiWikiの一般的な構造）
    body = soup.find(id="body") or soup
    
    # リンクを収集 (重複排除のためdict使用)
    links = {} 
    for a in body.find_all('a'):
        href = a.get('href')
        text = clean_text(a.get_text())
        
        # リンクがカード詳細ページっぽいか判定（簡易判定）
        # 相対パスで始まる、かつ特定のキーワードを含まない、など
        if href and not href.startswith('http') and len(text) > 1:
            full_url = "https://wikiwiki.jp" + href
            links[full_url] = text

    print(f"Found {len(links)} potential links. Starting scrape...")

    results = []
    count = 0
    
    for url, name in links.items():
        # デバッグ用: 数件で止める場合はコメントアウトを解除
        # if count >= 5: break 
        
        print(f"Processing ({count+1}/{len(links)}): {name}")
        
        # スクレイピングマナーとしてウェイトを入れる
        time.sleep(1) 
        
        card_data = parse_card_page(url)
        
        if card_data:
            # 基本情報とマージ
            row = {
                "name": name,
                "url": url,
                **card_data
            }
            results.append(row)
        
        count += 1

    # 4. TSV出力
    output_file = "output.tsv"
    fieldnames = [
        "name", "url", 
        "center_skill_effect", "center_skill_condition", 
        "skill_effect", "skill_ap", "center_characteristic"
    ]
    
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
        writer.writeheader()
        writer.writerows(results)

    print(f"Done. Saved to {output_file}")

if __name__ == "__main__":
    main()

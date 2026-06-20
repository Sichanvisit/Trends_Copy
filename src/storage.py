import csv
import re
from datetime import datetime

from config import RAW_DATA_DIR, BODY_DIR

INDEX_FILE_PATH = RAW_DATA_DIR / "content_index.csv"


def sanitize_filename(text):
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = text.replace(" ", "_")
    return text[:30]


def load_content_index():
    if not INDEX_FILE_PATH.exists():
        return []

    index_data = []
    try:
        with open(INDEX_FILE_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                index_data.append(row)
    except Exception as e:
        print(f"[!] Failed to read content index: {e}")

    return index_data


def save_content_index(index_data):
    fields = ["id", "title", "source", "date", "url", "rank", "file_path", "content"]
    try:
        with open(INDEX_FILE_PATH, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(index_data)
    except Exception as e:
        print(f"[!] Failed to save content index: {e}")


def add_posts_to_storage(posts):
    """
    Store lightweight metadata for candidates, and full markdown only when content exists.
    """
    current_index = load_content_index()
    existing_urls = {row.get("url", "").strip() for row in current_index}
    existing_titles = {row.get("title", "").strip() for row in current_index if row.get("title")}

    if current_index:
        next_id = max(int(row["id"]) for row in current_index if str(row.get("id", "")).isdigit()) + 1
    else:
        next_id = 1

    added_count = 0
    today_str = datetime.now().strftime("%Y-%m-%d")

    from src.processor import clean_content, build_markdown_card

    for post in posts:
        url = post.get("url", "").strip()
        title = post.get("title", "").strip()
        
        # URL 또는 글 제목 중 하나라도 이미 존재하면 중복 처리
        if not url or url in existing_urls or (title and title in existing_titles):
            continue
        source = post.get("source", "").strip()
        rank = post.get("rank", "")
        raw_content = (post.get("content") or "").strip()
        cleaned_content = clean_content(raw_content)

        file_path = ""
        if cleaned_content:
            safe_title = sanitize_filename(title or url)
            filename = f"{today_str}_{source}_{safe_title}.md"
            markdown_path = BODY_DIR / filename
            markdown_content = build_markdown_card(title, source, today_str, url, cleaned_content)
            with open(markdown_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            file_path = str(markdown_path.resolve())

        new_row = {
            "id": str(next_id),
            "title": title,
            "source": source,
            "date": today_str,
            "url": url,
            "rank": str(rank) if rank is not None else "",
            "file_path": file_path,
            "content": cleaned_content,
        }
        current_index.append(new_row)
        existing_urls.add(url)
        existing_titles.add(title)
        next_id += 1
        added_count += 1

    if added_count > 0:
        save_content_index(current_index)

    print(f"[+] Saved {added_count} new items to the index.")
    return added_count

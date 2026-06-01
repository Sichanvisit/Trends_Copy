import csv
import os
from datetime import datetime
import re
from config import RAW_DATA_DIR, GENERATED_DIR

INDEX_FILE_PATH = RAW_DATA_DIR / "content_index.csv"

def sanitize_filename(text):
    """
    파일명에 쓸 수 없는 특수문자 제거 및 간소화
    """
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = text.replace(" ", "_")
    return text[:30] # 파일명 길이 제한

def load_content_index():
    """
    content_index.csv를 읽어서 리스트로 반환
    통합 필드: id,title,source,date,url,file_path,content
    """
    if not INDEX_FILE_PATH.exists():
        return []
        
    index_data = []
    try:
        with open(INDEX_FILE_PATH, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                index_data.append(row)
    except Exception as e:
        print(f"[!] 인덱스 파일을 불러오는 중 오류 발생: {e}")
        
    return index_data

def save_content_index(index_data):
    """
    content_index.csv 통합 파일 갱신 저장
    """
    fields = ["id", "title", "source", "date", "url", "file_path", "content"]
    try:
        with open(INDEX_FILE_PATH, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(index_data)
    except Exception as e:
        print(f"[!] 인덱스 파일 저장 중 오류 발생: {e}")

def add_posts_to_storage(posts):
    """
    수집된 글들을 하나의 통합 CSV(content_index.csv) 파일에만 단일 저장 및 관리
    중복된 URL은 자동으로 무시
    """
    current_index = load_content_index()
    existing_urls = {row["url"] for row in current_index}
    
    # 다음 ID 값 결정
    if current_index:
        next_id = max(int(row["id"]) for row in current_index) + 1
    else:
        next_id = 1
        
    added_count = 0
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Lazy imports to prevent circular references
    from src.processor import clean_content, build_markdown_card
    
    for post in posts:
        url = post["url"]
        if url in existing_urls:
            continue # 중복 필터링
            
        title = post["title"]
        source = post["source"]
        raw_content = post["content"]
        
        # 1. 본문 정제
        cleaned_content = clean_content(raw_content)
        
        # 2. Markdown 카드 빌드 및 저장 (옵시디언 보관소 타겟)
        safe_title = sanitize_filename(title)
        filename = f"{today_str}_{source}_{safe_title}.md"
        markdown_path = GENERATED_DIR / filename
        
        # Markdown 파일 쓰기
        markdown_content = build_markdown_card(title, source, today_str, url, cleaned_content)
        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
        # 3. 단일 통합 인덱스 DB 등록 (본문 내용까지 하나의 CSV에 보존)
        new_row = {
            "id": str(next_id),
            "title": title,
            "source": source,
            "date": today_str,
            "url": url,
            "file_path": str(markdown_path.resolve()), # 다른 폴더로의 이전/이동에 완벽히 방어하기 위해 절대경로 저장
            "content": cleaned_content
        }
        current_index.append(new_row)
            
        next_id += 1
        added_count += 1
        
    if added_count > 0:
        save_content_index(current_index)
        
    print(f"[+] 총 {added_count}개의 새로운 글감이 단일 통합 데이터베이스에 저장되었습니다.")
    return added_count

import os
import sys
from datetime import datetime
from config import GENERATED_DIR
from src.crawler import crawl_nate_pann, crawl_nate_news, crawl_geeknews
from src.storage import load_content_index, add_posts_to_storage, sanitize_filename
from src.generator import FORMS, STYLES, generate_draft

def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    print("=" * 60)
    print("        🚀 Trends_Copy (인텔리전스 워크벤치) 🚀        ")
    print("   - 뉴스·커뮤니티 글감 자동 수집 및 X 초안 변환 워크스테이션 -   ")
    print("=" * 60)

def run_crawler_flow():
    print("\n[1] 실시간 인기 글감 수집 단계")
    print("-" * 50)
    print("1. 네이트판 실시간 오늘의톡/톡커들의선택")
    print("2. 네이트 실시간 랭킹 관심뉴스 (최대 20위)")
    print("3. GeekNews 최신 정보 트렌드 수집")
    print("4. 전체 수집 (네이트판 + 네이트뉴스 + GeekNews)")
    print("5. 취소")
    
    choice = input("\n메뉴 선택 (1-5): ").strip()
    if choice not in ["1", "2", "3", "4"]:
        print("[*] 수집을 취소합니다.")
        return
        
    try:
        if choice == "2":
            limit = int(input("수집할 뉴스 순위 개수 (최대 20, 기본 20): ").strip() or "20")
        else:
            limit = int(input("사이트별 최대 수집 개수 (기본 5): ").strip() or "5")
    except ValueError:
        limit = 20 if choice == "2" else 5
        
    posts = []
    if choice in ["1", "4"]:
        print("\n[*] 네이트판 크롤링 시작...")
        posts.extend(crawl_nate_pann(limit=5 if choice == "4" else limit))
        
    if choice in ["2", "4"]:
        print("\n[*] 네이트 랭킹 뉴스 크롤링 시작...")
        posts.extend(crawl_nate_news(limit=5 if choice == "4" else limit))
        
    if choice in ["3", "4"]:
        print("\n[*] GeekNews 크롤링 시작...")
        posts.extend(crawl_geeknews(limit=5 if choice == "4" else limit))
        
    if not posts:
        print("[!] 새로운 글감을 하나도 찾지 못했거나 네트워크 오류가 발생했습니다.")
        return
        
    add_posts_to_storage(posts)
    input("\n[Enter]를 누르면 메인 메뉴로 돌아갑니다.")

def show_content_database():
    print("\n[2] 글감 인덱스 데이터베이스 조회")
    print("-" * 60)
    index_list = load_content_index()
    
    if not index_list:
        print("[!] 저장된 글감이 없습니다. [1. 실시간 글감 수집]을 먼저 실행해주세요.")
        input("\n[Enter]를 누르면 메인 메뉴로 돌아갑니다.")
        return []
        
    print(f"{'ID':<5} | {'출처':<8} | {'수집일':<11} | {'제목'}")
    print("-" * 60)
    for row in index_list:
        src_map = {
            "nate": "네이트판",
            "nate_news": "네이트뉴스",
            "geeknews": "긱뉴스"
        }
        src_kr = src_map.get(row["source"], row["source"])
        title_truncated = row["title"][:32] + "..." if len(row["title"]) > 32 else row["title"]
        print(f"{row['id']:<5} | {src_kr:<8} | {row['date']:<11} | {title_truncated}")
    print("-" * 60)
    return index_list

def run_generator_flow():
    index_list = show_content_database()
    if not index_list:
        return
        
    post_id = input("\nX 초안으로 변환할 글감 ID 선택: ").strip()
    selected_post = next((row for row in index_list if row["id"] == post_id), None)
    
    if not selected_post:
        print("[!] 잘못된 ID 번호입니다.")
        input("\n[Enter]를 누르면 메인 메뉴로 돌아갑니다.")
        return
        
    file_path = selected_post["file_path"]
    if not os.path.exists(file_path):
        from pathlib import Path
        file_path = Path(file_path).resolve()
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            markdown_content = f.read()
    except Exception as e:
        print(f"[!] 글감 카드를 불러올 수 없습니다: {e}")
        input("\n[Enter]를 누르면 메인 메뉴로 돌아갑니다.")
        return
        
    content_part = markdown_content
    if "## 📌 원문 내용" in markdown_content:
        content_part = markdown_content.split("## 📌 원문 내용")[-1].split("---")[0].strip()
        
    # 1. 양식(Form) 선택
    print("\n" + "="*20 + " [STEP 1] 변환 양식(Form) 선택 " + "="*20)
    for k, (name, desc) in FORMS.items():
        print(f"{k}. {name:<10} - {desc}")
    form_choice = input("\n양식 번호 입력 (기본 1): ").strip() or "1"
    if form_choice not in FORMS:
        form_choice = "1"
        
    # 2. 스타일(Style) 선택
    print("\n" + "="*20 + " [STEP 2] 적용 스타일(Style) 선택 (다중 선택 가능) " + "="*20)
    for k, (name, desc) in STYLES.items():
        print(f"{k}. {name:<12} - {desc}")
    style_input = input("\n스타일 번호 입력 (쉼표로 구분 예: 1,4 / 기본 2): ").strip() or "2"
    style_choices = [s.strip() for s in style_input.split(",") if s.strip() in STYLES]
    if not style_choices:
        style_choices = ["2"]
        
    # 3. 추가 요구사항
    print("\n" + "="*20 + " [STEP 3] 에디터 추가 지시사항 (선택사항) " + "="*20)
    extra_instruction = input("예: '마지막 문구는 냉소적으로', '현장감 있게 대화 유도' (없으면 Enter): ").strip()
    
    print("\n[*] X 스타일 콘텐츠 초안 생성 파이프라인 가동 중...")
    
    # 초안 생성
    draft_text, is_offline = generate_draft(
        selected_post["title"],
        content_part,
        form_choice,
        style_choices,
        extra_instruction
    )
    
    # 4. 결과 출력
    print("\n" + "=" * 25 + " 🎉 X 생성 초안 🎉 " + "=" * 25)
    print(draft_text)
    print("=" * 68)
    
    # 5. 초안 파일 저장
    today_str = datetime.now().strftime("%Y-%m-%d")
    safe_title = sanitize_filename(selected_post["title"])
    draft_filename = f"{today_str}_{selected_post['source']}_{safe_title}_x_draft.md"
    draft_path = GENERATED_DIR / draft_filename
    
    form_name = FORMS[form_choice][0]
    style_names = ", ".join([STYLES[sc][0] for sc in style_choices])
    
    full_draft_file_content = f"""# [X 초안 변환 카드] {selected_post['title']}

- **원본 글감**: [{selected_post['title']}]({selected_post['url']})
- **출처/일시**: {selected_post['source']} / {selected_post['date']}
- **설정 양식**: {form_name}
- **설정 스타일**: {style_names}
- **생성 방식**: {"Template Generator (오프라인 룰 엔진)" if is_offline else "LLM API 연결"}
- **생성 일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 📝 X 게시글 초안 내용

{draft_text}

---
*본 X 초안 카드는 Trends_Copy의 템플릿 변환 파이프라인으로 구축되었습니다.*
"""
    try:
        with open(draft_path, "w", encoding="utf-8") as f:
            f.write(full_draft_file_content)
        print(f"[+] 성공적으로 최종 X 초안 카드가 파일로 자동 정리 및 보존되었습니다.")
        print(f"    경로: data/generated/{draft_filename}")
    except Exception as e:
        print(f"[!] 초안 파일 자동 정리 저장 중 에러 발생: {e}")
        
    input("\n[Enter]를 누르면 메인 메뉴로 돌아갑니다.")

def main_menu_loop():
    while True:
        clear_terminal()
        print_header()
        print(" 1. 실시간 글감 수집 및 자동 정제 (Nate Pann / Nate News / GeekNews)")
        print(" 2. 수집된 글감 데이터베이스(Index DB) 조회 및 카드 열람")
        print(" 3. 선택한 글감 -> X(Twitter) 맞춤형 초안 자동 변환")
        print(" 4. 프로그램 종료")
        print("=" * 60)
        
        menu_choice = input("원하는 메뉴 번호를 선택하세요 (1-4): ").strip()
        
        if menu_choice == "1":
            run_crawler_flow()
        elif menu_choice == "2":
            show_content_database()
            input("\n[Enter]를 누르면 메인 메뉴로 돌아갑니다.")
        elif menu_choice == "3":
            run_generator_flow()
        elif menu_choice == "4":
            print("\n[*] Trends_Copy를 종료합니다. 오늘도 파급력 있는 하루 되세요!")
            sys.exit(0)
        else:
            print("[!] 올바르지 않은 입력입니다. 1에서 4 사이의 숫자가 입력해 주세요.")
            import time
            time.sleep(1)

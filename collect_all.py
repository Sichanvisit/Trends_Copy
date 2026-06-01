import sys
import io
from pathlib import Path

# UTF-8 입출력 강제 설정 (Windows 인코딩 문제 차단)
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 모듈 경로 추가
sys.path.append(str(Path(__file__).resolve().parent))

from src.crawler import crawl_nate_pann, crawl_nate_news, crawl_geeknews
from src.storage import add_posts_to_storage, load_content_index

def run_automated_pipeline():
    print("=" * 60)
    print(" ⚡ X Content Workbench - 실시간 자동 통합 큐레이션 가동 ⚡")
    print("=" * 60)
    
    all_posts = []
    
    # 1. 네이트판 오늘의톡 / 톡커들의선택 수집 (각 10개 한도)
    try:
        print("\n[*] [1/3] 네이트판 인기 글감 수집 중...")
        nate_posts = crawl_nate_pann(limit=20)
        all_posts.extend(nate_posts)
        print(f"    -> 네이트판 후보 {len(nate_posts)}개 확보.")
    except Exception as e:
        print(f"[!] 네이트판 수집 실패: {e}")
        
    # 2. 네이트 실시간 랭킹 뉴스 수집 (최대 20개 한도)
    try:
        print("\n[*] [2/3] 네이트 실시간 랭킹 관심뉴스 수집 중...")
        news_posts = crawl_nate_news(limit=20)
        all_posts.extend(news_posts)
        print(f"    -> 네이트뉴스 후보 {len(news_posts)}개 확보.")
    except Exception as e:
        print(f"[!] 네이트 뉴스 수집 실패: {e}")
        
    # 3. GeekNews 최신 IT/스타트업 트렌드 수집 (최대 10개 한도)
    try:
        print("\n[*] [3/3] GeekNews 테크 트렌드 수집 중...")
        geek_posts = crawl_geeknews(limit=10)
        all_posts.extend(geek_posts)
        print(f"    -> GeekNews 후보 {len(geek_posts)}개 확보.")
    except Exception as e:
        print(f"[!] GeekNews 수집 실패: {e}")
        
    if not all_posts:
        print("\n[!] 확보된 후보 글감이 존재하지 않습니다.")
        return
        
    print("\n" + "=" * 60)
    print(" 📥 중복 검사 및 데이터베이스(content_index.csv) 적재")
    print("=" * 60)
    
    # 중복 체크 후 최종 저장소 적재
    added_count = add_posts_to_storage(all_posts)
    
    print("\n" + "=" * 60)
    print(f" 🎉 자동 통합 수집 완료! 총 {added_count}개의 새로운 글감이 정리되었습니다.")
    print(f" (필터링된 중복 글감: {len(all_posts) - added_count}개)")
    print("=" * 60)

if __name__ == "__main__":
    run_automated_pipeline()

import sys
from pathlib import Path

# 모듈 경로 세팅
sys.path.append(str(Path(__file__).resolve().parent))

from src.crawler import crawl_nate_pann, crawl_nate_news, crawl_geeknews

def test_crawlers():
    print("=" * 60)
    print(" [Nate Pann Today Talk / Talker Choice Verification] ")
    print("=" * 60)
    try:
        nate_posts = crawl_nate_pann(limit=3)
        for i, p in enumerate(nate_posts, 1):
            title_safe = p['title'].encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
            content_safe = p['content'][:120].strip().encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
            print(f"\n[{i}] Title: {title_safe}")
            print(f"    URL: {p['url']}")
            print(f"    Body Summary: {content_safe}...")
            print("-" * 55)
    except Exception as e:
        print(f"[!] Nate Pann test error: {e}")
        
    print("\n" + "=" * 60)
    print(" [Nate Ranking News - Interest Verification] ")
    print("=" * 60)
    try:
        news_posts = crawl_nate_news(limit=3)
        for i, p in enumerate(news_posts, 1):
            title_safe = p['title'].encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
            content_safe = p['content'][:120].strip().encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
            print(f"\n[{i}] Title: {title_safe}")
            print(f"    URL: {p['url']}")
            print(f"    Body Summary: {content_safe}...")
            print("-" * 55)
    except Exception as e:
        print(f"[!] Nate Ranking News test error: {e}")
        
    print("\n" + "=" * 60)
    print(" [GeekNews Tech Trend Verification] ")
    print("=" * 60)
    try:
        geek_posts = crawl_geeknews(limit=3)
        for i, p in enumerate(geek_posts, 1):
            title_safe = p['title'].encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
            content_safe = p['content'][:120].strip().encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
            print(f"\n[{i}] Title: {title_safe}")
            print(f"    URL: {p['url']}")
            print(f"    Body Summary: {content_safe}...")
            print("-" * 55)
    except Exception as e:
        print(f"[!] GeekNews test error: {e}")

if __name__ == "__main__":
    import sys
    import io
    if sys.platform.startswith('win'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    test_crawlers()

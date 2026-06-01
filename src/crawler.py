import re
import urllib.parse
import requests
from bs4 import BeautifulSoup

# User-Agent 설정 (봇 차단 방지)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def crawl_nate_pann(limit=10):
    """
    네이트판 메인 홈에서 '오늘의 톡'과 '톡커들의 선택' 영역을 각 10개 단위로 정밀 수집
    """
    url = "https://pann.nate.com/"
    posts = []
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"[!] 네이트판 목록 조회 실패 (HTTP {response.status_code})")
            return posts
            
        soup = BeautifulSoup(response.text, "html.parser")
        unique_links = {}
        
        # 1. 오늘의 톡 수집
        today_talk_items = soup.select(".today-talk li")
        today_count = 0
        for li in today_talk_items:
            for a in li.find_all("a", href=True):
                href = a["href"]
                match = re.search(r"/talk/(\d+)", href)
                if match:
                    post_id = match.group(1)
                    full_url = f"https://pann.nate.com/talk/{post_id}"
                    
                    cate = li.select_one(".cate")
                    cate_text = cate.get_text(strip=True) if cate else ""
                    title_text = a.get_text(strip=True)
                    full_title = f"{cate_text} {title_text}".strip()
                    
                    if full_url not in unique_links and title_text and len(title_text) > 4:
                        if today_count < 10:
                            unique_links[full_url] = (full_title, "오늘의톡")
                            today_count += 1
                        
        # 2. 톡커들의 선택 수집
        best_talk_items = soup.select(".best-talk li")
        best_count = 0
        for li in best_talk_items:
            for a in li.find_all("a", href=True):
                href = a["href"]
                match = re.search(r"/talk/(\d+)", href)
                if match:
                    post_id = match.group(1)
                    full_url = f"https://pann.nate.com/talk/{post_id}"
                    
                    title_text = a.get_text(strip=True)
                    if full_url not in unique_links and title_text and len(title_text) > 4:
                        if best_count < 10:
                            unique_links[full_url] = (title_text, "톡커들의선택")
                            best_count += 1
                            
        target_links = list(unique_links.items())[:limit]
        print(f"[*] 네이트판 글감 후보 중 총 {len(target_links)}개 수집 대상 선정 (오늘의톡 {today_count}개, 톡커들의선택 {best_count}개)")
        print(f"[*] 상위 {len(target_links)}개 게시물 본문 상세 수집 중...")
        
        for post_url, (title, sub_source) in target_links:
            detail_response = requests.get(post_url, headers=HEADERS, timeout=8)
            if detail_response.status_code == 200:
                detail_soup = BeautifulSoup(detail_response.text, "html.parser")
                
                content_div = detail_soup.select_one("#contentArea, .view_area, .pann_content")
                if content_div:
                    content_text = content_div.get_text(separator="\n", strip=True)
                    posts.append({
                        "title": f"[{sub_source}] {title}",
                        "content": content_text,
                        "url": post_url,
                        "source": "nate"
                    })
            
    except Exception as e:
        print(f"[!] 네이트판 크롤링 중 예외 발생: {e}")
        
    return posts

def crawl_nate_news(limit=20):
    """
    네이트 랭킹뉴스 관심뉴스 영역 수집 (최대 20개 타겟팅)
    """
    url = "https://news.nate.com/rank/interest?sc=all&p=day"
    posts = []
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"[!] 네이트 랭킹뉴스 목록 조회 실패 (HTTP {response.status_code})")
            return posts
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        # /view/ 및 mid=n1006 패턴의 상세 뉴스 링크 추출
        unique_links = {}
        rank_index = 1
        for a in soup.find_all("a", href=True):
            href = a["href"]
            title_text = a.get_text(strip=True)
            
            if "news.nate.com/view/" in href or ("/view/" in href and "mid=" in href):
                # 절대 경로 정규화
                if href.startswith("//"):
                    full_url = "https:" + href
                elif href.startswith("/"):
                    full_url = "https://news.nate.com" + href
                else:
                    full_url = href
                    
                # 파라미터 제외하고 URL 고유키로 중복 방지
                base_url = full_url.split("?")[0]
                
                if base_url not in unique_links and title_text and len(title_text) > 8:
                    if rank_index <= 20:
                        unique_links[base_url] = (title_text, rank_index)
                        rank_index += 1
                        
        target_links = list(unique_links.items())[:limit]
        print(f"[*] 네이트 관심뉴스 랭킹 글감 후보 {len(unique_links)}개 탐색 완료. 상위 {len(target_links)}개 수집 중...")
        
        for post_url, (title, rank) in target_links:
            detail_response = requests.get(post_url, headers=HEADERS, timeout=8)
            if detail_response.status_code == 200:
                detail_soup = BeautifulSoup(detail_response.text, "html.parser")
                
                # 네이트 뉴스 본문 전용 셀렉터 (#realArtcContents, #articleContetns)
                content_div = detail_soup.select_one("#realArtcContents, #articleContetns, div.articleContetns")
                if content_div:
                    content_text = content_div.get_text(separator="\n", strip=True)
                    posts.append({
                        "title": f"[네이트뉴스 {rank}위] {title}",
                        "content": content_text,
                        "url": post_url,
                        "source": "nate_news"
                    })
                    
    except Exception as e:
        print(f"[!] 네이트 뉴스 랭킹 크롤링 중 예외 발생: {e}")
        
    return posts

def crawl_geeknews(limit=5):
    """
    GeekNews (news.hada.io)의 최신 테크/트렌드 토픽 수집
    목록에서는 요약문(일부 생략됨)만 제공하므로 각 토픽의 상세 페이지(topic?id=...)로 이동하여
    전체 원문 내용(.topic_contents)을 정밀하게 수집합니다.
    """
    url = "https://news.hada.io/"
    posts = []
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"[!] GeekNews 목록 조회 실패 (HTTP {response.status_code})")
            return posts
            
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select(".topic_row")
        
        print(f"[*] GeekNews 후보 토픽 {len(rows)}개 수집 및 상세 원문 추출 시작...")
        
        count = 0
        for row in rows:
            if count >= limit:
                break
                
            title_elem = row.select_one(".topictitle a")
            desc_elem = row.select_one(".topicdesc")
            
            if title_elem and desc_elem:
                title = title_elem.get_text(strip=True)
                desc = desc_elem.get_text(separator="\n", strip=True)
                href = title_elem["href"]
                
                # 아웃바운드 링크 정규화
                if href.startswith("http"):
                    post_url = href
                else:
                    post_url = "https://news.hada.io/" + href
                
                # 상세 페이지(댓글 페이지) 링크 찾기 (원문 전체 디스크립션 추출 목적)
                topic_link = None
                for a in row.find_all("a", href=True):
                    if "topic?id=" in a["href"]:
                        topic_link = a["href"]
                        break
                
                # 상세 페이지가 존재할 경우, 상세 본문을 긁어옴
                if topic_link:
                    detail_url = "https://news.hada.io/" + topic_link
                    try:
                        detail_res = requests.get(detail_url, headers=HEADERS, timeout=8)
                        if detail_res.status_code == 200:
                            detail_soup = BeautifulSoup(detail_res.text, "html.parser")
                            contents_elem = detail_soup.select_one("#topic_contents, .topic_contents, div.topic_contents")
                            if contents_elem:
                                full_desc = contents_elem.get_text(separator="\n", strip=True)
                                if full_desc:
                                    desc = full_desc
                    except Exception as ex:
                        print(f"[!] GeekNews 상세 페이지 {detail_url} 수집 중 오류 (목록 요약본 대체): {ex}")
                    
                posts.append({
                    "title": f"[GeekNews] {title}",
                    "content": desc,
                    "url": post_url,
                    "source": "geeknews"
                })
                count += 1
                
    except Exception as e:
        print(f"[!] GeekNews 크롤링 중 예외 발생: {e}")
        
    return posts

if __name__ == "__main__":
    # 개별 테스트용
    print("--- 네이트 뉴스 랭킹 테스트 ---")
    news_results = crawl_nate_news(limit=3)
    for p in news_results:
        print(f"[{p['source']}] {p['title']}")
        print(p['url'])
        print(p['content'][:100] + "...")
        print("-" * 30)

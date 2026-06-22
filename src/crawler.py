import re
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

NOISE_QUERY_KEYS = {
    "page",
    "po",
    "od",
    "category",
    "groupCd",
    "sort",
    "tab",
    "from",
    "utm_source",
    "utm_medium",
    "utm_campaign",
}


def _clean_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _canonical_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in NOISE_QUERY_KEYS]
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query, doseq=True), ""))


_TRANSLATION_SESSION = requests.Session()

def translate_to_korean(text: str) -> str:
    if not text:
        return ""
    import urllib.parse
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ko&dt=t&q={urllib.parse.quote(text)}"
        response = _TRANSLATION_SESSION.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            res_json = response.json()
            if res_json and len(res_json) > 0 and res_json[0]:
                translated = "".join([part[0] for part in res_json[0] if part[0]])
                return translated
    except Exception as e:
        print(f"[!] Translation error for '{text}': {e}")
    return text


def _translate_posts_parallel(posts: list[dict]) -> None:
    from concurrent.futures import ThreadPoolExecutor
    import time
    import random
    
    def translate_single(post):
        source = post.get("source")
        if source in [
            "hn_news", "hn_best", "yahoo_jp", "mumsnet",
            "reddit_boru", "reddit_mc", "reddit_pr", "reddit_aita", "reddit_rel",
            "reddit_aww", "reddit_animals_jerks", "reddit_animals_derps", "reddit_animals_funny",
            "reddit_parenting_fails", "reddit_toddlers", "reddit_children_falling", "reddit_kids_stupid"
        ]:
            title = post.get("title", "")
            if not title or title.startswith("[번역]"):
                return
            # 구글 번역 차단을 방지하기 위한 미세 딜레이 추가
            time.sleep(random.uniform(0.05, 0.15))
            translated = translate_to_korean(title)
            if translated and translated != title:
                post["title"] = f"[번역] {translated}"
                
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(translate_single, posts))


def _make_post(source: str, title: str, url: str, rank=None, feed: str = "", content: str = "") -> dict:
    post = {
        "source": source,
        "title": _clean_text(title),
        "url": _canonical_url(url),
        "rank": "" if rank is None else rank,
        "content": _clean_text(content),
    }
    if feed:
        post["feed"] = feed
    return post



def _request_html(url: str, timeout: int = 15) -> str:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    if response.status_code != 200:
        raise Exception(f"HTTP {response.status_code}")
    return response.text


def _append_unique(posts: list[dict], seen: set[str], candidate: dict, limit: int) -> None:
    if len(posts) >= limit:
        return
    key = candidate["url"]
    if not key or key in seen:
        return
    seen.add(key)
    posts.append(candidate)


def crawl_theqoo_hot(limit=30, include_content=True):
    """
    theqoo hot board. Collects list titles and links only by default.
    """
    posts = []
    seen = set()
    page = 1
    max_pages = max(1, min(10, (limit + 19) // 20 + 1))

    try:
        while len(posts) < limit and page <= max_pages:
            url = f"https://theqoo.net/hot?page={page}"
            html = _request_html(url)
            soup = BeautifulSoup(html, "html.parser")

            for tr in soup.select("tr"):
                if "notice" in (tr.get("class") or []):
                    continue
                title_cell = tr.select_one("td.title a[href]")
                if not title_cell:
                    continue
                href = title_cell.get("href", "")
                if not re.search(r"/hot/\d+", href):
                    continue

                title = _clean_text(title_cell.get_text(" ", strip=True))
                if not title or title.startswith("[공지]"):
                    continue

                candidate = _make_post("theqoo", title, urljoin(url, href), rank=page, feed="hot")
                _append_unique(posts, seen, candidate, limit)

            next_link = soup.find("a", href=re.compile(r"/hot\?page=%d" % (page + 1)))
            if not next_link and page >= max_pages:
                break
            page += 1

    except Exception as e:
        print(f"[!] theqoo crawl error: {e}")

    return posts


def crawl_hn_best(limit=30, include_content=True, feed="best"):
    """
    Hacker News hot/best list.
    """
    posts = []
    seen = set()
    page = 1
    max_pages = max(1, min(10, (limit + 29) // 30 + 1))
    base = "https://news.ycombinator.com/best" if feed == "best" else "https://news.ycombinator.com/"
    source = f"hn_{feed}"

    try:
        while len(posts) < limit and page <= max_pages:
            url = base if page == 1 else f"{base}?p={page}"
            html = _request_html(url)
            soup = BeautifulSoup(html, "html.parser")

            for row in soup.select("tr.athing"):
                title_link = row.select_one("span.titleline > a") or row.select_one("a.storylink")
                if not title_link:
                    continue
                title = _clean_text(title_link.get_text(" ", strip=True))
                href = title_link.get("href", "")
                if not href:
                    continue
                candidate = _make_post(source, title, urljoin(url, href), rank=row.get("id"), feed=feed)
                _append_unique(posts, seen, candidate, limit)

            if len(posts) >= limit:
                break
            page += 1

    except Exception as e:
        print(f"[!] HN {feed} crawl error: {e}")

    _translate_posts_parallel(posts)
    return posts


def crawl_ruliweb_best(limit=30, include_content=True):
    posts = []
    seen = set()
    page = 1
    max_pages = max(1, min(10, (limit + 19) // 20 + 1))

    try:
        while len(posts) < limit and page <= max_pages:
            url = "https://bbs.ruliweb.com/best/humor_only/now" if page == 1 else f"https://bbs.ruliweb.com/best/humor_only/now?page={page}"
            html = _request_html(url)
            soup = BeautifulSoup(html, "html.parser")

            for a in soup.select("a.subject_link"):
                href = a.get("href", "")
                if not href.startswith("/best/board/"):
                    continue
                title = _clean_text(a.get_text(" ", strip=True))
                title = re.sub(r"\s*\(\d+\)$", "", title).strip()
                if not title:
                    continue
                candidate = _make_post("ruliweb", title, urljoin(url, href), rank=page, feed="best")
                _append_unique(posts, seen, candidate, limit)

            if len(posts) >= limit:
                break
            page += 1

    except Exception as e:
        print(f"[!] Ruliweb crawl error: {e}")

    return posts


def crawl_todayhumor_humorbest(limit=30, include_content=True):
    posts = []
    seen = set()
    page = 1
    max_pages = max(1, min(10, (limit + 19) // 20 + 1))

    try:
        while len(posts) < limit and page <= max_pages:
            url = "https://www.todayhumor.co.kr/board/list.php?table=humorbest" if page == 1 else f"https://www.todayhumor.co.kr/board/list.php?table=humorbest&page={page}"
            html = _request_html(url)
            soup = BeautifulSoup(html, "html.parser")

            for a in soup.select("td.subject a[href]"):
                href = a.get("href", "")
                if "/board/view.php" not in href:
                    continue
                title = _clean_text(a.get_text(" ", strip=True))
                if not title:
                    continue
                candidate = _make_post("todayhumor", title, urljoin(url, href), rank=page, feed="humorbest")
                _append_unique(posts, seen, candidate, limit)

            if len(posts) >= limit:
                break
            page += 1

    except Exception as e:
        print(f"[!] TodayHumor crawl error: {e}")

    return posts


def crawl_clien_park(limit=30, include_content=True):
    posts = []
    seen = set()
    po = 0
    step = 20
    max_pages = max(1, min(10, (limit + step - 1) // step + 1))

    try:
        while len(posts) < limit and (po // step) < max_pages:
            url = f"https://www.clien.net/service/board/park?po={po}&category=0&groupCd="
            html = _request_html(url)
            soup = BeautifulSoup(html, "html.parser")

            for a in soup.select("a.list_subject[href]"):
                href = a.get("href", "")
                if "/service/board/park/" not in href:
                    continue
                title = _clean_text(a.get_text(" ", strip=True))
                if not title or title.startswith("[보안안내]"):
                    continue
                candidate = _make_post("clien", title, urljoin(url, href), rank=po, feed="park")
                _append_unique(posts, seen, candidate, limit)

            if len(posts) >= limit:
                break
            po += step

    except Exception as e:
        print(f"[!] Clien crawl error: {e}")

    return posts


def crawl_yahoo_entertainment(limit=40, include_content=True):
    posts = []
    seen = set()

    try:
        url = "https://news.yahoo.co.jp/ranking/comment/entertainment"
        html = _request_html(url)
        soup = BeautifulSoup(html, "html.parser")

        for idx, a in enumerate(soup.find_all("a", href=True), start=1):
            href = a.get("href", "")
            title = _clean_text(a.get_text(" ", strip=True))
            if "news.yahoo.co.jp/articles/" not in href:
                continue
            if not title or len(title) < 8:
                continue
            candidate = _make_post("yahoo_jp", title, href, rank=idx, feed="comment_entertainment")
            _append_unique(posts, seen, candidate, limit)
            if len(posts) >= limit:
                break

    except Exception as e:
        print(f"[!] Yahoo Japan crawl error: {e}")

    _translate_posts_parallel(posts)
    return posts


def crawl_mumsnet_aibu(limit=30, include_content=True):
    posts = []
    seen = set()
    page = 1
    max_pages = max(1, min(10, (limit + 24) // 25 + 1))

    try:
        while len(posts) < limit and page <= max_pages:
            url = "https://www.mumsnet.com/talk/am_i_being_unreasonable" if page == 1 else f"https://www.mumsnet.com/talk/am_i_being_unreasonable?page={page}"
            html = _request_html(url)
            soup = BeautifulSoup(html, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                if "/talk/am_i_being_unreasonable/" not in href:
                    continue
                title = _clean_text(a.get_text(" ", strip=True))
                if not title or title in {"Am I being unreasonable?", "Active discussions"}:
                    continue
                candidate = _make_post("mumsnet", title, urljoin(url, href), rank=page, feed="aibu")
                _append_unique(posts, seen, candidate, limit)

            if len(posts) >= limit:
                break
            page += 1

    except Exception as e:
        print(f"[!] Mumsnet crawl error: {e}")

    _translate_posts_parallel(posts)
    return posts


def crawl_reddit_subreddit(subreddit: str, limit=20, sort="hot"):
    """
    Reddit 수집기: Cloudflare 블록을 우회하기 위해 old.reddit.com HTML 페이지를 직접 파싱하여 수집합니다.
    """
    posts = []
    seen = set()
    import time
    time.sleep(1.0)
    try:
        url = f"https://old.reddit.com/r/{subreddit}/{sort}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"[!] Reddit old mirror returned {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.text, "html.parser")
        things = soup.select("div.thing")
        
        for thing in things:
            classes = thing.get("class", [])
            # 스폰서 및 공지사항 핀 제외
            if "stub" in classes or "promoted" in classes:
                continue
                
            title_a = thing.select_one("a.title")
            if not title_a:
                continue
                
            title = _clean_text(title_a.get_text(" ", strip=True))
            href = title_a.get("href", "")
            if not href:
                continue
                
            full_url = urljoin("https://old.reddit.com", href)
            
            score_elem = thing.select_one("div.score.unvoted")
            score = score_elem.get("title", "") if score_elem else ""
            if not score and score_elem:
                score = score_elem.text.strip()
                
            reddit_key_map = {
                "BestofRedditorUpdates": "reddit_boru",
                "MaliciousCompliance": "reddit_mc",
                "ProRevenge": "reddit_pr",
                "AmItheAsshole": "reddit_aita",
                "relationship_advice": "reddit_rel",
                "aww": "reddit_aww",
                "AnimalsBeingJerks": "reddit_animals_jerks",
                "AnimalsBeingDerps": "reddit_animals_derps",
                "AnimalsBeingFunny": "reddit_animals_funny",
                "Parentingfails": "reddit_parenting_fails",
                "toddlers": "reddit_toddlers",
                "ChildrenFallingOver": "reddit_children_falling",
                "KidsAreFuckingStupid": "reddit_kids_stupid"
            }
            source_key = reddit_key_map.get(subreddit, f"reddit_{subreddit}")
            candidate = _make_post(source_key, title, full_url, rank=score, feed=sort)
            _append_unique(posts, seen, candidate, limit)
            if len(posts) >= limit:
                break
    except Exception as e:
        print(f"[!] Reddit old mirror crawl error: {e}")
        
    _translate_posts_parallel(posts)
    return posts


def collect_hot_candidates(limit=None):
    """
    Collect a balanced hot/popular candidate pool across the configured sites.
    """
    sources = [
        ("theqoo", lambda n: crawl_theqoo_hot(limit=n, include_content=False), 10),
        ("hn_hot", lambda n: crawl_hn_best(limit=n, include_content=False, feed="news"), 10),
        ("hn_best", lambda n: crawl_hn_best(limit=n, include_content=False, feed="best"), 10),
        ("ruliweb", lambda n: crawl_ruliweb_best(limit=n, include_content=False), 10),
        ("todayhumor", lambda n: crawl_todayhumor_humorbest(limit=n, include_content=False), 10),
        ("clien", lambda n: crawl_clien_park(limit=n, include_content=False), 10),
        ("yahoo_jp", lambda n: crawl_yahoo_entertainment(limit=n, include_content=False), 10),
        ("mumsnet", lambda n: crawl_mumsnet_aibu(limit=n, include_content=False), 10),
        ("reddit_boru", lambda n: crawl_reddit_subreddit("BestofRedditorUpdates", limit=n, sort="hot"), 10),
        ("reddit_mc", lambda n: crawl_reddit_subreddit("MaliciousCompliance", limit=n, sort="hot"), 10),
        ("reddit_pr", lambda n: crawl_reddit_subreddit("ProRevenge", limit=n, sort="hot"), 10),
        ("reddit_aita", lambda n: crawl_reddit_subreddit("AmItheAsshole", limit=n, sort="hot"), 10),
        ("reddit_rel", lambda n: crawl_reddit_subreddit("relationship_advice", limit=n, sort="hot"), 10),
        ("reddit_aww", lambda n: crawl_reddit_subreddit("aww", limit=n, sort="hot"), 10),
        ("reddit_animals_jerks", lambda n: crawl_reddit_subreddit("AnimalsBeingJerks", limit=n, sort="hot"), 10),
        ("reddit_animals_derps", lambda n: crawl_reddit_subreddit("AnimalsBeingDerps", limit=n, sort="hot"), 10),
        ("reddit_animals_funny", lambda n: crawl_reddit_subreddit("AnimalsBeingFunny", limit=n, sort="hot"), 10),
        ("reddit_parenting_fails", lambda n: crawl_reddit_subreddit("Parentingfails", limit=n, sort="hot"), 10),
        ("reddit_toddlers", lambda n: crawl_reddit_subreddit("toddlers", limit=n, sort="hot"), 10),
        ("reddit_children_falling", lambda n: crawl_reddit_subreddit("ChildrenFallingOver", limit=n, sort="hot"), 10),
        ("reddit_kids_stupid", lambda n: crawl_reddit_subreddit("KidsAreFuckingStupid", limit=n, sort="hot"), 10),
        ("nate", lambda n: crawl_nate_pann(limit=n, include_content=False), 10),
        ("nate_news", lambda n: crawl_nate_news(limit=n, include_content=False), 10),
        ("geeknews", lambda n: crawl_geeknews(limit=n, include_content=False), 10),
        ("shinsia", lambda n: crawl_shinsia(limit=n, include_content=True), 10),
        ("inssider_couple", lambda n: crawl_inssider_couple(limit=n, include_content=False), 10),
        ("inssider_job", lambda n: crawl_inssider_job(limit=n, include_content=False), 10),
        ("inssider_politics", lambda n: crawl_inssider_politics(limit=n, include_content=False), 10),
        ("inssider_humor", lambda n: crawl_inssider_humor(limit=n, include_content=False), 10),
        ("inssider_lounge", lambda n: crawl_inssider_lounge(limit=n, include_content=False), 10),
    ]

    from concurrent.futures import ThreadPoolExecutor

    collected = []
    seen = set()

    def run_crawler(source_item):
        source_name, fn, cap = source_item
        try:
            return source_name, fn(cap)
        except Exception as e:
            print(f"[!] Source failed ({source_name}): {e}")
            return source_name, []

    with ThreadPoolExecutor(max_workers=len(sources)) as executor:
        results = list(executor.map(run_crawler, sources))

    # 라운드 로빈 방식으로 각 출처의 글감을 골고루 병합하여 limit 슬라이스 시 특정 출처가 잘리는 현상 방지
    collected = []
    seen = set()
    
    batches = [list(batch) for _, batch in results if batch]
    while any(batches):
        for b in list(batches):
            if not b:
                batches.remove(b)
                continue
            post = b.pop(0)
            key = post["url"]
            if key in seen:
                continue
            seen.add(key)
            collected.append(post)

    if limit is not None:
        return collected[:limit]
    return collected


def get_image_base64(img_url: str) -> tuple[str, str]:
    """
    이미지 URL을 다운로드하여 (base64_string, mime_type) 튜플을 반환합니다.
    """
    import base64
    import mimetypes
    try:
        r = requests.get(img_url, headers=HEADERS, timeout=5, stream=True)
        if r.status_code == 200:
            content_type = r.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                mime, _ = mimetypes.guess_type(img_url)
                content_type = mime or "image/jpeg"
            
            data = b""
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                data += chunk
                if len(data) > 3 * 1024 * 1024:  # 최대 3MB 제한
                    return None, None
            
            b64_data = base64.b64encode(data).decode("utf-8")
            return b64_data, content_type
    except Exception as e:
        print(f"[!] Failed to convert image {img_url}: {e}")
    return None, None


def scrape_single_url(url: str) -> dict:
    """
    URL 스크래퍼: Gemini API를 사용하여 본문과 이미지 경로를 수집하며,
    멀티모달 이미지를 해석하여 상세한 설명과 번역을 포함해 마크다운 형태로 정밀 재구성합니다.
    """
    url = url.strip()
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")
        
        # 1. 스크립트, 스타일, 네비게이션, 푸터 등 노이즈 제거
        for tag in soup(["script", "style", "nav", "footer", "header", "iframe"]):
            tag.decompose()
            
        # 2. 모든 이미지 태그 정보 추출
        images = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src:
                full_src = urljoin(url, src)
                alt = img.get("alt", "").strip() or "이미지"
                if "icon" not in full_src.lower() and not full_src.endswith(".gif") and not "logo" in full_src.lower():
                    images.append({"src": full_src, "alt": alt})
                    
        # 3. HTML 텍스트 정밀화 (토큰 세이브)
        html_content = str(soup.body)[:15000] if soup.body else str(soup)[:15000]
        
        # 4. 제미나이 API 호출 설정
        import config
        from openai import OpenAI
        
        if config.GEMINI_API_KEY:
            try:
                client = OpenAI(api_key=config.GEMINI_API_KEY, base_url=config.GEMINI_BASE_URL)
                
                # 이미지 분석 데이터 준비 (최대 4개 이미지 전송)
                user_content_parts = []
                text_instruction = (
                    "You are a web scraper assistant. Analyze the raw HTML and the attached images.\n"
                    "Reconstruct the article in clean Korean Markdown format.\n"
                    "Specifically, analyze each attached image visually (e.g. explain charts, describe photographs, translate text inside screenshots if relevant) "
                    "and weave that image analysis directly into the corresponding part of the article text.\n"
                    "Embed the image link in the markdown like: `![Image Description: [Detailed Visual Interpretation]](image_url)`.\n"
                    "Do not include advertising, headers, footers, or comments.\n"
                    "Your response must be a valid JSON object with EXACTLY two keys: 'title' (string) and 'content' (Markdown string).\n\n"
                    f"[HTML Content]\n{html_content}"
                )
                user_content_parts.append({"type": "text", "text": text_instruction})
                
                for idx, img in enumerate(images[:4]):  # 최대 4개 제한
                    b64_str, mime = get_image_base64(img["src"])
                    if b64_str and mime:
                        user_content_parts.append({
                            "type": "text",
                            "text": f"\n\n[Vision Input - Image {idx+1}] Associated Image URL: {img['src']}"
                        })
                        user_content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64_str}"}
                        })
                
                system_prompt = (
                    "You are a vision-capable web scraper. Reconstruct Korean articles with visual analysis of embedded images. "
                    "Always output a valid JSON object with 'title' and 'content' keys."
                )
                
                response = client.chat.completions.create(
                    model=config.GEMINI_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content_parts}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    timeout=45.0
                )
                
                import json
                result = json.loads(response.choices[0].message.content.strip())
                return {
                    "title": result.get("title", "Scraped Content"),
                    "content": result.get("content", ""),
                    "url": url,
                    "source": "gemini_multimodal_scraper"
                }
            except Exception as gemini_err:
                print(f"[!] Gemini multimodal scraping fallback: {gemini_err}")
                
        # Fallback to legacy static scraping if Gemini key is missing or fails
        title_elem = soup.select_one("h1, title")
        title = _clean_text(title_elem.get_text(" ", strip=True)) if title_elem else "Web Page"
        
        # 기본 텍스트 추출 및 이미지 링크 리스트 추가
        text_lines = []
        for p in soup.find_all(["p", "div"]):
            txt = _clean_text(p.get_text(strip=True))
            if txt and len(txt) > 20 and txt not in text_lines:
                text_lines.append(txt)
                
        content_markdown = "\n\n".join(text_lines)
        if images:
            content_markdown += "\n\n### [수집된 이미지 목록]\n"
            for img in images[:10]:
                content_markdown += f"![{img['alt']}]({img['src']})\n"
                
        return {"title": title, "content": content_markdown, "url": url, "source": "fallback_scraper"}
        
    except Exception as e:
        raise Exception(f"URL scrape failed: {e}")


def crawl_nate_pann(limit=30, include_content=True):
    posts = []
    seen = set()
    try:
        url = "https://pann.nate.com/talk"
        html = _request_html(url)
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/talk/" not in href or not re.search(r"/talk/\d+", href):
                continue
            title = _clean_text(a.get_text(" ", strip=True))
            if not title or len(title) < 5 or title.startswith("댓글"):
                continue
            full_url = urljoin("https://pann.nate.com", href)
            
            content_text = ""
            if include_content:
                try:
                    detail_html = _request_html(full_url)
                    detail_soup = BeautifulSoup(detail_html, "html.parser")
                    body_elem = detail_soup.select_one("#contentArea, .user_area")
                    if body_elem:
                        content_text = body_elem.get_text("\n", strip=True)
                except Exception as detail_err:
                    print(f"[!] Detail fetch error: {detail_err}")
                    
            candidate = _make_post("nate", title, full_url, rank=len(posts)+1, content=content_text)
            _append_unique(posts, seen, candidate, limit)
            if len(posts) >= limit:
                break
    except Exception as e:
        print(f"[!] Nate Pann crawl error: {e}")
    return posts


def crawl_nate_news(limit=30, include_content=True):
    posts = []
    seen = set()
    try:
        url = "https://news.nate.com/rank/"
        html = _request_html(url)
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/view/" not in href:
                continue
            title = _clean_text(a.get_text(" ", strip=True))
            if not title or len(title) < 10:
                continue
            full_url = urljoin("https://news.nate.com", href)
            if not full_url.startswith("http"):
                full_url = "https:" + full_url if full_url.startswith("//") else urljoin("https://news.nate.com", full_url)
            
            content_text = ""
            if include_content:
                try:
                    detail_html = _request_html(full_url)
                    detail_soup = BeautifulSoup(detail_html, "html.parser")
                    body_elem = detail_soup.select_one("#realImg, #articleCont, .article_txt, #articleBody, #artcBody")
                    if body_elem:
                        content_text = body_elem.get_text("\n", strip=True)
                except Exception as detail_err:
                    print(f"[!] Detail fetch error: {detail_err}")

            candidate = _make_post("nate_news", title, full_url, rank=len(posts)+1, content=content_text)
            _append_unique(posts, seen, candidate, limit)
            if len(posts) >= limit:
                break
    except Exception as e:
        print(f"[!] Nate News crawl error: {e}")
    return posts


def crawl_geeknews(limit=30, include_content=True):
    posts = []
    seen = set()
    try:
        url = "https://news.hada.io/"
        html = _request_html(url)
        soup = BeautifulSoup(html, "html.parser")
        for row in soup.select("div.topic_row"):
            # 1. Extract Title and URL from div.topictitle a
            title_a = row.select_one("div.topictitle a")
            if not title_a:
                continue
            
            href = title_a.get("href", "")
            if not href:
                continue
                
            title = _clean_text(title_a.get_text(" ", strip=True))
            if not title:
                continue
                
            full_url = urljoin("https://news.hada.io/", href)
            
            # 2. Get Detail URL for body scraping
            topic_id = row.get("data-topic-state-id")
            if not topic_id:
                # Fallback: parse from links inside the row
                for a in row.find_all("a", href=True):
                    a_href = a.get("href", "")
                    if a_href.startswith("topic?id="):
                        parts = a_href.split("?id=")
                        if len(parts) > 1:
                            topic_id = parts[1].split("&")[0]
                            break
            
            detail_url = f"https://news.hada.io/topic?id={topic_id}" if topic_id else full_url
            
            content_text = ""
            if include_content:
                try:
                    detail_html = _request_html(detail_url)
                    detail_soup = BeautifulSoup(detail_html, "html.parser")
                    body_elem = detail_soup.select_one("div.topic_contents, div.topic_desc, .topic_desc")
                    if body_elem:
                        content_text = body_elem.get_text("\n", strip=True)
                except Exception as detail_err:
                    print(f"[!] Detail fetch error for {detail_url}: {detail_err}")

            candidate = _make_post("geeknews", title, full_url, rank=len(posts)+1, content=content_text)
            _append_unique(posts, seen, candidate, limit)
            if len(posts) >= limit:
                break
    except Exception as e:
        print(f"[!] GeekNews crawl error: {e}")
    return posts


def crawl_shinsia(limit=10, include_content=True):
    """
    Crawls posts from shinsia82 Naver Blog RSS feed.
    """
    import xml.etree.ElementTree as ET
    posts = []
    seen = set()
    try:
        url = "https://rss.blog.naver.com/shinsia82.xml"
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"[!] Naver Blog RSS returned {response.status_code}")
            return []
            
        root = ET.fromstring(response.content)
        items = root.findall(".//item")
        
        for item in items:
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            
            title = _clean_text(title_el.text) if title_el is not None else ""
            link = link_el.text.strip() if link_el is not None else ""
            content = _clean_text(desc_el.text) if desc_el is not None and include_content else ""
            
            if not title or not link:
                continue
                
            candidate = _make_post("shinsia", title, link, rank=len(posts)+1, content=content)
            _append_unique(posts, seen, candidate, limit)
            if len(posts) >= limit:
                break
    except Exception as e:
        print(f"[!] Shinsia crawl error: {e}")
    return posts


def _crawl_inssider_category(category_cd: str, source_key: str, limit=10) -> list:
    import uuid
    posts = []
    seen = set()
    page = 1
    max_pages = max(1, (limit + 9) // 10)
    
    url_post = "https://inssider.kr/api/posts/list"
    guest_id = str(uuid.uuid4())
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "X-Guest-Id": guest_id,
        "Referer": f"https://inssider.kr/posts/{category_cd}",
        "Origin": "https://inssider.kr"
    }
    
    cookies = {
        "guest_id": guest_id
    }
    
    try:
        while len(posts) < limit and page <= max_pages:
            payload = {
                "categoryCd": category_cd,
                "currPage": page,
                "pageSize": 10,
                "sortType": "D"
            }
            response = requests.post(url_post, json=payload, headers=headers, cookies=cookies, timeout=15)
            if response.status_code != 200:
                print(f"[!] Inssider API error for category {category_cd}: HTTP {response.status_code}")
                break
                
            res_json = response.json()
            if res_json.get("status") != "SUCCESS":
                print(f"[!] Inssider API error for category {category_cd}: {res_json.get('message')}")
                break
                
            data = res_json.get("data", {})
            post_list = data.get("posts", [])
            if not post_list:
                break
                
            for item in post_list:
                post_seq = item.get("postSeq")
                title = item.get("postTitle", "")
                preview = item.get("previewContent", "")
                
                if not post_seq or not title:
                    continue
                    
                post_url = f"https://inssider.kr/posts/{category_cd}/{post_seq}"
                candidate = _make_post(source_key, title, post_url, rank=post_seq, content=preview)
                _append_unique(posts, seen, candidate, limit)
                
            page += 1
            
    except Exception as e:
        print(f"[!] Inssider crawl error for category {category_cd}: {e}")
        
    return posts


def crawl_inssider_couple(limit=10, include_content=False):
    return _crawl_inssider_category("003011", "inssider_couple", limit)


def crawl_inssider_job(limit=10, include_content=False):
    return _crawl_inssider_category("003001", "inssider_job", limit)


def crawl_inssider_politics(limit=10, include_content=False):
    return _crawl_inssider_category("003003", "inssider_politics", limit)


def crawl_inssider_humor(limit=10, include_content=False):
    return _crawl_inssider_category("003008", "inssider_humor", limit)


def crawl_inssider_lounge(limit=10, include_content=False):
    return _crawl_inssider_category("011001", "inssider_lounge", limit)


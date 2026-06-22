import os
import time
from datetime import datetime
from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional

import config
from src.storage import load_content_index, add_posts_to_storage, sanitize_filename
from src.crawler import (
    crawl_nate_pann,
    crawl_nate_news,
    crawl_geeknews,
    crawl_theqoo_hot,
    crawl_hn_best,
    crawl_ruliweb_best,
    crawl_todayhumor_humorbest,
    crawl_clien_park,
    crawl_yahoo_entertainment,
    crawl_mumsnet_aibu,
    crawl_reddit_subreddit,
    crawl_shinsia,
    crawl_inssider_couple,
    crawl_inssider_job,
    crawl_inssider_politics,
    crawl_inssider_humor,
    crawl_inssider_lounge,
    scrape_single_url,
    collect_hot_candidates,
)
from src.generator import FORMS, STYLES, generate_draft, generate_image_prompt

app = FastAPI(title="Trends_Copy Dashboard", version="2.0.0")

SOURCE_DISPLAY_NAMES = {
    "nate": "네이트판",
    "nate_news": "네이트뉴스",
    "geeknews": "긱뉴스",
    "shinsia": "신시아블로그",
    "theqoo": "더쿠",
    "hn_hot": "HN Hot",
    "hn_best": "HN Best",
    "ruliweb": "루리웹",
    "todayhumor": "오늘의유머",
    "clien": "클리앙",
    "yahoo_jp": "Yahoo Japan",
    "mumsnet": "Mumsnet",
    "reddit_boru": "Reddit BORU",
    "reddit_mc": "Reddit MC",
    "reddit_pr": "Reddit PR",
    "reddit_aita": "Reddit AITA",
    "reddit_rel": "Reddit RA",
    "reddit_aww": "Reddit Aww",
    "reddit_animals_jerks": "Reddit AnimalsJerks",
    "reddit_animals_derps": "Reddit AnimalsDerps",
    "reddit_animals_funny": "Reddit AnimalsFunny",
    "reddit_parenting_fails": "Reddit ParentingFails",
    "reddit_toddlers": "Reddit Toddlers",
    "reddit_children_falling": "Reddit ChildrenFalling",
    "reddit_kids_stupid": "Reddit KidsStupid",
    "inssider_couple": "인싸이더(연애)",
    "inssider_job": "인싸이더(직장)",
    "inssider_politics": "인싸이더(정치)",
    "inssider_humor": "인싸이더(유머)",
    "inssider_lounge": "인싸이더(라운지)",
    "manual": "직접입력",
}
SOURCE_HOME_URLS = {
    "nate": "https://pann.nate.com/",
    "nate_news": "https://news.nate.com/rank/",
    "geeknews": "https://news.hada.io/",
    "shinsia": "https://blog.naver.com/shinsia82",
    "theqoo": "https://theqoo.net/hot",
    "hn_hot": "https://news.ycombinator.com/",
    "hn_best": "https://news.ycombinator.com/best",
    "ruliweb": "https://bbs.ruliweb.com/best",
    "todayhumor": "https://www.todayhumor.co.kr/board/list.php?table=humorbest",
    "clien": "https://www.clien.net/service/board/park",
    "yahoo_jp": "https://news.yahoo.co.jp/ranking/comment/entertainment",
    "mumsnet": "https://www.mumsnet.com/talk/am_i_being_unreasonable",
    "reddit_boru": "https://www.reddit.com/r/BestofRedditorUpdates/hot/",
    "reddit_mc": "https://www.reddit.com/r/MaliciousCompliance/hot/",
    "reddit_pr": "https://www.reddit.com/r/ProRevenge/hot/",
    "reddit_aita": "https://www.reddit.com/r/AmItheAsshole/hot/",
    "reddit_rel": "https://www.reddit.com/r/relationship_advice/hot/",
    "reddit_aww": "https://www.reddit.com/r/aww/hot/",
    "reddit_animals_jerks": "https://www.reddit.com/r/AnimalsBeingJerks/hot/",
    "reddit_animals_derps": "https://www.reddit.com/r/AnimalsBeingDerps/hot/",
    "reddit_animals_funny": "https://www.reddit.com/r/AnimalsBeingFunny/hot/",
    "reddit_parenting_fails": "https://www.reddit.com/r/Parentingfails/hot/",
    "reddit_toddlers": "https://www.reddit.com/r/toddlers/hot/",
    "reddit_children_falling": "https://www.reddit.com/r/ChildrenFallingOver/hot/",
    "reddit_kids_stupid": "https://www.reddit.com/r/KidsAreFuckingStupid/hot/",
    "inssider_couple": "https://inssider.kr/posts/003011",
    "inssider_job": "https://inssider.kr/posts/003001",
    "inssider_politics": "https://inssider.kr/posts/003003",
    "inssider_humor": "https://inssider.kr/posts/003008",
    "inssider_lounge": "https://inssider.kr/posts/011001",
}
SOURCE_SAMPLE_FETCHERS = {
    "theqoo": lambda: crawl_theqoo_hot(limit=1, include_content=False),
    "hn_hot": lambda: crawl_hn_best(limit=1, include_content=False, feed="news"),
    "hn_best": lambda: crawl_hn_best(limit=1, include_content=False, feed="best"),
    "ruliweb": lambda: crawl_ruliweb_best(limit=1, include_content=False),
    "todayhumor": lambda: crawl_todayhumor_humorbest(limit=1, include_content=False),
    "clien": lambda: crawl_clien_park(limit=1, include_content=False),
    "yahoo_jp": lambda: crawl_yahoo_entertainment(limit=1, include_content=False),
    "mumsnet": lambda: crawl_mumsnet_aibu(limit=1, include_content=False),
    "reddit_boru": lambda: crawl_reddit_subreddit("BestofRedditorUpdates", limit=1, sort="hot"),
    "reddit_mc": lambda: crawl_reddit_subreddit("MaliciousCompliance", limit=1, sort="hot"),
    "reddit_pr": lambda: crawl_reddit_subreddit("ProRevenge", limit=1, sort="hot"),
    "reddit_aita": lambda: crawl_reddit_subreddit("AmItheAsshole", limit=1, sort="hot"),
    "reddit_rel": lambda: crawl_reddit_subreddit("relationship_advice", limit=1, sort="hot"),
    "reddit_aww": lambda: crawl_reddit_subreddit("aww", limit=1, sort="hot"),
    "reddit_animals_jerks": lambda: crawl_reddit_subreddit("AnimalsBeingJerks", limit=1, sort="hot"),
    "reddit_animals_derps": lambda: crawl_reddit_subreddit("AnimalsBeingDerps", limit=1, sort="hot"),
    "reddit_animals_funny": lambda: crawl_reddit_subreddit("AnimalsBeingFunny", limit=1, sort="hot"),
    "reddit_parenting_fails": lambda: crawl_reddit_subreddit("Parentingfails", limit=1, sort="hot"),
    "reddit_toddlers": lambda: crawl_reddit_subreddit("toddlers", limit=1, sort="hot"),
    "reddit_children_falling": lambda: crawl_reddit_subreddit("ChildrenFallingOver", limit=1, sort="hot"),
    "reddit_kids_stupid": lambda: crawl_reddit_subreddit("KidsAreFuckingStupid", limit=1, sort="hot"),
    "shinsia": lambda: crawl_shinsia(limit=1, include_content=False),
    "inssider_couple": lambda: crawl_inssider_couple(limit=1, include_content=False),
    "inssider_job": lambda: crawl_inssider_job(limit=1, include_content=False),
    "inssider_politics": lambda: crawl_inssider_politics(limit=1, include_content=False),
    "inssider_humor": lambda: crawl_inssider_humor(limit=1, include_content=False),
    "inssider_lounge": lambda: crawl_inssider_lounge(limit=1, include_content=False),
}

SOURCE_SAMPLE_CACHE = {"ts": 0.0, "value": []}
SOURCE_SAMPLE_CACHE_TTL = 300


def _build_source_samples():
    now = time.time()
    cached_sources = {item.get("source") for item in SOURCE_SAMPLE_CACHE["value"]}
    expected_sources = {source for source in SOURCE_DISPLAY_NAMES if source != "manual"}
    if SOURCE_SAMPLE_CACHE["value"] and (now - SOURCE_SAMPLE_CACHE["ts"]) < SOURCE_SAMPLE_CACHE_TTL and expected_sources.issubset(cached_sources):
        return SOURCE_SAMPLE_CACHE["value"]

    posts = collect_hot_candidates(limit=200)
    source_first = {}
    for post in posts:
        source = post.get("source")
        if source and source not in source_first:
            source_first[source] = post

    samples = []

    for source, label in SOURCE_DISPLAY_NAMES.items():
        if source == "manual":
            continue

        sample = source_first.get(source)

        samples.append({
            "source": source,
            "label": label,
            "home_url": SOURCE_HOME_URLS.get(source, ""),
            "title": (sample or {}).get("title", "수집 예시 없음"),
            "url": (sample or {}).get("url", SOURCE_HOME_URLS.get(source, "")),
            "status": "ok" if sample else "empty",
        })

    SOURCE_SAMPLE_CACHE["ts"] = now
    SOURCE_SAMPLE_CACHE["value"] = samples
    return samples

# 경로 보장
static_path = config.BASE_DIR / "static"
templates_path = config.BASE_DIR / "templates"
static_path.mkdir(exist_ok=True)
templates_path.mkdir(exist_ok=True)

# Jinja2 템플릿 환경 구성
templates = Jinja2Templates(directory=str(templates_path))

# 정적 파일 서빙 마운트 (누락된 마운트 설정 추가)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# 수집을 위한 Pydantic 스키마
class CollectionRequest(BaseModel):
    limit: Optional[int] = None
    source: str # nate, nate_news, geeknews, all

class ManualPostRequest(BaseModel):
    title: str
    source: str
    content: str
    url: Optional[str] = ""

class ScrapeUrlRequest(BaseModel):
    url: str

# 생성 변환을 위한 Pydantic 스키마 (다중 선택 대응)
class GenerateRequest(BaseModel):
    post_ids: List[str] # 다중선택 지원
    form_choice: str
    style_choices: List[str]
    extra_instruction: Optional[str] = ""
    custom_form: Optional[str] = None # 커스텀 양식 추가
    custom_style: Optional[str] = None # 커스텀 스타일 추가
    model_choice: Optional[str] = "auto" # 모델 선택 추가

class DirectGenerateRequest(BaseModel):
    url: Optional[str] = ""
    raw_text: Optional[str] = ""
    form_choice: str
    style_choices: List[str]
    extra_instruction: Optional[str] = ""
    custom_form: Optional[str] = None
    custom_style: Optional[str] = None
    model_choice: Optional[str] = "auto"

class SaveDraftRequest(BaseModel):
    draft_text: str
    post_ids: List[str]
    form_choice: str
    style_choices: List[str]

class ImagePromptRequest(BaseModel):
    draft_text: str
    theme_type: str
    prompt_mode: Optional[str] = "image"
    model_choice: Optional[str] = "auto" # 모델 선택 추가

class PresetItemRequest(BaseModel):
    id: str
    name: str
    desc: str

@app.get("/", response_class=HTMLResponse)
def read_dashboard(request: Request):
    """
    메인 대시보드 화면 렌더링
    """
    from src.generator import load_presets
    forms, styles, themes = load_presets()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "forms": forms,
            "styles": styles,
            "themes": themes,
            "local_qwen_url": config.LOCAL_QWEN_URL
        }
    )

@app.get("/api/posts")
def get_posts():
    """
    저장된 글감 리스트 반환
    """
    posts = load_content_index()
    return JSONResponse(content=posts)

@app.get("/api/source-samples")
def get_source_samples():
    """
    Return one example per source for the right-side site rail.
    """
    return JSONResponse(content={"sources": _build_source_samples()})

@app.get("/api/stats")
def get_stats():
    """
    글감 분석 및 시각화 데이터용 통계 반환
    """
    posts = load_content_index()
    total_count = len(posts)
    
    source_counts = {}
    date_counts = {}

    for p in posts:
        src = (p.get("source") or "").strip() or "unknown"
        source_counts[src] = source_counts.get(src, 0) + 1

        dt = (p.get("date") or "").strip()
        if dt:
            date_counts[dt] = date_counts.get(dt, 0) + 1

    sorted_dates = sorted(date_counts.items(), key=lambda x: x[0], reverse=True)[:5]
    chart_dates = [item[0] for item in reversed(sorted_dates)]
    chart_values = [item[1] for item in reversed(sorted_dates)]

    source_items = sorted(source_counts.items(), key=lambda item: (-item[1], item[0]))
    source_labels = [item[0] for item in source_items]
    source_values = [item[1] for item in source_items]

    return JSONResponse(content={
        "total": total_count,
        "nate_count": source_counts.get("nate", 0),
        "news_count": source_counts.get("nate_news", 0),
        "geek_count": source_counts.get("geeknews", 0),
        "source_breakdown": source_counts,
        "source_labels": source_labels,
        "source_values": source_values,
        "chart_dates": chart_dates,
        "chart_values": chart_values,
    })

@app.post("/api/collect")
def run_collection(req: CollectionRequest):
    """
    Collect hot/popular candidate titles and links.
    """
    limit = req.limit
    source = req.source
    posts = []
    
    try:
        if source in ["all", "hot"]:
            posts.extend(collect_hot_candidates(limit=limit))
        else:
            source_limit = limit if limit is not None else 10
            if source in ["nate", "legacy"]:
                posts.extend(crawl_nate_pann(limit=source_limit, include_content=False))
            if source in ["nate_news", "legacy"]:
                posts.extend(crawl_nate_news(limit=source_limit, include_content=False))
            if source in ["geeknews", "legacy"]:
                posts.extend(crawl_geeknews(limit=source_limit, include_content=False))
            if source in ["shinsia", "legacy"]:
                posts.extend(crawl_shinsia(limit=source_limit, include_content=True))
            if source == "inssider_couple":
                posts.extend(crawl_inssider_couple(limit=source_limit, include_content=False))
            if source == "inssider_job":
                posts.extend(crawl_inssider_job(limit=source_limit, include_content=False))
            if source == "inssider_politics":
                posts.extend(crawl_inssider_politics(limit=source_limit, include_content=False))
            if source == "inssider_humor":
                posts.extend(crawl_inssider_humor(limit=source_limit, include_content=False))
            if source == "inssider_lounge":
                posts.extend(crawl_inssider_lounge(limit=source_limit, include_content=False))
            
        added = add_posts_to_storage(posts)
        return JSONResponse(content={"status": "success", "crawled": len(posts), "added": added})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def resolve_post_file_path(original_path_str: str):
    if not original_path_str:
        return None
    from pathlib import Path
    p = Path(original_path_str)
    if p.exists():
        return p
    # Fallback 0-1: config.BODY_DIR
    fb = config.BODY_DIR / p.name
    if fb.exists():
        return fb
    # Fallback 0-2: config.RECONSTRUCTED_DIR
    fr = config.RECONSTRUCTED_DIR / p.name
    if fr.exists():
        return fr
    # Fallback 1: config.GENERATED_DIR
    f1 = config.GENERATED_DIR / p.name
    if f1.exists():
        return f1
    # Fallback 2: data/generated
    f2 = config.BASE_DIR / "data" / "generated" / p.name
    if f2.exists():
        return f2
    # Fallback 3: data/raw
    f3 = config.BASE_DIR / "data" / "raw" / p.name
    if f3.exists():
        return f3
    return None

@app.post("/api/generate")
def create_draft_api(req: GenerateRequest):
    """
    ?ㅼ쨷 湲媛먮뱾??議고솕濡?쾶 蹂묓빀/寃고빀?섏뿬 X 留욎땄??珥덉븞 ?먮룞 蹂??(?ㅽ듃由щ컢 諛섑솚)
    """
    index_list = load_content_index()
    selected_posts = [row for row in index_list if row["id"] in req.post_ids]
    
    if not selected_posts:
        raise HTTPException(status_code=404, detail="No selected posts were found.")
        
    try:
        merged_title = " / ".join([p["title"] for p in selected_posts])
        merged_contents = []
        
        for p in selected_posts:
            content_part = ""
            file_path = p.get("file_path", "")
            resolved_path = resolve_post_file_path(file_path) if file_path else None
            
            if resolved_path:
                try:
                    with open(resolved_path, "r", encoding="utf-8") as f:
                        markdown_content = f.read()
                    if "## 📌 원문 내용" in markdown_content:
                        content_part = markdown_content.split("## 📌 원문 내용")[-1].split("---")[0].strip()
                    elif "## 핵심 사실 관계" in markdown_content:
                        content_part = markdown_content.split("## 핵심 사실 관계")[-1].split("---")[0].strip()
                    else:
                        content_part = markdown_content
                except Exception:
                    content_part = ""
            
            if not content_part:
                content_part = (p.get("content") or "").strip()
            
            if not content_part:
                raise HTTPException(status_code=400, detail=f"글감 '{p['title']}'의 본문이 비어 있습니다. 대시보드 테이블에서 '본문 추출'을 먼저 진행해 주세요.")
            
            merged_contents.append(f"--- [Source: {p['source']}] ---\n{content_part}")
        
        final_merged_content = "\n\n".join(merged_contents)
        
        from src.generator import generate_draft_stream
        
        return StreamingResponse(
            generate_draft_stream(
                merged_title,
                final_merged_content,
                req.form_choice,
                req.style_choices,
                req.extra_instruction,
                custom_form=req.custom_form,
                custom_style=req.custom_style,
                model_choice=req.model_choice
            ),
            media_type="text/event-stream"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/generate-direct")
def create_draft_direct_api(req: DirectGenerateRequest):
    """
    [간편 변환] DB 저장 없이 URL 스크랩 또는 일반 입력 텍스트를 바로 X 맞춤형 초안으로 자동 변환 (스트리밍 반환)
    """
    try:
        title = "직접 입력 글감"
        content = ""
        
        # 1. URL이 입력되었으면 실시간 메모리 스크랩 진행
        if req.url and req.url.strip():
            scraped = scrape_single_url(req.url)
            title = scraped["title"]
            content = scraped["content"]
        # 2. 직접 텍스트가 입력되었으면 해당 텍스트 사용
        elif req.raw_text and req.raw_text.strip():
            content = req.raw_text.strip()
            # 첫 40글자를 잘라서 타이틀로 설정
            title = content.replace("\n", " ")
            if len(title) > 40:
                title = title[:40] + "..."
                
        if not content:
            raise HTTPException(status_code=400, detail="분석할 URL 혹은 본문 내용이 없습니다.")
            
        from src.generator import generate_draft_stream
        
        return StreamingResponse(
            generate_draft_stream(
                title,
                content,
                req.form_choice,
                req.style_choices,
                req.extra_instruction,
                custom_form=req.custom_form,
                custom_style=req.custom_style,
                model_choice=req.model_choice
            ),
            media_type="text/event-stream"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/save-draft")
def save_draft_api(req: SaveDraftRequest):
    """
    [API] 프리뷰 확인 후 완성된 초안을 수동으로 옵시디언 vault에 최종 저장
    """
    index_list = load_content_index()
    selected_posts = [row for row in index_list if row["id"] in req.post_ids]
    
    if not selected_posts:
        raise HTTPException(status_code=404, detail="선택하신 ID의 글감을 전혀 찾을 수 없습니다.")
        
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        safe_title = sanitize_filename(selected_posts[0]["title"])
        draft_filename = f"{today_str}_{selected_posts[0]['source']}_{safe_title}_merged_draft.md"
        draft_path = config.RECONSTRUCTED_DIR / draft_filename
        
        from src.generator import load_presets
        forms, styles = load_presets()
        form_name = forms.get(req.form_choice, ("자유 재구성", ""))[0]
        style_names = ", ".join([styles.get(sc, ("기본", ""))[0] for sc in req.style_choices])
        
        origins_str = ', '.join([f"[{p['title']}]({p['url']})" for p in selected_posts])
        sources_str = ', '.join([p['source'] for p in selected_posts])

        full_draft_file_content = f"""# [콘텐츠 초안 변환 카드 - 병합본] {selected_posts[0]['title']} 외 {len(selected_posts)-1}건

- **결합 원본들**: {origins_str}
- **출처/일시**: {sources_str} / {today_str}
- **설정 양식**: {form_name}
- **설정 스타일**: {style_names}
- **생성 일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 📝 콘텐츠 초안 내용

{req.draft_text}

---
*본 콘텐츠 초안 카드는 Trends_Copy의 템플릿 변환 파이프라인으로 구축되었습니다.*
"""
        with open(draft_path, "w", encoding="utf-8") as f:
            f.write(full_draft_file_content)
            
        return JSONResponse(content={
            "status": "success",
            "saved_path": str(draft_path.resolve())
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate-image-prompt")
def generate_image_prompt_api(req: ImagePromptRequest):
    """
    [API] 이미지/동영상 생성용 프롬프트 빌드
    """
    try:
        from src.generator import generate_image_prompt
        prompt, is_offline = generate_image_prompt(req.draft_text, req.theme_type, prompt_mode=req.prompt_mode, model_choice=req.model_choice)
        return JSONResponse(content={
            "status": "success",
            "prompt": prompt,
            "is_offline": is_offline
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/presets")
def get_presets_api():
    from src.generator import load_presets
    forms, styles, themes = load_presets()
    return JSONResponse(content={"forms": forms, "styles": styles, "themes": themes})

@app.post("/api/presets/form")
def save_form_preset(req: PresetItemRequest):
    from src.generator import load_presets, save_presets
    forms, styles, themes = load_presets()
    forms[req.id] = (req.name, req.desc)
    if save_presets(forms, styles, themes):
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="양식 저장에 실패했습니다.")

@app.delete("/api/presets/form/{form_id}")
def delete_form_preset(form_id: str):
    from src.generator import load_presets, save_presets
    forms, styles, themes = load_presets()
    if form_id in forms:
        del forms[form_id]
        if save_presets(forms, styles, themes):
            return {"status": "success"}
    raise HTTPException(status_code=500, detail="양식 삭제에 실패했습니다.")

@app.post("/api/presets/style")
def save_style_preset(req: PresetItemRequest):
    from src.generator import load_presets, save_presets
    forms, styles, themes = load_presets()
    styles[req.id] = (req.name, req.desc)
    if save_presets(forms, styles, themes):
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="스타일 저장에 실패했습니다.")

@app.delete("/api/presets/style/{style_id}")
def delete_style_preset(style_id: str):
    from src.generator import load_presets, save_presets
    forms, styles, themes = load_presets()
    if style_id in styles:
        del styles[style_id]
        if save_presets(forms, styles, themes):
            return {"status": "success"}
    raise HTTPException(status_code=500, detail="스타일 삭제에 실패했습니다.")

@app.post("/api/presets/theme")
def save_theme_preset(req: PresetItemRequest):
    from src.generator import load_presets, save_presets
    forms, styles, themes = load_presets()
    themes[req.id] = (req.name, req.desc)
    if save_presets(forms, styles, themes):
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="이미지 테마 저장에 실패했습니다.")

@app.delete("/api/presets/theme/{theme_id}")
def delete_theme_preset(theme_id: str):
    from src.generator import load_presets, save_presets
    forms, styles, themes = load_presets()
    if theme_id in themes:
        del themes[theme_id]
        if save_presets(forms, styles, themes):
            return {"status": "success"}
    raise HTTPException(status_code=500, detail="이미지 테마 삭제에 실패했습니다.")

@app.get("/api/view-file")
def view_file_api(path: Optional[str] = None, id: Optional[str] = None):
    import os
    import json
    
    post = None
    index_list = load_content_index()
    
    if id:
        matching_rows = [row for row in index_list if row["id"] == id]
        if matching_rows:
            post = matching_rows[0]
    elif path:
        matching_rows = [row for row in index_list if row["file_path"] == path]
        if matching_rows:
            post = matching_rows[0]
            
    if not post:
        raise HTTPException(status_code=404, detail="湲媛??뺣낫瑜?李얠쓣 ???놁뒿?덈떎.")
        
    resolved_path = resolve_post_file_path(post["file_path"])
    content = ""
    
    if resolved_path:
        try:
            with open(resolved_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            pass
            
    if not content and post.get("url"):
        try:
            scraped = scrape_single_url(post["url"])
            scraped_content = scraped.get("content", "")
            if scraped_content:
                content = f"""# {scraped.get('title', post['title'])}

- **URL**: {post['url']}
- **Source**: {post['source']}
- **Date**: {post['date']}

---

## Content

{scraped_content}
"""
        except Exception:
            pass
    try:
        escaped_content = json.dumps(content)
        return HTMLResponse(content=f"""
        <html>
        <head>
            <title>湲€媛??뚯씪 ?곸꽭 蹂닿린</title>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
            <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
            <style>
                body {{
                    background-color: #0b0f19;
                    color: #f3f4f6;
                    font-family: 'Inter', -apple-system, sans-serif;
                    padding: 40px 20px;
                    max-width: 800px;
                    margin: 0 auto;
                    line-height: 1.8;
                }}
                .card {{
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 16px;
                    padding: 40px;
                    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
                    backdrop-filter: blur(8px);
                }}
                h1, h2, h3 {{
                    color: #3b82f6;
                    margin-top: 24px;
                    margin-bottom: 12px;
                }}
                h1 {{
                    color: #8b5cf6;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                    padding-bottom: 12px;
                    font-size: 24px;
                    margin-top: 0;
                }}
                ul {{
                    padding-left: 20px;
                    margin-bottom: 16px;
                }}
                li {{
                    margin-bottom: 8px;
                }}
                hr {{
                    border: 0;
                    border-top: 1px solid rgba(255, 255, 255, 0.08);
                    margin: 24px 0;
                }}
                a {{
                    color: #3b82f6;
                    text-decoration: none;
                }}
                a:hover {{
                    text-decoration: underline;
                }}
                pre {{
                    background: rgba(0, 0, 0, 0.3);
                    padding: 16px;
                    border-radius: 8px;
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    overflow-x: auto;
                    font-family: monospace;
                    font-size: 13px;
                    white-space: pre-wrap;
                }}
            </style>
        </head>
        <body>
            <div class="card" id="content"></div>
            <script>
                document.getElementById('content').innerHTML = marked.parse({escaped_content});
            </script>
        </body>
        </html>
        """)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scrape-url")
def scrape_url_api(req: ScrapeUrlRequest):
    """
    [API] 원문 URL을 Gemini 기반 스크래퍼로 긁어와 제목/본문을 반환
    """
    try:
        if not req.url or not req.url.strip():
            raise HTTPException(status_code=400, detail="URL이 비어 있습니다.")

        scraped = scrape_single_url(req.url)
        return JSONResponse(content={
            "status": "success",
            "title": scraped.get("title", ""),
            "content": scraped.get("content", ""),
            "url": scraped.get("url", req.url),
            "source": scraped.get("source", "gemini_scrape"),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/posts/manual")
def add_manual_post(req: ManualPostRequest):
    """
    [API] 사용자가 수동으로 직접 긁어오거나 작성한 글감을 데이터베이스 및 옵시디언 vault에 동시 적재
    """
    try:
        from src.storage import add_posts_to_storage
        
        # URL이 없는 경우 고유 가상 URL 생성
        url = req.url.strip() if req.url else f"https://manual.entry/{int(datetime.now().timestamp())}"
        
        posts = [{
            "title": req.title.strip(),
            "content": req.content.strip(),
            "url": url,
            "source": req.source
        }]
        
        added = add_posts_to_storage(posts)
        if added > 0:
            return {"status": "success", "added": added}
        else:
            raise HTTPException(status_code=400, detail="이미 등록되었거나 중복된 원문 링크(URL)입니다.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class StyleExampleItem(BaseModel):
    format_key: str
    id: str
    content: str


class ExtractBodyRequest(BaseModel):
    post_id: str


@app.get("/api/style-library")
def get_style_library():
    import json
    if not config.STYLE_LIBRARY_FILE.exists():
        return JSONResponse(content={})
    try:
        with open(config.STYLE_LIBRARY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read style library: {e}")


@app.post("/api/style-library")
def save_style_example(item: StyleExampleItem):
    import json
    data = {}
    if config.STYLE_LIBRARY_FILE.exists():
        try:
            with open(config.STYLE_LIBRARY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
            
    if item.format_key not in data:
        data[item.format_key] = []
        
    examples = data[item.format_key]
    
    exists = False
    for ex in examples:
        if ex["id"] == item.id:
            ex["content"] = item.content
            exists = True
            break
            
    if not exists:
        examples.append({"id": item.id, "content": item.content})
        
    try:
        with open(config.STYLE_LIBRARY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/style-library/{format_key}/{example_id}")
def delete_style_example(format_key: str, example_id: str):
    import json
    if not config.STYLE_LIBRARY_FILE.exists():
        raise HTTPException(status_code=404, detail="Style library file not found.")
    try:
        with open(config.STYLE_LIBRARY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if format_key in data:
            data[format_key] = [ex for ex in data[format_key] if ex["id"] != example_id]
            
        with open(config.STYLE_LIBRARY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SavePostBodyRequest(BaseModel):
    post_id: str
    title: Optional[str] = None
    content: str


@app.post("/api/save-post-body")
def save_post_body_api(req: SavePostBodyRequest):
    try:
        from src.storage import load_content_index, save_content_index, sanitize_filename
        from src.processor import build_markdown_card
        import datetime as dt_mod
        
        index_list = load_content_index()
        target_post = None
        for row in index_list:
            if row["id"] == req.post_id:
                target_post = row
                break
                
        if not target_post:
            raise HTTPException(status_code=404, detail="Post not found in index.")
            
        title = req.title or target_post.get("title", "제목 없음")
        source = target_post.get("source", "unknown")
        url = target_post.get("url", "")
        
        # 1. 파일 이름 설정
        today_str = dt_mod.datetime.now().strftime("%Y-%m-%d")
        safe_title = sanitize_filename(title or url or req.post_id)
        filename = f"{today_str}_{source}_{safe_title}.md"
        markdown_path = config.BODY_DIR / filename
        
        # 2. 마크다운 빌드 및 디스크 저장
        markdown_content = build_markdown_card(title, source, today_str, url, req.content)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
        # 3. 로컬 인덱스에 파일 경로 및 content 업데이트
        target_post["file_path"] = str(markdown_path.resolve())
        target_post["content"] = req.content
        if req.title:
            target_post["title"] = req.title
            
        save_content_index(index_list)
        
        return {
            "status": "success",
            "file_path": str(markdown_path.resolve()),
            "title": title
        }
    except Exception as e:
        from src.generator import log_workbench
        log_workbench("error", "SAVE_POST_BODY_FAIL", f"postId: {req.post_id}, error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/extract-body")
def extract_post_body(req: ExtractBodyRequest):
    try:
        from src.storage import load_content_index, save_content_index
        from src.generator import _extract_structured_facts
        from src.processor import build_markdown_card
        import requests
        from bs4 import BeautifulSoup
        
        # 자체 이미지 MIME 타입 감지 로컬 함수 (imghdr 대체 - 파이썬 3.13 대응)
        def _detect_mime(content: bytes) -> str:
            if content.startswith(b'\x89PNG\r\n\x1a\n'):
                return "image/png"
            elif content.startswith(b'\xff\xd8\xff'):
                return "image/jpeg"
            elif content.startswith(b'GIF87a') or content.startswith(b'GIF89a'):
                return "image/gif"
            elif content.startswith(b'RIFF') and b'WEBP' in content[8:16]:
                return "image/webp"
            elif content.startswith(b'BM'):
                return "image/bmp"
            return None
            
        index_list = load_content_index()
        target_post = None
        for row in index_list:
            if row["id"] == req.post_id:
                target_post = row
                break
                
        if not target_post:
            raise HTTPException(status_code=404, detail="Post not found in index.")
            
        url = target_post.get("url", "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="Post does not have a valid URL.")
            
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code} when fetching URL")
            
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # 순차적 본문 셀렉터 탐색 (문서 최상위 body 중복매칭 회피)
        body_selectors = [
            "#contentArea",
            ".xe_content",
            ".rd_body",
            ".user_area",
            "#articleBody",
            "#artcBody",
            "#articleCont",
            ".article_txt",
            "div.topic_contents",
            "div.topic_desc",
            ".topic_desc",
            "article",
            "body"
        ]
        
        body_elem = None
        for sel in body_selectors:
            elem = soup.select_one(sel)
            if elem:
                body_elem = elem
                break
                
        if not body_elem:
            body_elem = soup
            
        for tag in body_elem(["script", "style", "nav", "footer", "header", "iframe"]):
            try:
                tag.decompose()
            except Exception:
                pass
                
        raw_text = body_elem.get_text("\n", strip=True)
        
        # 이미지 파싱 및 base64 인코딩 (최대 5개)
        import base64
        from urllib.parse import urljoin
        images = []
        img_tags = body_elem.find_all("img")
        
        max_imgs = 5
        img_count = 0
        for img in img_tags:
            if img_count >= max_imgs:
                break
            src = img.get("src", "").strip()
            if not src:
                continue
                
            img_url = urljoin(url, src)
            url_lower = img_url.lower()
            if any(k in url_lower for k in ["icon", "logo", "ad_", "advertisement", "share", "banner", "btn", "button", "emoji", "avatar"]):
                continue
                
            try:
                img_resp = requests.get(img_url, headers=headers, timeout=5)
                if img_resp.status_code == 200:
                    content_length = len(img_resp.content)
                    if content_length < 10000:  # 10KB 미만 무시
                        continue
                        
                    mime_type = _detect_mime(img_resp.content)
                    if not mime_type:
                        # 폴백
                        mime_type = img_resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
                        if "image" not in mime_type:
                            continue
                            
                    b64 = base64.b64encode(img_resp.content).decode("utf-8")
                    images.append({
                        "mime_type": mime_type,
                        "base64_data": b64
                    })
                    img_count += 1
            except Exception:
                pass
        
        title = target_post.get("title", "제목 없음")
        
        from src.processor import build_markdown_card, clean_content
        from src.generator import _extract_image_text_via_gemini
        
        # 1. 본문 HTML 텍스트 정제 (원문 그대로 보존)
        cleaned_text = clean_content(raw_text)
        
        # 2. 이미지가 존재하면 Gemini 멀티모달 API로 이미지 내 텍스트 전체 추출 (상세 전사)
        image_ocr_text = ""
        if images:
            image_ocr_text = _extract_image_text_via_gemini(images, model_choice="gemini")
            
        # 3. 본문과 이미지 텍스트 결합
        if image_ocr_text:
            combined_content = f"{cleaned_text}\n\n--- [🖼️ 이미지 내 텍스트 추출 데이터 (Gemini)] ---\n{image_ocr_text}"
        else:
            combined_content = cleaned_text
            
        today_str = datetime.now().strftime("%Y-%m-%d")
        source = target_post.get("source", "unknown")
        safe_title = sanitize_filename(title or url)
        filename = f"{today_str}_{source}_{safe_title}.md"
        markdown_path = config.BODY_DIR / filename
        
        markdown_content = build_markdown_card(title, source, today_str, url, combined_content)
        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
        target_post["content"] = combined_content
        target_post["file_path"] = str(markdown_path.resolve())
        target_post["date"] = today_str
        
        save_content_index(index_list)
        
        return {"status": "success", "content": combined_content, "file_path": target_post["file_path"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CommentCardRequest(BaseModel):
    post_id: str
    model_choice: Optional[str] = "gemini"


@app.post("/api/generate-comment-card")
def generate_comment_card_api(req: CommentCardRequest):
    import shutil
    import datetime as dt_mod
    from src.storage import load_content_index, sanitize_filename
    from src.generator import generate_character_comments, draw_character_card
    
    index_list = load_content_index()
    target_post = None
    for row in index_list:
        if row["id"] == req.post_id:
            target_post = row
            break
            
    if not target_post:
        raise HTTPException(status_code=404, detail="글감을 찾을 수 없습니다.")
        
    facts_content = target_post.get("content", "").strip()
    if not facts_content:
        raise HTTPException(status_code=400, detail="본문 추출이 먼저 완료되어야 합니다. 대시보드에서 '본문 추출'을 클릭해 주세요.")
        
    title = target_post.get("title", "제목 없음")
    source = target_post.get("source", "unknown")
    
    try:
        # 1. 캐릭터 댓글 생성
        card_data = generate_character_comments(title, facts_content, model_choice=req.model_choice)
        
        # 2. 이미지 파일명 및 저장 경로 설정
        import hashlib
        today_str = dt_mod.datetime.now().strftime("%Y-%m-%d")
        title_hash = hashlib.md5(title.encode('utf-8')).hexdigest()[:12]
        filename = f"{today_str}_{source}_{title_hash}_comment_card.png"
        
        # static 서빙 디렉토리에 바로 생성 (옵시디언 vault 자동 저장 제거)
        static_card_dir = config.BASE_DIR / "static" / "cards"
        static_card_dir.mkdir(parents=True, exist_ok=True)
        output_path = static_card_dir / filename
        
        # 3. 드로잉 및 파일 쓰기
        draw_character_card(
            title=card_data.get("title", title),
            summary=card_data.get("summary", ""),
            comments=card_data.get("comments", {}),
            output_path=output_path
        )
        
        relative_web_path = f"/static/cards/{filename}"
        
        return {
            "status": "success",
            "image_url": relative_web_path,
            "file_path": str(output_path.resolve()),
            "card_data": card_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CommentCardFromTextRequest(BaseModel):
    text: str
    title: Optional[str] = "콘텐츠 초안"
    post_ids: Optional[List[str]] = []
    model_choice: Optional[str] = "gemini"


@app.post("/api/generate-comment-card-from-text")
def generate_comment_card_from_text_api(req: CommentCardFromTextRequest):
    import shutil
    import datetime as dt_mod
    from src.storage import load_content_index, sanitize_filename
    from src.generator import generate_character_comments_from_draft, draw_character_card
    
    title = req.title or "콘텐츠 초안"
    source = "manual"
    
    # 1. 만약 post_ids가 주어지면 원본 글 제목과 소스를 찾아서 사용
    if req.post_ids:
        index_list = load_content_index()
        selected_posts = [row for row in index_list if row["id"] in req.post_ids]
        if selected_posts:
            title = selected_posts[0].get("title", title)
            source = selected_posts[0].get("source", "unknown")
            
    try:
        # 2. 캐릭터 댓글 및 요약문 생성
        card_data = generate_character_comments_from_draft(title, req.text, model_choice=req.model_choice)
        
        # 3. 이미지 저장 경로 설정
        import hashlib
        today_str = dt_mod.datetime.now().strftime("%Y-%m-%d")
        title_hash = hashlib.md5(title.encode('utf-8')).hexdigest()[:12]
        filename = f"{today_str}_draft_{source}_{title_hash}_comment_card.png"
        
        # static 서빙 디렉토리에 바로 생성 (옵시디언 vault 자동 저장 제거)
        static_card_dir = config.BASE_DIR / "static" / "cards"
        static_card_dir.mkdir(parents=True, exist_ok=True)
        output_path = static_card_dir / filename
        
        # 4. 카드 드로잉
        draw_character_card(
            title=card_data.get("title", title),
            summary=card_data.get("summary", ""),
            comments=card_data.get("comments", {}),
            output_path=output_path
        )
        
        relative_web_path = f"/static/cards/{filename}"
        
        return {
            "status": "success",
            "image_url": relative_web_path,
            "file_path": str(output_path.resolve()),
            "card_data": card_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DirectCommentCardRequest(BaseModel):
    title: str
    summary: str
    binnyang: str
    kkamak: str
    heotgae: str


@app.post("/api/generate-comment-card-direct")
def generate_comment_card_direct_api(req: DirectCommentCardRequest):
    import shutil
    import datetime as dt_mod
    from src.storage import sanitize_filename
    from src.generator import draw_character_card
    
    try:
        # comments dictionary structure for the drawing function
        comments = {
            "binnyang": req.binnyang,
            "kkamak": req.kkamak,
            "heotgae": req.heotgae
        }
        
        # Determine unique filename based on the title
        import hashlib
        today_str = dt_mod.datetime.now().strftime("%Y-%m-%d")
        title_hash = hashlib.md5(req.title.encode('utf-8')).hexdigest()[:12]
        filename = f"{today_str}_direct_{title_hash}_comment_card.png"
        
        # static 서빙 디렉토리에 바로 생성 (옵시디언 vault 자동 저장 제거)
        static_card_dir = config.BASE_DIR / "static" / "cards"
        static_card_dir.mkdir(parents=True, exist_ok=True)
        output_path = static_card_dir / filename
        
        # Render the card image
        draw_character_card(
            title=req.title,
            summary=req.summary,
            comments=comments,
            output_path=output_path
        )
        
        relative_web_path = f"/static/cards/{filename}"
        
        return {
            "status": "success",
            "image_url": relative_web_path,
            "file_path": str(output_path.resolve())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload-temp-image")
async def upload_temp_image(file: UploadFile = File(...)):
    import uuid
    import shutil
    from pathlib import Path
    try:
        upload_dir = config.BASE_DIR / "static" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        ext = Path(file.filename).suffix
        if not ext:
            ext = ".png"
        filename = f"temp_{uuid.uuid4().hex}{ext}"
        filepath = upload_dir / filename
        
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        relative_url = f"/static/uploads/{filename}"
        return {"status": "success", "image_url": relative_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DirectStoryCardRequest(BaseModel):
    title: str
    text: str
    image_url: Optional[str] = None
    auto_search_keyword: Optional[str] = None
    img_scale: Optional[float] = 1.0
    img_offset_x: Optional[int] = 0
    img_offset_y: Optional[int] = 0


@app.post("/api/generate-story-card-direct")
def generate_story_card_direct_api(req: DirectStoryCardRequest):
    import shutil
    import datetime as dt_mod
    from src.storage import sanitize_filename
    from src.generator import draw_story_card, search_web_image
    
    try:
        image_url = req.image_url
        if not image_url and req.auto_search_keyword:
            searched_url = search_web_image(req.auto_search_keyword)
            if searched_url:
                image_url = searched_url
                print(f"[AI Auto Image Search] Keyword '{req.auto_search_keyword}' resolved to: {image_url}")
            else:
                print(f"[AI Auto Image Search] Keyword '{req.auto_search_keyword}' search failed.")

        import hashlib
        today_str = dt_mod.datetime.now().strftime("%Y-%m-%d")
        title_hash = hashlib.md5(req.title.encode('utf-8')).hexdigest()[:12]
        filename = f"{today_str}_direct_{title_hash}_story_card.png"
        
        # static 서빙 디렉토리에 생성 (대시보드 실시간 프리뷰용)
        static_card_dir = config.BASE_DIR / "static" / "cards"
        static_card_dir.mkdir(parents=True, exist_ok=True)
        output_path = static_card_dir / filename
        
        draw_story_card(
            text=req.text,
            image_url=image_url,
            output_path=output_path,
            img_scale=req.img_scale,
            img_offset_x=req.img_offset_x,
            img_offset_y=req.img_offset_y
        )
        
        # 옵시디언 본문재구성 폴더 백업 저장 (유저 원래 아랫부분 소스코드 기능 복구)
        try:
            obsidian_output_path = config.RECONSTRUCTED_DIR / filename
            shutil.copy2(output_path, obsidian_output_path)
            print(f"[Backup] Copied story card to Obsidian: {obsidian_output_path}")
        except Exception as e:
            print(f"[Backup Warning] Obsidian save failed: {e}")
            
        relative_web_path = f"/static/cards/{filename}"
        
        return {
            "status": "success",
            "image_url": relative_web_path,
            "file_path": str(output_path.resolve())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- X (Twitter) Scheduled Posts API ---

class CreateScheduleRequest(BaseModel):
    text: str
    scheduled_at: str

class UpdateScheduleRequest(BaseModel):
    text: Optional[str] = None
    scheduled_at: Optional[str] = None
    status: Optional[str] = None

@app.get("/api/schedule")
def get_schedule_api(start: Optional[str] = None, end: Optional[str] = None):
    from src.scheduler import get_scheduled_tweets
    return get_scheduled_tweets(start, end)

@app.post("/api/schedule")
def create_schedule_api(req: CreateScheduleRequest):
    from src.scheduler import add_scheduled_tweet
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Tweet content cannot be empty")
    new_id = add_scheduled_tweet(req.text, req.scheduled_at)
    if new_id is None:
        raise HTTPException(status_code=500, detail="Failed to save scheduled tweet")
    return {"status": "success", "id": new_id}

@app.put("/api/schedule/{post_id}")
def update_schedule_api(post_id: int, req: UpdateScheduleRequest):
    from src.scheduler import update_scheduled_tweet
    success = update_scheduled_tweet(
        post_id,
        text=req.text,
        scheduled_at=req.scheduled_at,
        status=req.status
    )
    if not success:
        raise HTTPException(status_code=404, detail="Scheduled tweet not found or no changes made")
    return {"status": "success"}

@app.delete("/api/schedule/{post_id}")
def delete_schedule_api(post_id: int):
    from src.scheduler import delete_scheduled_tweet
    success = delete_scheduled_tweet(post_id)
    if not success:
        raise HTTPException(status_code=404, detail="Scheduled tweet not found")
    return {"status": "success"}

@app.post("/api/schedule/{post_id}/post_now")
def post_now_api(post_id: int):
    from src.scheduler import get_scheduled_tweet, post_to_x, update_scheduled_tweet
    tweet = get_scheduled_tweet(post_id)
    if not tweet:
        raise HTTPException(status_code=404, detail="Scheduled tweet not found")
    
    update_scheduled_tweet(post_id, status="posting")
    res = post_to_x(tweet["text"])
    if res["success"]:
        update_scheduled_tweet(
            post_id,
            status="posted",
            tweet_id=res["tweet_id"],
            error_message=None
        )
        return {"status": "success", "tweet_id": res["tweet_id"]}
    else:
        update_scheduled_tweet(
            post_id,
            status="failed",
            error_message=res.get("error", "Unknown error")
        )
        raise HTTPException(status_code=500, detail=res.get("error", "X API posting failed"))

@app.on_event("startup")
def startup_event():
    from src.scheduler import start_scheduler
    start_scheduler()

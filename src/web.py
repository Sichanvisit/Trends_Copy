import os
from datetime import datetime
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional

import config
from src.storage import load_content_index, add_posts_to_storage, sanitize_filename
from src.crawler import crawl_nate_pann, crawl_nate_news, crawl_geeknews
from src.generator import FORMS, STYLES, generate_draft, generate_image_prompt

app = FastAPI(title="X Content Workbench Dashboard", version="2.0.0")

# 경로 보장
static_path = config.BASE_DIR / "static"
templates_path = config.BASE_DIR / "templates"
static_path.mkdir(exist_ok=True)
templates_path.mkdir(exist_ok=True)

# Jinja2 템플릿 환경 구성
templates = Jinja2Templates(directory=str(templates_path))

# 수집을 위한 Pydantic 스키마
class CollectionRequest(BaseModel):
    limit: Optional[int] = 5
    source: str # nate, nate_news, geeknews, all

class ManualPostRequest(BaseModel):
    title: str
    source: str
    content: str
    url: Optional[str] = ""

# 생성 변환을 위한 Pydantic 스키마 (다중 선택 대응)
class GenerateRequest(BaseModel):
    post_ids: List[str] # 다중선택 지원
    form_choice: str
    style_choices: List[str]
    extra_instruction: Optional[str] = ""
    custom_form: Optional[str] = None # 커스텀 양식 추가
    custom_style: Optional[str] = None # 커스텀 스타일 추가

class SaveDraftRequest(BaseModel):
    draft_text: str
    post_ids: List[str]
    form_choice: str
    style_choices: List[str]

class ImagePromptRequest(BaseModel):
    draft_text: str
    theme_type: str
    prompt_mode: Optional[str] = "image"

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
    return templates.TemplateResponse("index.html", {
        "request": request,
        "forms": forms,
        "styles": styles,
        "themes": themes,
        "local_qwen_url": config.LOCAL_QWEN_URL
    })

@app.get("/api/posts")
def get_posts():
    """
    저장된 글감 리스트 반환
    """
    posts = load_content_index()
    return JSONResponse(content=posts)

@app.get("/api/stats")
def get_stats():
    """
    글감 분석 및 시각화 데이터용 통계 반환
    """
    posts = load_content_index()
    total_count = len(posts)
    
    # 출처별 분포 계산
    source_counts = {"nate": 0, "nate_news": 0, "geeknews": 0}
    for p in posts:
        src = p.get("source", "")
        if src in source_counts:
            source_counts[src] += 1
            
    # 최근 5일 등록 추이 가공
    date_counts = {}
    for p in posts:
        dt = p.get("date", "")
        if dt:
            date_counts[dt] = date_counts.get(dt, 0) + 1
            
    # 최근 5일 정렬
    sorted_dates = sorted(date_counts.items(), key=lambda x: x[0], reverse=True)[:5]
    chart_dates = [item[0] for item in reversed(sorted_dates)]
    chart_values = [item[1] for item in reversed(sorted_dates)]
    
    return JSONResponse(content={
        "total": total_count,
        "nate_count": source_counts["nate"],
        "news_count": source_counts["nate_news"],
        "geek_count": source_counts["geeknews"],
        "chart_dates": chart_dates,
        "chart_values": chart_values
    })

@app.post("/api/collect")
def run_collection(req: CollectionRequest):
    """
    실시간 통합 크롤링 강제 기동
    """
    limit = req.limit or 5
    source = req.source
    posts = []
    
    try:
        if source in ["nate", "all"]:
            posts.extend(crawl_nate_pann(limit=limit))
        if source in ["nate_news", "all"]:
            posts.extend(crawl_nate_news(limit=limit))
        if source in ["geeknews", "all"]:
            posts.extend(crawl_geeknews(limit=limit))
            
        added = add_posts_to_storage(posts)
        return JSONResponse(content={"status": "success", "crawled": len(posts), "added": added})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate")
def create_draft_api(req: GenerateRequest):
    """
    다중 글감들을 조화롭게 병합/결합하여 X 맞춤형 초안 자동 변환 (자동 저장 없음)
    """
    index_list = load_content_index()
    selected_posts = [row for row in index_list if row["id"] in req.post_ids]
    
    if not selected_posts:
        raise HTTPException(status_code=404, detail="선택하신 ID의 글감을 전혀 찾을 수 없습니다.")
        
    try:
        # 다중 글감 병합 가공
        merged_title = " / ".join([p["title"] for p in selected_posts])
        
        merged_contents = []
        for p in selected_posts:
            file_path = p["file_path"]
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    markdown_content = f.read()
                content_part = markdown_content
                if "## 📌 원문 내용" in markdown_content:
                    content_part = markdown_content.split("## 📌 원문 내용")[-1].split("---")[0].strip()
                merged_contents.append(f"--- [글감 출처: {p['source']}] ---\n{content_part}")
                
        final_merged_content = "\n\n".join(merged_contents)
        
        # 초안 변환 가동 (커스텀 Form/Style 지원)
        draft_text, is_offline = generate_draft(
            merged_title,
            final_merged_content,
            req.form_choice,
            req.style_choices,
            req.extra_instruction,
            custom_form=req.custom_form,
            custom_style=req.custom_style
        )
        
        return JSONResponse(content={
            "status": "success",
            "draft": draft_text,
            "is_offline": is_offline
        })
        
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
        draft_filename = f"{today_str}_{selected_posts[0]['source']}_{safe_title}_x_merged_draft.md"
        draft_path = config.GENERATED_DIR / draft_filename
        
        from src.generator import load_presets
        forms, styles = load_presets()
        form_name = forms.get(req.form_choice, ("자유 재구성", ""))[0]
        style_names = ", ".join([styles.get(sc, ("기본", ""))[0] for sc in req.style_choices])
        
        origins_str = ', '.join([f"[{p['title']}]({p['url']})" for p in selected_posts])
        sources_str = ', '.join([p['source'] for p in selected_posts])

        full_draft_file_content = f"""# [X 초안 변환 카드 - 병합본] {selected_posts[0]['title']} 외 {len(selected_posts)-1}건

- **결합 원본들**: {origins_str}
- **출처/일시**: {sources_str} / {today_str}
- **설정 양식**: {form_name}
- **설정 스타일**: {style_names}
- **생성 일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 📝 X 게시글 초안 내용

{req.draft_text}

---
*본 X 초안 카드는 X Content Workbench의 템플릿 변환 파이프라인으로 구축되었습니다.*
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
        prompt, is_offline = generate_image_prompt(req.draft_text, req.theme_type, prompt_mode=req.prompt_mode)
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
def view_file_api(path: str):
    import os
    import json
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # marked.js CDN을 통해 Markdown 파일을 미려한 HTML 카드로 동적 변환
        escaped_content = json.dumps(content)
        return HTMLResponse(content=f"""
        <html>
        <head>
            <title>글감 파일 상세 보기</title>
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



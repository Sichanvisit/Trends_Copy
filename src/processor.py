import re

def clean_content(text):
    """
    본문 텍스트에서 광고 영역, 불필요한 공백, 저작권 문구, 댓글 잔재 등을 제거합니다.
    """
    if not text:
        return ""
        
    # 광고 제거 패턴
    ad_patterns = [
        r"무단전재\s*&\s*재배포\s*금지",
        r"Copyrights\s*ⓒ.*All\s*rights\s*reserved",
        r"▶\s*네이버\s*에서\s*.*구독하기",
        r"▶\s*가장\s*빠른\s*뉴스\s*.*구독",
        r"\[기사제보\s*및\s*보도자료\]",
        r"기사제보\s*:\s*.*",
        r"※\s*실시간\s*인기\s*댓글\s*보기",
        r"본문\s*내용\s*.*광고",
        r"AD\s*▼",
        r"광고\s*영역",
        r"스폰서\s*링크",
    ]
    
    cleaned = text
    for pattern in ad_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        
    # 너무 많은 빈 줄(2개 연속 초과) 단일 개행으로 압축
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    
    # 앞뒤 불필요 공백 제거
    cleaned = cleaned.strip()
    
    return cleaned

def build_markdown_card(title, source, date, url, content):
    """
    정제된 글감을 예쁘게 가공된 Markdown 카드 포맷으로 작성
    """
    if source == "nate":
        source_name = "네이트판"
    elif source == "nate_news":
        source_name = "네이트 뉴스"
    elif source == "geeknews":
        source_name = "GeekNews"
    else:
        source_name = source
    
    # 본문이 너무 길면 상위 15라인 정도 요약 표시를 위해 일부 슬라이스 구성 가능
    # (여기서는 원문 전체 보존하되 보기 좋은 레이아웃 형성)
    card_template = f"""# [글감 카드] {title}

- **출처**: {source_name} ({source})
- **수집일**: {date}
- **원문 링크**: {url}

---

## 📌 원문 내용

{content}

---
*본 카드는 X Content Workbench에 의해 자동으로 정제 및 보존 처리된 글감입니다.*
"""
    return card_template

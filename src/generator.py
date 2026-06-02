import os
import datetime
import requests
from openai import OpenAI
import config
import re

import json
from pathlib import Path

def clean_thinking_process(text: str) -> str:
    if not text:
        return ""
    
    # 1. <think>...</think> 태그 및 미완성 태그 내용 일괄 제거
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    cleaned = re.sub(r'<think>.*', '', cleaned, flags=re.DOTALL)
    
    # 2. 모델이 출력한 메타 지문(Critique, Iteration, Refining, Draft, Wait, Polish, Version 등)을 기준으로 나누어 최하단 최종 블록 추출
    meta_pattern = r'(?im)^\s*(?:\d+\.\s*)?[\*\-\s]*(?:critique|iteration|refining|draft|final\s*version|final\s*draft|wait|polish|version|step\s*\d+)\b.*$'
    
    parts = re.split(meta_pattern, cleaned)
    if len(parts) > 1:
        # 가장 아래쪽 조각부터 역순으로 탐색하여 실제 본문이 들어있는 조각 찾기
        for part in reversed(parts):
            candidate = part.strip()
            # 마크다운 부호 및 빈 줄 제거 후 글자 수가 어느 정도 되는 조각 선택
            candidate = re.sub(r'^[:\*\-\s\d\.]+', '', candidate)
            if len(candidate) > 15:
                cleaned = part.strip()
                break

    # 3. 드래프트 시도용 헤더 라인 제거 (예: *Draft:* 등 분리 후 남은 단독 타이틀 제거)
    cleaned = re.sub(r'(?im)^(?:\*?\s*(?:critique|iteration|refining|draft|final\s*version|final\s*draft|wait|polish|version|step\s*\d+)[:\*\-\s]+.*$)', '', cleaned)
    
    # 4. "Thinking Process:" 또는 "[AI 생각 과정" 으로 시작하는 블록을 감지하여 통째로 필터링
    lines = cleaned.split("\n")
    filtered_lines = []
    skip_mode = False
    
    for line in lines:
        stripped = line.strip()
        
        # 생각 과정의 시작을 알리는 헤더 감지
        if (stripped.lower().startswith("thinking process:") or 
            stripped.lower().startswith("[ai 생각 과정") or
            "thinking process" in stripped.lower() or
            stripped.startswith("### 생각 과정") or
            stripped.startswith("### Thought")):
            skip_mode = True
            continue
        
        # 생각 과정 내부의 글머리 기호들 스킵
        if skip_mode:
            # 생각 과정 본문이 끝났다고 판단하는 기준 (보통 빈 줄 이후 일반 문장 시작 또는 구분선)
            if stripped.startswith("---") or stripped.startswith("==="):
                skip_mode = False
                continue
            # 일반 텍스트 문단이 나오면 생각 과정 블록이 끝난 것으로 판단
            if stripped and not (stripped.startswith("*") or stripped.startswith("-") or stripped.startswith(">") or 
                                (len(stripped) > 1 and stripped[0].isdigit() and stripped[1] in [".", ")", ":"])):
                skip_mode = False
            else:
                # 글머리 기호 형태의 생각 과정 단계들은 스킵
                continue
                
        filtered_lines.append(line)
        
    cleaned = "\n".join(filtered_lines).strip()
    
    # 5. 영어로 적혀있는 가이드/메타생각 라인들이 문서 시작 부분에 나타나면 제거
    lines = cleaned.split("\n")
    start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        has_korean = any(0xAC00 <= ord(char) <= 0xD7A3 or 0x3130 <= ord(char) <= 0x318F for char in stripped)
        if not has_korean and len(stripped) > 5 and not re.match(r'^\d+\.', stripped):
            start_idx = i + 1
        else:
            break
            
    cleaned = "\n".join(lines[start_idx:]).strip()
    
    # 혹시 남아있을 수 있는 생각 과정 잔재 제거
    cleaned = re.sub(r'(?i)thinking process:.*?\n\n', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'\[AI 생각 과정.*?\]\n', '', cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip()


# 가용 양식(Forms) 및 스타일(Styles) 기본값 정의
DEFAULT_FORMS = {
    "1": ("현실공감 독백형", "지시사항: 자신의 경험을 담담히 독백하며 읽는 이의 깊은 현실 공감을 유도하는 구조입니다. AI에게 '과거 경험에 기반하여 담담하고 사색적인 독백조로 구성하고 문단을 넉넉히 비워 가독성을 극대화해라'라는 정밀 프롬프트가 주입됩니다."),
    "2": ("대화형 단막극", "지시사항: 대화체(A: B:)를 사용하여 상황을 유머러스하거나 직관적으로 요약하는 극작 형태입니다. AI에게 '상황의 모순점을 A:와 B:의 가상 대화 플로우로 구성하고, 마지막 행에 날카로운 관찰평 한 줄을 덧붙여라'라는 프롬프트가 실행됩니다."),
    "3": ("구축 로그형", "지시사항: 시작부터 시행착오, 깨달음에 이르는 과정을 순차적인 타임라인 형식으로 정리한 구조입니다. AI에게 '1. 발단, 2. 전개, 3. 깨달음, 4. 결론으로 기승전결 번호를 매겨 빌드 일지 형식으로 정렬해라'라는 구조적 프롬프트가 작동합니다."),
    "4": ("짧은 시/문학형", "지시사항: 감정을 낭만적이거나 깊이 있게 압축하여 마치 시처럼 호흡을 짧게 가져가는 기법입니다. AI에게 '감정선을 극대화하고 쓸데없는 수식을 배제하며 가독성 높은 문학적 행갈이 시 형식으로 조각해라'라는 시적 프롬프트가 적용됩니다."),
    "5": ("자유 재구성", "지시사항: 규격화된 틀 없이 자유롭게 원문의 핵심을 X 포맷에 녹여내는 스타일입니다. AI에게 '인위적인 틀을 전혀 쓰지 말고, 오직 원문의 핵심을 트위터 유저들이 공감하기 가장 쉬운 280자 트윗으로 요약해라'라고 지시합니다.")
}

DEFAULT_STYLES = {
    "1": ("사회풍자형", "지시사항: 사회의 부조리나 세태의 모순을 날카롭고 시니컬하게 짚어내는 문체입니다. AI에게 '사회의 모순을 드러내기 위해 겉으로는 담담하게 포장하되 속으로는 날카롭게 찌르는 반어법과 풍자적 어조를 사용해라'라고 지시합니다."),
    "2": ("인간심리 관찰형", "지시사항: 사소한 행동에서 사람의 숨은 욕망이나 본성을 정밀하게 투사하는 시각입니다. AI에게 '원문에 나타난 인물들의 대화나 행위 이면의 속마음과 세밀한 본능적 동기를 투과하듯 묘사해라'라고 지시합니다."),
    "3": ("시대관찰형", "지시사항: 요즘 세대의 트렌드나 달라진 라이프스타일을 거시적으로 조망하는 태도입니다. AI에게 '현대 사회 세태와 유행의 흐름을 통찰하는 제3의 분석가적 시점에서 객관적으로 사건을 조망해라'라고 지시합니다."),
    "4": ("블랙코미디형", "지시사항: 냉소적인 헛웃음과 유머를 믹스하여 뼈 있는 웃음을 주는 스타일입니다. AI에게 '우스꽝스럽고 비극적인 상황의 모순을 결합하여 가벼운 실소를 자아내고 여운을 남겨라'라고 지시합니다."),
    "5": ("감정 압축형", "지시사항: 군더더기 수식어를 전부 걷어내고 가장 핵심적인 묵직한 한마디로 승부하는 압축입니다. AI에게 '쓸데없는 수식어와 중간 다리 문장을 전부 생략하고, 한 줄의 뼈대 문장들만으로 극도의 함축 미를 주어라'라고 지시합니다."),
    "6": ("생각 흐름 드러내기형", "지시사항: 마치 뇌 속 생각을 여과 없이 트윗하듯, 날것의 의식의 흐름을 서술하는 방식입니다. AI에게 '정제되지 않은 인터넷 구어체 말투와 줄바꿈을 사용하여 즉흥적으로 적어내려간 의식의 흐름을 재현해라'라고 지시합니다.")
}

DEFAULT_THEMES = {
    "1": ("캐릭터형", "지시사항: Cinematic Character Portrait. 글감의 내용에 해당하는 대상을 극적인 캐릭터 인물화 형태로 묘사합니다. AI에게 'volumetric lighting, octane render, expressive look, 8k resolution' 등의 디테일을 주입합니다."),
    "2": ("기물형", "지시사항: Premium Studio Object Photography. 글감의 내용을 은유하는 기물이나 오브젝트를 정물 스튜디오 제품 샷처럼 연출합니다. AI에게 'minimal concrete background, hyper-realistic, ray tracing reflections, raw texture' 등을 지시합니다."),
    "3": ("풍경형", "지시사항: Breathtaking Scenic Concept Art. 광활하거나 몽환적인 자연/도시 배경의 풍경화 콘셉트로 묘사합니다. AI에게 'golden hour, detailed matte painting, dynamic light, octane render'를 주입합니다."),
    "4": ("실사형", "지시사항: Photojournalistic 35mm Realism. 다큐멘터리 보도사진이나 일상 스냅샷과 같은 극실사형 스타일로 촬영합니다. AI에게 'shot on 35mm lens, candid moment, natural daylight, cinematic color' 등을 지시합니다.")
}

PRESETS_FILE = config.RAW_DATA_DIR / "presets.json"

def load_presets():
    if not PRESETS_FILE.exists():
        PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"forms": DEFAULT_FORMS, "styles": DEFAULT_STYLES, "themes": DEFAULT_THEMES}
        try:
            with open(PRESETS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass
        return DEFAULT_FORMS, DEFAULT_STYLES, DEFAULT_THEMES
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 튜플로 강제 변환
        forms = {k: tuple(v) for k, v in data.get("forms", {}).items()}
        styles = {k: tuple(v) for k, v in data.get("styles", {}).items()}
        themes = {k: tuple(v) for k, v in data.get("themes", DEFAULT_THEMES).items()}
        return forms, styles, themes
    except Exception:
        return DEFAULT_FORMS, DEFAULT_STYLES, DEFAULT_THEMES

def save_presets(forms, styles, themes):
    try:
        PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"forms": forms, "styles": styles, "themes": themes}
        with open(PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception:
        return False

# 초기 로딩
FORMS, STYLES, THEMES = load_presets()

def log_workbench(level, event, details):
    """
    [observability] 워크벤치 동작 모니터링 로그 기록 유틸리티
    저장 경로: data/raw/workbench.log
    """
    log_file = config.RAW_DATA_DIR / "workbench.log"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level.upper()}] [{event}] {details}\n"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        print(f"[!] 로그 저장소 기록 실패: {e}")

def build_prompt(original_title, original_content, form_name, form_desc, styles_info, extra_instruction=""):
    """
    LLM API에 전달할 정밀한 X 스타일용 시스템/유저 프롬프트 빌드
    """
    styles_str = "\n".join([f"- {name}: {desc}" for name, desc in styles_info])
    
    prompt = f"""[필독: 출력 형식 절대 규칙]
- 첫 글자부터 어떠한 영어 해설, 사전 설명, 단계별 생각 과정, 후보 시도(Attempt 1/2, Critique, 후보군, 수정 과정 등), 메타 평론을 전부 배제하고 오직 최종 완성된 한글 X 초안 한 개만 즉시 출력하세요.
- 설명글이나 인사말, 서론/결론, 시도 안내선 등은 절대로 포함해서는 안 됩니다.

당신은 SNS 플랫폼 'X(구 트위터)'에서 고도로 다듬어진 바이럴 콘텐츠를 생산하는 최고의 작가이자 에디터입니다.
제공된 '원문 글감'을 기반으로, 지정된 '양식(Form)'과 '적용 스타일(Style)'의 지시사항을 정밀하게 조합하여 X 콘텐츠 초안을 작성해주세요.

[설정 사항]
- **변환 양식 (Form)**: {form_name}
  * 세부 지시: {form_desc}
- **적용 스타일 (Style)**:
{styles_str}
- **추가 지시사항**: {extra_instruction if extra_instruction else "없음"}

[X(트위터) 글쓰기 규칙 - 반드시 준수]
1. 문장 간의 간격(공백 라인)을 넓게 배치하여 가독성을 극대화하세요. (줄바꿈 적극 활용)
2. 짧고 임팩트 있는 문장 구조를 사용하세요. (~다. 혹은 명사형 종결 추천)
3. 억지로 교훈을 주려 하지 마세요. 담담한 현실 묘사, 날카로운 심리 포착, 혹은 냉소적인 유머가 핵심입니다.
4. 해시태그와 에모지(이모티콘)는 가독성을 저해하므로 절대 사용하지 마세요.
5. 마치 실제 유저가 올린 포스트처럼 자연스러운 독백/구어체 말투로 작성하세요.

[원문 정보]
제목: {original_title}
본문:
{original_content[:2000]}
"""
    return prompt


def run_template_generator(title, content, form_id, style_ids, extra="", custom_form=None, custom_style=None):
    """
    [Template Generator]
    API Key가 없는 오프라인 환경에서도, 템플릿과 원문 분석을 조합해
    극도로 사실적인 X 스타일 초안을 생성해내는 규칙 기반 엔진.
    """
    forms, styles, themes = load_presets()
    form_name = custom_form if custom_form else forms.get(form_id, ("자유 재구성", ""))[0]
    selected_styles = [custom_style] if custom_style else [styles.get(sid, ("기본", ""))[0] for sid in style_ids]
    
    # 핵심 문장 추출 (첫 2개 의미 라인)
    lines = [line.strip() for line in content.split('\n') if len(line.strip()) > 8]
    core_story = lines[0] if len(lines) > 0 else title
    sub_story = lines[1] if len(lines) > 1 else "생각보다 사소한 일에서 세상의 본질이 드러난다."
    
    # Form에 따른 구조 빌드
    if form_id == "2": # 대화형 단막극
        output = f"""요즘 SNS 뒤집어놓은 한 대화 요약.

A: "{title}"
B: "{core_story[:50]}..."

A: "아니, 그게 진짜 상식적으로 말이 되나요?"
B: "{sub_story[:50]}..."

세상에 빌런은 멀리 있지 않다.
늘 가장 가까운 이웃의 얼굴을 하고 있을 뿐."""

    elif form_id == "3": # 구축 로그형
        output = f"""[오늘의 글감 관찰기]

1. 발단
"{title}" 사건 접수.

2. 전개
자세히 들여다보니 상황이 골 때린다.
"{core_story[:60]}..."

3. 깨달음
단순 해프닝인 줄 알았는데, 인간의 본성이 녹아있다.
"{sub_story[:60]}..."

4. 결론
이래서 사람은 겪어봐야 알고,
원칙 없는 나눔이나 선의는 쉽게 왜곡된다."""

    elif form_id == "4": # 짧은 시/문학형
        output = f"""<{title}>

주고받는 마음에
생채기만 남았다.

"{core_story[:40]}"

다정함이 독이 되는 시절.
우리는 선의를 베풀고
상처를 거두어들인다.

"{sub_story[:40]}"

바람이 불고,
또 하나의 인간군상을 지나친다."""

    else: # 현실공감 독백형 / 자유 재구성 / 커스텀 양식
        output = f"""요새 주변을 보면 참 많은 생각이 든다.

얼마 전 있었던 일이다.
"{title}" 관련해서 고민해볼 만한 상황.

실제로 나에게 일어났다면 어땠을까.
"{core_story[:60]}..." 라는 현실.

다들 겉으로는 아무렇지 않은 척 살아가지만
속은 다 똑같이 닳아 있는지도 모르겠다.

결국 핵심은 이거다.
"{sub_story[:50]}..."

공짜 점심은 없고, 사람 마음은 참 알다가도 모를 일.
양식 스타일: {form_name} 적용 완료."""

    # 스타일 기반 꼬리표/에센스 추가
    style_boosters = []
    if "1" in style_ids: # 사회풍자
        style_boosters.append("\n(풍자 한 줄) 규칙과 상식이 무너진 시대, 빌런들은 점점 지능적이 되어간다.")
    if "4" in style_ids: # 블랙코미디
        style_boosters.append("\n(블랙코미디) 웃기지만 슬픈 코리아의 일상 다큐멘터리 완성.")
    if custom_style:
        style_boosters.append(f"\n(커스텀 스타일: {custom_style}) 원문의 감각을 이채롭게 재해석했습니다.")
        
    if style_boosters:
        output += "\n" + "\n".join(style_boosters)
        
    if extra:
        output += f"\n\n[추가지시 반영 피드백]\n* '{extra}' 반영을 고려한 현실적 어조 마무리 완료."
        
    return output

def get_llm_client():
    """
    사용 가능한 최적의 AI 클라이언트를 프로브하여 반환
    """
    client = None
    model_name = config.DEFAULT_MODEL
    
    # 1. 로컬 Qwen AI 호출 점검 (Ollama 등)
    if config.LOCAL_QWEN_URL:
        try:
            check_url = config.LOCAL_QWEN_URL.replace("/v1", "")
            r = requests.get(check_url, timeout=1.5)
            if r.status_code == 200 or "Ollama" in r.text:
                client = OpenAI(api_key="none", base_url=config.LOCAL_QWEN_URL)
                model_name = config.LOCAL_QWEN_MODEL
                
                # Ollama가 반환하는 실제 로컬 모델 리스트를 탐색하여 매핑 오류 방지
                try:
                    tags_url = check_url.rstrip("/") + "/api/tags"
                    tags_resp = requests.get(tags_url, timeout=1.5)
                    if tags_resp.status_code == 200:
                        models_info = tags_resp.json().get("models", [])
                        available_models = [m.get("name") for m in models_info if m.get("name")]
                        if available_models:
                            if model_name not in available_models:
                                # 부분 일치 검색 (예: qwen -> qwen3.5:4b)
                                match = [m for m in available_models if model_name in m or m in model_name]
                                if match:
                                    model_name = match[0]
                                else:
                                    model_name = available_models[0]
                except Exception as tags_err:
                    log_workbench("warn", "AI_PROBE_WARN", f"Ollama 모델 목록 조회 실패: {tags_err}")
                
                return client, model_name, "local"
        except Exception:
            pass
            
    # 2. 클라우드 DashScope Qwen API 키 검사
    if config.QWEN_API_KEY:
        client = OpenAI(api_key=config.QWEN_API_KEY, base_url=config.QWEN_BASE_URL)
        return client, "qwen-turbo", "cloud_qwen"
        
    # 3. OpenAI 클라우드 API 키 검사
    if config.OPENAI_API_KEY:
        client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
        return client, config.DEFAULT_MODEL, "cloud_openai"
        
    return None, None, "offline"

def generate_draft(title, content, form_id, style_ids, extra_instruction="", custom_form=None, custom_style=None):
    """
    초안 생성 통합 오케스트레이션.
    로컬 Qwen(Ollama/LM Studio), DashScope Qwen, OpenAI 순서로 감지하여 자동 호출하며 실패 시 템플릿 엔진으로 자동 폴백.
    """
    forms, styles, themes = load_presets()
    
    # 커스텀 양식/스타일 세부 속성 추출
    if custom_form:
        form_name = custom_form
        form_desc = "사용자 정의 커스텀 변환 양식"
    else:
        form_item = forms.get(form_id, ("자유 재구성", "원문의 핵심을 자유롭게 X 포맷에 녹여내기"))
        form_name = form_item[0]
        form_desc = form_item[1]
        
    styles_info = []
    if custom_style:
        styles_info.append((custom_style, "사용자 정의 커스텀 어조 및 문체"))
    else:
        for sid in style_ids:
            style_item = styles.get(sid, ("기본", "기본 문체"))
            styles_info.append((style_item[0], style_item[1]))
            
    style_names_str = ", ".join([name for name, _ in styles_info])
    log_workbench("info", "GEN_START", f"초안 변환 프로세스 가동 (글감: '{title[:25]}...', 양식: {form_name}, 스타일: {style_names_str})")
    
    client, model_name, mode_type = get_llm_client()
    
    if client:
        try:
            log_workbench("info", "AI_PROBE_SUCCESS", f"AI 엔진 감지 성공 ({mode_type} - {model_name})")
            prompt_text = build_prompt(title, content, form_name, form_desc, styles_info, extra_instruction)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a professional SNS copywriter specialized in X/Twitter viral content. IMPORTANT: You must ONLY output the final Korean draft. NEVER output your thinking process, critiques, iterations, drafts, attempts, or self-reviews. Your response must contain absolutely nothing else except the final Korean draft itself, starting immediately with the first line of the post. Do not write 'Attempt', 'Critique', 'Final Version', or 'Draft'."},
                    {"role": "user", "content": prompt_text}
                ],
                temperature=0.7,
                max_tokens=1500,
                timeout=90.0
            )
            msg = response.choices[0].message
            draft_content = msg.content.strip() if msg.content else ""
            
            # reasoning 모델 대응 (content가 비어있고 reasoning_content나 reasoning이 채워진 경우)
            if not draft_content:
                extra = getattr(msg, "model_extra", {}) or {}
                reasoning_text = extra.get("reasoning_content", "") or extra.get("reasoning", "") or ""
                if reasoning_text:
                    draft_content = clean_thinking_process(reasoning_text)
            else:
                draft_content = clean_thinking_process(draft_content)
            
            if not draft_content or len(draft_content) < 5:
                log_workbench("info", "GEN_CLEAN_EMPTY", "AI draft was empty after removing thoughts. Falling back to template generator.")
                draft_content = run_template_generator(title, content, form_id, style_ids, extra_instruction, custom_form, custom_style)
                return draft_content, True
            
            log_workbench("info", "GEN_SUCCESS", f"AI 모델 '{model_name}'을 사용해 초안 변환 생성 성공")
            return draft_content, False
        except Exception as e:
            log_workbench("error", "GEN_FAIL", f"인공지능 호출 실패. 템플릿 엔진으로 긴급 폴백합니다. (에러: {e})")
            
    # API 키가 없거나 실패 시 Template Generator 실행
    log_workbench("info", "TEMPLATE_GEN_START", "Template Generator 오프라인 모드 호출")
    draft_content = run_template_generator(title, content, form_id, style_ids, extra_instruction, custom_form, custom_style)
    log_workbench("info", "GEN_SUCCESS", "Template Generator를 사용해 X 초안 변환 성공 (오프라인)")
    return draft_content, True

def generate_draft_stream(title, content, form_id, style_ids, extra_instruction="", custom_form=None, custom_style=None):
    """
    초안 생성을 스트리밍 방식으로 가동하여 각 단계별 진행 상황(status)과 생성 토큰(token)을 실시간으로 반환합니다.
    """
    forms, styles, themes = load_presets()
    
    # 커스텀 양식/스타일 세부 속성 추출
    if custom_form:
        form_name = custom_form
        form_desc = "사용자 정의 커스텀 변환 양식"
    else:
        form_item = forms.get(form_id, ("자유 재구성", "원문의 핵심을 자유롭게 X 포맷에 녹여내기"))
        form_name = form_item[0]
        form_desc = form_item[1]
        
    styles_info = []
    if custom_style:
        styles_info.append((custom_style, "사용자 정의 커스텀 어조 및 문체"))
    else:
        for sid in style_ids:
            style_item = styles.get(sid, ("기본", "기본 문체"))
            styles_info.append((style_item[0], style_item[1]))
            
    style_names_str = ", ".join([name for name, _ in styles_info])
    
    yield json.dumps({"status": "progress", "message": "🔍 [1/4] 로컬 AI 엔진 작동 확인 및 구동 모델 탐색 중..."}) + "\n"
    log_workbench("info", "GEN_STREAM_START", f"스트리밍 초안 변환 가동 (글감: '{title[:25]}...', 양식: {form_name}, 스타일: {style_names_str})")
    
    client, model_name, mode_type = get_llm_client()
    
    if not client:
        yield json.dumps({"status": "progress", "message": "⚠️ 로컬 AI 클라이언트 연결 실패. 규칙 기반 오프라인 엔진으로 자동 전환..."}) + "\n"
        draft_content = run_template_generator(title, content, form_id, style_ids, extra_instruction, custom_form, custom_style)
        yield json.dumps({"status": "content", "text": draft_content}) + "\n"
        yield json.dumps({"status": "done", "draft": draft_content, "is_offline": True}) + "\n"
        log_workbench("info", "GEN_SUCCESS_STREAM", "Template Generator를 사용해 스트리밍 변환 완료 (오프라인)")
        return

    yield json.dumps({"status": "progress", "message": f"🧠 [2/4] AI 엔진 감지 성공 ({mode_type} - {model_name}). 컨텍스트 병합 및 프롬프트 인젝션 완료..."}) + "\n"
    
    prompt_text = build_prompt(title, content, form_name, form_desc, styles_info, extra_instruction)
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a professional SNS copywriter specialized in X/Twitter viral content. IMPORTANT: You must ONLY output the final Korean draft. NEVER output your thinking process, critiques, iterations, drafts, attempts, or self-reviews. Your response must contain absolutely nothing else except the final Korean draft itself, starting immediately with the first line of the post. Do not write 'Attempt', 'Critique', 'Final Version', or 'Draft'."},
                {"role": "user", "content": prompt_text}
            ],
            temperature=0.7,
            max_tokens=1500,
            timeout=90.0,
            stream=True
        )
        
        yield json.dumps({"status": "progress", "message": "✍️ [3/4] 실시간 초안 작성 중... (아래 창에 실시간으로 완성되는 글이 노출됩니다)"}) + "\n"
        
        full_content = ""
        full_reasoning = ""
        previously_sent_clean = ""
        
        for chunk in response:
            delta = chunk.choices[0].delta
            
            # reasoning_content 또는 reasoning이 있는 경우 (생각 과정)
            reasoning_chunk = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
            if reasoning_chunk:
                full_reasoning += reasoning_chunk
                yield json.dumps({"status": "reasoning", "text": reasoning_chunk}) + "\n"
                
            # 일반 content
            content_chunk = getattr(delta, "content", None)
            if content_chunk:
                full_content += content_chunk
                
                # 실시간으로 생각 과정을 제거한 텍스트 계산
                cleaned_full = clean_thinking_process(full_content)
                if cleaned_full:
                    # 이전 전송했던 텍스트의 연속선상에 있는지 체크
                    if cleaned_full.startswith(previously_sent_clean):
                        new_text = cleaned_full[len(previously_sent_clean):]
                        if new_text:
                            yield json.dumps({"status": "content", "text": new_text}) + "\n"
                    else:
                        # 드래프트가 교체되거나 내용이 완전히 바뀐 경우 -> 전체 덮어쓰기 명령 전송
                        yield json.dumps({"status": "rewrite", "text": cleaned_full}) + "\n"
                    previously_sent_clean = cleaned_full
                
        draft_content = clean_thinking_process(full_content)
        if not draft_content and full_reasoning:
            draft_content = clean_thinking_process(full_reasoning)
            
        if not draft_content or len(draft_content) < 5:
            yield json.dumps({"status": "progress", "message": "⚠️ AI 결과물이 비어있거나 생각 과정만 포함되어 오프라인 엔진으로 자동 전환합니다..."}) + "\n"
            draft_content = run_template_generator(title, content, form_id, style_ids, extra_instruction, custom_form, custom_style)
            # 스트림 클라이언트의 출력을 템플릿 콘텐츠로 리셋하기 위해 전송
            yield json.dumps({"status": "content", "text": draft_content}) + "\n"
            yield json.dumps({"status": "done", "draft": draft_content, "is_offline": True}) + "\n"
        else:
            yield json.dumps({"status": "progress", "message": "💾 [4/4] 초안 작성 완료! 프리뷰가 최종 구성되었습니다."}) + "\n"
            yield json.dumps({"status": "done", "draft": draft_content, "is_offline": False}) + "\n"
        log_workbench("info", "GEN_SUCCESS_STREAM", f"AI 모델 '{model_name}'을 사용해 스트리밍 초안 작성 성공")
        
    except Exception as e:
        log_workbench("error", "GEN_FAIL_STREAM", f"AI 스트리밍 초안 생성 실패. 에러: {e}")
        yield json.dumps({"status": "progress", "message": f"❌ 로컬 AI API 에러로 오프라인 엔진 전환 (에러: {e})"}) + "\n"
        draft_content = run_template_generator(title, content, form_id, style_ids, extra_instruction, custom_form, custom_style)
        yield json.dumps({"status": "content", "text": draft_content}) + "\n"
        yield json.dumps({"status": "done", "draft": draft_content, "is_offline": True}) + "\n"

def generate_image_prompt(draft_text, theme_id, prompt_mode="image"):
    """
    [AI 이미지/동영상 프롬프트 생성기]
    생성된 X 콘텐츠 본문을 기반으로 DALL-E 3/Midjourney/Luma/Runway용 프리미엄 영문 프롬프트를 조각해 줍니다.
    """
    forms, styles, themes = load_presets()
    theme_item = themes.get(theme_id, ("실사형", "다큐멘터리 실사형"))
    theme_name = theme_item[0]
    theme_desc = theme_item[1]
    
    log_workbench("info", "IMG_PROMPT_START", f"프롬프트 생성기 기동 (모드: {prompt_mode}, 테마: {theme_name})")
    
    client, model_name, mode_type = get_llm_client()
    
    if client:
        try:
            if prompt_mode == "video":
                system_prompt = "You are a professional prompt engineer for AI video generators like Runway Gen-2, Luma Dream Machine, and Sora. Your goal is to write a highly detailed, kinetic, fluid motion prompt in English."
                user_prompt = f"""Based on this social media text draft, write an advanced video generation prompt.
                
[Social Media Post Draft]
\"\"\"
{draft_text[:1000]}
\"\"\"

[Desired Video Style and Camera Directions]
- Theme/Vibe: {theme_name}
- Theme Description: {theme_desc}

[Requirements for Video Prompts]
1. Write the final prompt only in English.
2. Emphasize camera movement, pacing, lighting dynamics, and character kinetic motion (e.g. slow pan, high-speed motion, volumetric mist, cinematic fluid camera, photorealistic 8k, slow motion).
3. Do not include introductory sentences. Output ONLY the raw prompt.
"""
            else:
                system_prompt = "You are a professional prompt engineer for Midjourney and DALL-E 3. Your goal is to write a highly detailed, descriptive, artistic image generation prompt in English."
                user_prompt = f"""Based on this social media text draft, write an advanced image generation prompt.

[Social Media Post Draft]
\"\"\"
{draft_text[:1000]}
\"\"\"

[Desired Image Style Category and Instructions]
- Theme Name: {theme_name}
- Detailed Instructions: {theme_desc}

[Requirements]
1. Write the final prompt only in English.
2. Make it incredibly descriptive, focusing on lighting, mood, color palette, and camera lens details (e.g. volumetric lighting, octane render, 8k resolution).
3. Do not include any introductory sentences like "Here is your prompt:". Output only the raw prompt.
"""
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=300,
                timeout=60.0
            )
            prompt_result = response.choices[0].message.content.strip()
            log_workbench("info", "IMG_PROMPT_SUCCESS", f"AI 모델 '{model_name}'을 사용해 {prompt_mode} 프롬프트 생성 성공")
            return prompt_result, False
        except Exception as e:
            log_workbench("warn", "IMG_PROMPT_FAIL", f"인공지능을 이용한 프롬프트 생성 실패. 오프라인 규칙 템플릿으로 폴백합니다. (사유: {e})")

    # 오프라인 규칙 룰 템플릿 풀백 (오프라인 환경에서도 놀라운 품질 제공)
    clean_words = re.sub(r'[^\w\s]', ' ', draft_text[:100])
    keywords = [w for w in clean_words.split() if len(w) > 1 and w not in ["오늘", "요즘", "생각", "인스타", "대화"]][:4]
    kw_str = ", ".join(keywords) if keywords else "human life, daily observation"
    
    if prompt_mode == "video":
        prompt_result = f"Cinematic video clip of {kw_str}. Style: {theme_desc}. Dynamic fluid camera motion, slow panning shot, slow motion, hyper-realistic details, highly dramatic light, Runway video generation, 4k"
    else:
        prompt_result = f"A highly detailed creative artwork representing {kw_str}. Style: {theme_desc}. Highly expressive, detailed concept art, 8k resolution, volumetric lighting --ar 16:9"
        
    log_workbench("info", "IMG_PROMPT_SUCCESS", f"오프라인 규칙 템플릿을 사용해 {prompt_mode} 프롬프트 생성 성공")
    return prompt_result, True
import re

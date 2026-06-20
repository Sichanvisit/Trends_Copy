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
    "news": ("뉴스형식", "원문의 내용을 사실 그대로 보존하고 전달합니다. 창작이나 왜곡, 인위적인 이야기 구조, 감정 수식을 절대 배제하고 팩트만 단정하게 정리하여 전달하세요. (보존 / 전달)"),
    "story": ("썰형식", "원문의 핵심 사실을 흥미진진한 이야기 구조로 재작성합니다. 실제 인터넷 커뮤니티나 SNS에 본인의 경험담을 올리는 것과 같은 자연스러운 구어체와 독백 어조를 사용하되 핵심 팩트는 온전히 보존하세요. (스토리화)"),
    "ai_explain": ("AI설명형식", "원문의 내용을 설명 중심으로 쉽고 구조적으로 재작성합니다. 복잡한 개념이나 흐름을 누구나 이해하기 쉬운 설명글 및 기호 형식으로 정리하고 가독성을 극대화하세요. (설명화)"),
    "prompt_share": ("프롬프트 공유형식", "원문의 내용을 명령어 가이드나 지시문 템플릿 형태로 재작성합니다. 유저가 AI나 실무에 적용해볼 수 있는 구체적인 가이드 및 지시형 레이아웃으로 변경하세요. (지시문화)")
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
    4대 포맷(뉴스형식, 썰형식, AI설명형식, 프롬프트 공유형식)에 맞춘 X 스타일 초안 생성.
    """
    forms, styles, themes = load_presets()
    form_name = custom_form if custom_form else forms.get(form_id, ("자유 재구성", ""))[0]
    
    # 핵심 문장 추출 (첫 2개 의미 라인)
    lines = [line.strip() for line in content.split('\n') if len(line.strip()) > 8]
    core_story = lines[0] if len(lines) > 0 else title
    sub_story = lines[1] if len(lines) > 1 else "자세한 맥락과 팩트는 본문 내용을 참조하십시오."
    
    if form_id == "news":
        output = f"""[속보] {title}

국내 보도 및 외신 정보에 따르면, 해당 사안에 대해 아래와 같은 구체적 정황이 확인되었습니다.

- 주요 쟁점: {core_story[:80]}
- 세부 내용: {sub_story[:80]}

본 사건의 객관적 분석에 근거하면 향후 업계 및 대중에 작지 않은 영향을 줄 것으로 전망됩니다."""

    elif form_id == "story":
        output = f"""진짜 어제 퇴근하고 커뮤니티 보다가 완전 소름 돋는 글 발견했음.

내용 요약하자면 "{title}" 관련 이야기인데...
실제로 이런 일이 나한테 일어났으면 진짜 멘탈 바스라졌을 듯 ㅋㅋㅋ

핵심 팩트는 이거임:
"{core_story[:70]}..."
게다가 뒤이어 밝혀진 얘기가 더 대박임:
"{sub_story[:70]}..."

세상에 참 신기하고 골 때리는 일들 많다 진짜. 다들 어떻게 생각함?"""

    elif form_id == "ai_explain":
        output = f"""오늘 화제된 "{title}" 내용 핵심만 깔끔하게 3줄 정리해 드립니다.

1. 사건의 핵심 요지
- {core_story[:90]}

2. 주목해야 할 사실 관계
- {sub_story[:90]}

3. 시사점 및 한줄 요약
- 원문의 정보에 입각했을 때, 본 사안의 핵심은 팩트의 객관적 확인입니다."""

    elif form_id == "prompt_share":
        output = f"""방금 뜬 핫토픽 "{title}" 관련해서 생각 정리할 때 쓰기 좋은 AI 프롬프트 템플릿 공유함.

[프롬프트]
너는 전문 분석가다. 아래의 사건 팩트를 바탕으로 주요 쟁점과 향후 리스크 시나리오 3가지를 정리해 줘.

[사건 내용]
- 핵심 내용: {core_story[:80]}
- 참고 팩트: {sub_story[:80]}

이 프롬프트 복사해서 ChatGPT나 Claude에 넣으면 관련 주제 디벨롭하기 정말 편함! 도움 되었길 바람."""

    else:
        output = f"""요즘 화제인 "{title}" 관련 팩트 정리.

"{core_story[:80]}"
"{sub_story[:80]}"

(양식: {form_name})"""

    if extra:
        output += f"\n\n[피드백 반영]\n* {extra}"
        
    return output

def get_llm_client(model_choice=None):
    """
    사용 가능한 최적의 AI 클라이언트를 프로브하여 반환
    model_choice: 특정 모델 선택 ('gemini', 'local', 'qwen', 'openai', None=auto)
    """
    client = None
    model_name = config.DEFAULT_MODEL
    
    # model_choice가 'gemini'이면 Google Gemini 시도
    if model_choice == "gemini":
        if config.GEMINI_API_KEY:
            try:
                from openai import OpenAI as OpenAIAlt
                client = OpenAIAlt(
                    api_key=config.GEMINI_API_KEY,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                )
                return client, "gemini-2.0-flash", "cloud_gemini"
            except Exception:
                pass
        return None, None, None
    
    # model_choice가 특정 모델로 지정된 경우 해당 모델만 시도
    if model_choice == "local":
        if config.LOCAL_QWEN_URL:
            try:
                client = OpenAI(api_key="none", base_url=config.LOCAL_QWEN_URL)
                return client, config.LOCAL_QWEN_MODEL, "local"
            except Exception:
                pass
        return None, None, None
    if model_choice == "qwen":
        if config.QWEN_API_KEY:
            try:
                client = OpenAI(api_key=config.QWEN_API_KEY, base_url=config.QWEN_BASE_URL)
                return client, "qwen-turbo", "cloud_qwen"
            except Exception:
                pass
        return None, None, None
    if model_choice == "openai":
        if config.OPENAI_API_KEY:
            try:
                client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
                return client, config.DEFAULT_MODEL, "cloud_openai"
            except Exception:
                pass
        return None, None, None
    
    # model_choice가 None이면 (auto) 순차 탐색
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
            
    # 2. Google Gemini API
    if config.GEMINI_API_KEY:
        try:
            from openai import OpenAI as OpenAIAlt
            client = OpenAIAlt(
                api_key=config.GEMINI_API_KEY,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
            return client, "gemini-2.0-flash", "cloud_gemini"
        except Exception:
            pass
    
    # 3. 클라우드 DashScope Qwen API 키 검사
    if config.QWEN_API_KEY:
        client = OpenAI(api_key=config.QWEN_API_KEY, base_url=config.QWEN_BASE_URL)
        return client, "qwen-turbo", "cloud_qwen"
        
    # 4. OpenAI 클라우드 API 키 검사
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

def _generate_character_comments_internal(title, text_content, is_draft=False, model_choice="gemini"):
    """
    [내부 공통 캐릭터 댓글 생성 엔진]
    호기심 유발 헤드라인(훅)과 클릭을 유도하는 초압축 본문 요약, 
    그리고 빈냥, 헛개, 까막 캐릭터들의 성격에 완벽히 맞춘 댓글을 LLM failover 루프를 통해 안전하게 추출합니다.
    """
    import json
    import re
    
    models_to_try = [model_choice] if model_choice != "auto" else ["gemini", "local", "qwen", "openai"]
    for m in ["gemini", "local", "qwen", "openai"]:
        if m not in models_to_try:
            models_to_try.append(m)
            
    content_type_label = "X 콘텐츠 초안" if is_draft else "본문 원문 사실"
    
    prompt = f"""너는 제공된 '{content_type_label}'을 바탕으로, 사람들의 호기심과 가독성을 극대화하여 클릭을 유도할 수 있는 '초압축 이미지 카드용 텍스트'를 제작하는 전문 콘텐츠 에디터다.

[미션 및 단계]
1. **제목 (훅)**: 이 글의 핵심 주제를 아우르며, 읽는 사람이 강하게 이끌리고 궁금해서 링크를 클릭하게끔 유도하는 한눈에 들어오는 헤드라인 1개 (예: "~~의 충격적인 진실", "한 번쯤 생각해보게 만드는 ~~ 사태" 등).
2. **짧은 본문 (초압축 요약)**: 본문의 핵심 포인트를 단 2~3줄 이내로 매우 쉽고 직관적으로 요약하되, 결말이나 상세한 수치를 일부 숨겨서 유저가 '왜 그랬지?', '어떻게 되었지?' 하고 원문 링크로 타고 들어오고 싶게끔 호기심(클리프행어)을 유발하도록 구성하라.
3. **캐릭터 댓글 반응**: 아래의 3명 고유 캐릭터(빈냥, 헛개, 까막)의 페르소나 설명에 완벽히 부합하면서, 본문 내용에 대해 각각 다른 1인칭 시점으로 비평하는 1줄 댓글을 작성하라.
   - **빈냥 (빈정대는 날개 달린 고양이)**:
     - 페르소나: 빈정대고, 비꼬고, 시니컬하지만 정곡을 찌르는 팩트폭행 스타일. 인터넷 유행어(ㅋㅋ, 퓨 등) 사용 가능. 삐딱함. 말투는 빈정대는 뉘앙스여야 함.
   - **헛개 (침 흘리며 헛소리를 차단하는 개)**:
     - 페르소나: 단순하고 직설적이며, 복잡한 생각이나 장황한 논리를 다 걷어차고 본질을 1초 만에 짚어내는 댕댕이 스타일. "그냥 ~하면 됨!" 처럼 쿨하게 헛소리 일침.
   - **까막 (까칠하고 이성적인 까마귀)**:
     - 페르소나: 똑똑하고 까칠하며, 감정을 완전히 배제하고 이성적이고 예리한 분석을 던지는 지식인 스타일. 팩트와 논리 기반의 냉철한 1줄 지적.

[출력 JSON 포맷]
반드시 아래와 같은 JSON 구조로만 답변하라. 마크다운 기호(```json)를 포함하지 말고 순수 JSON 문자열만 리턴하라.
{{
    "title": "여기에 크게 들어갈 제목 (강력한 훅)",
    "summary": "여기에 2~3줄 이내로 축약된 호기심 유발형 본문 요약",
    "comments": {{
        "binnyang": "빈냥의 빈정대는 1줄 댓글",
        "heotgae": "헛개의 단순명쾌한 1줄 일침",
        "kkamak": "까막의 예리한 분석형 1줄 댓글"
    }}
}}

[입력 데이터]
원본 제목: {title}
{content_type_label} 내용:
{text_content}
"""

    for m in models_to_try:
        client, model_name, mode_type = get_llm_client(m)
        if not client:
            continue
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a creative writer that outputs raw JSON data for character comments based on inputs."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=800,
                timeout=45.0
            )
            result_text = response.choices[0].message.content.strip()
            result_text = re.sub(r"^```json\s*", "", result_text, flags=re.IGNORECASE)
            result_text = re.sub(r"\s*```$", "", result_text)
            
            return json.loads(result_text)
        except Exception as e:
            log_workbench("warn", "CHAR_GEN_RETRY", f"Model {m} failed: {e}. Trying next fallback...")
            continue
            
    # 모든 AI 클라이언트가 실패했을 때의 최후의 보루(Absolute Fallback)
    return {
        "title": f"📢 {title}",
        "summary": text_content[:120].strip().replace("\n", " ") + "...",
        "comments": {
            "binnyang": "딱 보니 별것도 아니구만 ㅋㅋㅋ 다들 호들갑은.",
            "heotgae": "그냥 팩트만 봐! 길게 말할 필요 없음.",
            "kkamak": "논리적 팩트 분석 결과, 대중들의 심리적 유행 구조와 부합합니다."
        }
    }


def _generate_comments_llm_chain(title, content_text, prompt_template_fn, model_choice="gemini"):
    import json
    choices = [model_choice] if model_choice not in ["gemini", "auto"] else ["gemini", "local", "qwen", "openai"]
    
    last_error = None
    for choice in choices:
        client, model_name, mode_type = get_llm_client(choice)
        if not client:
            continue
        try:
            if mode_type == "local":
                # 로컬 Qwen 3.5 모델용 듀얼 전략:
                # 1차: think=false (빠르지만 4B 모델이 빈 댓글 생성할 수 있음)
                # 2차: think=true (느리지만 thinking 필드에서 창작된 JSON 추출)
                content_snippet = content_text[:1200]
                prompt = f"""아래 본문을 읽고 JSON을 출력하라.

[본문]
제목: {title}
내용: {content_snippet}

[규칙]
1. title: 본문 핵심을 살린 궁금증 유발 제목 (본문 키워드 반드시 포함)
2. summary: 본문 핵심 2~3줄 요약. 끝은 "...인데" "...라는데" 등으로 끊어서 궁금하게
3. comments: 본문 내용에 대한 각 캐릭터의 구체적 반응 (본문 키워드를 언급해야 함)
   - binnyang(빈냥): 시니컬하게 비꼼. "~하는게 웃기네 ㅋㅋ" 식
   - heotgae(헛개): 단순 직설. "~하면 되지! 뭘 복잡하게!" 식 
   - kkamak(까막): 분석적 지적. "~의 원인은 ~에 있습니다" 식

[출력: 순수 JSON만]
{{
    "title": "제목",
    "summary": "요약...",
    "comments": {{
        "binnyang": "빈냥 댓글",
        "heotgae": "헛개 댓글",
        "kkamak": "까막 댓글"
    }}
}}"""
                ollama_url = config.LOCAL_QWEN_URL.replace("/v1", "").rstrip("/") + "/api/chat"
                result_text = ""
                
                # 전략: thinking 활성화 상태로 요청, thinking+content 모두 수집
                # Qwen 3.5:4b는 think=false시 댓글을 빈 문자열로 생성하는 문제가 있어
                # thinking을 켜서 충분한 reasoning 후 JSON을 추출
                for think_mode in [False, True]:
                    num_predict_val = 1200 if not think_mode else 4000
                    payload = {
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": "Output raw JSON only. No markdown. No explanation."},
                            {"role": "user", "content": prompt}
                        ],
                        "options": {
                            "temperature": 0.5,
                            "num_predict": num_predict_val
                        },
                        "think": think_mode,
                        "stream": True
                    }
                    log_workbench("info", "CHAR_GEN_TRY", f"Ollama chat call (model: {model_name}, think: {think_mode})")
                    res = requests.post(ollama_url, json=payload, stream=True, timeout=120.0)
                    if res.status_code == 200:
                        content_chunks = []
                        thinking_chunks = []
                        for line in res.iter_lines():
                            if line:
                                chunk_data = json.loads(line.decode("utf-8"))
                                msg = chunk_data.get("message", {})
                                c = msg.get("content", "")
                                t = msg.get("thinking", "")
                                if c:
                                    content_chunks.append(c)
                                if t:
                                    thinking_chunks.append(t)
                        result_text = "".join(content_chunks).strip()
                        thinking_text = "".join(thinking_chunks).strip()
                        
                        # content가 비어있으면 thinking에서 JSON 추출
                        if not result_text and thinking_text:
                            log_workbench("info", "CHAR_GEN_THINKING_EXTRACT", f"content 비어있음, thinking에서 JSON 추출 (thinking 길이: {len(thinking_text)})")
                            result_text = thinking_text
                        
                        # content에 JSON이 있는지 빠른 검증
                        if result_text and "{" in result_text and "}" in result_text:
                            if len(result_text) > 30 and "comments" in result_text:
                                log_workbench("info", "CHAR_GEN_FAST_SUCCESS", f"think={think_mode} 상태에서 유효해 보이는 JSON 수신 성공")
                                break
                    else:
                        raise Exception(f"Ollama native API returned {res.status_code}: {res.text}")
                
                if not result_text:
                    raise Exception("Ollama returned empty content and empty thinking")
            else:
                prompt = prompt_template_fn(title, content_text)
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a creative writer that outputs raw JSON data for character comments. Output ONLY the JSON object, no markdown fences, no explanation."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.8,
                    max_tokens=800,
                    timeout=120.0,
                    stream=True
                )
                result_chunks = []
                for chunk in response:
                    delta = chunk.choices[0].delta
                    content_chunk = getattr(delta, "content", None)
                    if content_chunk:
                        result_chunks.append(content_chunk)
                result_text = "".join(result_chunks).strip()
            
            import re
            
            # 1. <think>...</think> 태그 제거 (Qwen reasoning output 정리)
            result_text = re.sub(r'<think>.*?</think>', '', result_text, flags=re.DOTALL)
            result_text = re.sub(r'<think>.*', '', result_text, flags=re.DOTALL)
            
            # 2. 마크다운 코드 펜스 제거 (```json ... ```)
            result_text = re.sub(r'```(?:json)?\s*', '', result_text)
            result_text = result_text.strip()
            
            # 3. Robust JSON 추출: 역순으로 { 위치를 찾아 json.loads 시도
            # thinking 필드에 reasoning 텍스트가 섞여 있을 때 greedy regex가 실패하므로
            # 각 { 위치에서 매칭되는 }를 찾아 json.loads로 검증
            data = None
            brace_positions = [i for i, ch in enumerate(result_text) if ch == '{']
            
            # 역순 시도 (마지막에 생성된 최종 JSON 우선)
            for pos in reversed(brace_positions):
                # 해당 위치부터 중괄호 깊이 추적하여 매칭되는 } 찾기
                depth = 0
                end_pos = pos
                in_string = False
                escape_next = False
                for j in range(pos, len(result_text)):
                    ch = result_text[j]
                    if escape_next:
                        escape_next = False
                        continue
                    if ch == '\\':
                        escape_next = True
                        continue
                    if ch == '"' and not escape_next:
                        in_string = not in_string
                        continue
                    if in_string:
                        continue
                    if ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            end_pos = j
                            break
                
                if depth != 0:
                    continue
                    
                candidate = result_text[pos:end_pos + 1]
                
                # 최소 길이 검증 (너무 짧은 건 스킵)
                if len(candidate) < 30:
                    continue
                
                try:
                    # 제어문자 정리
                    cleaned = re.sub(r'[\x00-\x1f\x7f]', ' ', candidate)
                    cleaned = re.sub(r',\s*}', '}', cleaned)
                    cleaned = re.sub(r',\s*]', ']', cleaned)
                    parsed = json.loads(cleaned)
                    
                    # 필수 키 검증
                    if "title" in parsed and "comments" in parsed:
                        data = parsed
                        log_workbench("debug", "CHAR_GEN_RAW", f"JSON 추출 성공 (위치 {pos}, 길이 {len(candidate)})")
                        break
                except (json.JSONDecodeError, ValueError):
                    continue
            
            if data is None:
                # 최후 시도: 전체 텍스트에서 "title" 키를 포함하는 패턴 매칭
                pattern = r'\{\s*"title"\s*:\s*"[^"]*"[^}]*"comments"\s*:\s*\{[^}]*\}\s*\}'
                match = re.search(pattern, result_text, re.DOTALL)
                if match:
                    try:
                        cleaned = re.sub(r'[\x00-\x1f\x7f]', ' ', match.group(0))
                        data = json.loads(cleaned)
                    except:
                        pass
                
                if data is None:
                    raise ValueError(f"유효한 JSON을 찾을 수 없음 (텍스트 길이: {len(result_text)}, {{ 개수: {len(brace_positions)})")
            # Validate keys
            if "title" in data and "summary" in data and "comments" in data:
                log_workbench("info", "CHAR_GEN_SUCCESS", f"AI 모델 '{model_name}' ({mode_type})을 사용해 캐릭터 댓글 생성 성공")
                return data
        except Exception as e:
            last_error = e
            log_workbench("warn", "CHAR_GEN_TRY_FAIL", f"AI 모델 '{model_name}' ({mode_type}) 호출 실패: {e}. 다음 차선책 시도...")
            
    # Final safety fallback: 본문 키워드를 추출하여 맥락이 있는 댓글 생성
    log_workbench("error", "CHAR_GEN_ALL_FAIL", f"모든 AI 모델 호출 실패. 본문 키워드 기반 안전 댓글을 생성합니다. (마지막 에러: {last_error})")
    return _build_content_aware_fallback(title, content_text)

def _build_content_aware_fallback(title, content_text):
    """
    [본문 키워드 기반 안전 댓글 생성]
    AI가 전부 실패했을 때, 본문에서 키워드를 추출하여 맥락이 있는 댓글을 생성합니다.
    기존의 generic 댓글 대신 본문 제목과 핵심어를 반영합니다.
    """
    # 본문에서 의미있는 키워드 추출
    combined = f"{title} {content_text[:500]}"
    # 불용어 제거 후 2글자 이상 한글 단어 추출
    stop_words = {"오늘", "요즘", "생각", "정말", "진짜", "사실", "내용", "관련", "이것", "그것", "저것",
                  "하는", "되는", "있는", "없는", "같은", "대한", "위한", "통한", "따른", "의한",
                  "합니다", "입니다", "됩니다", "있습니다", "없습니다", "했습니다", "했다", "했음",
                  "그리고", "하지만", "그런데", "그래서", "때문에", "이런", "저런", "그런"}
    words = re.findall(r'[가-힣]{2,6}', combined)
    keywords = [w for w in words if w not in stop_words][:8]
    
    # 제목에서 핵심 주제 추출
    topic = title[:20] if title else "이 주제"
    kw1 = keywords[0] if len(keywords) > 0 else "이거"
    kw2 = keywords[1] if len(keywords) > 1 else "현상"
    kw3 = keywords[2] if len(keywords) > 2 else "상황"
    
    # 본문 첫 두 줄 추출 (요약용)
    lines = [l.strip() for l in (content_text or "").splitlines() if l.strip() and len(l.strip()) > 5]
    summary_line1 = lines[0][:60] if lines else topic
    summary_line2 = lines[1][:40] if len(lines) > 1 else ""
    
    summary = f"{summary_line1}"
    if summary_line2:
        summary += f" {summary_line2}"
    summary += "...더 자세한 내용은 직접 확인해보세요."
    
    return {
        "title": f"화제의 '{topic}' 무슨 일이길래?",
        "summary": summary,
        "comments": {
            "binnyang": f"아니 {kw1} 가지고 이렇게까지 난리를 치네 ㅋㅋㅋ 웃기다 진짜",
            "heotgae": f"{kw2} 어쩌고저쩌고 복잡하게 말하지 말고 그냥 {kw1} 보면 됨!",
            "kkamak": f"'{kw1}'과 '{kw3}'의 상관관계를 분석해보면, 이 사안의 본질이 보입니다."
        }
    }

def generate_character_comments(title, facts_content, model_choice="gemini"):
    """
    [댓글형 카드 텍스트 생성]
    본문 사실 데이터를 압축하여 훅(제목), 호기심 유발 요약문(본문), 3대 페르소나 캐릭터의 1줄 댓글을 JSON으로 추출합니다.
    """
    def make_prompt(t, c):
        return f"""너는 제공된 본문 팩트 데이터를 바탕으로 X(트위터)용 이미지 카드 뉴스에 들어갈 '초압축 제목(훅)', '호기심 유발 요약본문', 그리고 3명의 고유 캐릭터(빈냥, 헛개, 까막)의 댓글 반응을 창작하는 역할을 맡았다.

[지시사항]
1. 제목(훅): 
   - 글자 크기가 가장 크게 강조되어 이미지 상단에 들어갈 제목이다.
   - 본문의 핵심 주제나 화제를 아우르며, 읽는 사람이 궁금해서 미치게 만들 자극적이고 트렌디한 한 줄 제목(예: "포켓몬고 야간산행에 사람들이 열광하는 진짜 이유", "이것 모르면 평생 후회하는 야간산행 비밀" 등)으로 구성하라.

2. 초압축 본문(summary):
   - 이미지 카드 본문에 들어갈 2~3줄 분량의 극도로 짧은 내용 요약이다.
   - 단, 단순히 건조하게 요약하지 말고, 핵심 상황이나 팩트의 빌드업만 짧게 제시한 뒤 끝부분을 절묘하게 끊어(클리프행어, cliffhanger) 독자가 링크를 클릭해 더 읽어보고 싶게 호기심을 극대화하라.
   - 예시: "최근 포켓몬고 야간산행 인증글이 올라오며 온라인이 발칵 뒤집혔습니다. 밤 11시에 모여 산을 오르는 이들이 노리는 '진짜 목표'는 따로 있다는데... 그 정체는 바로..."

3. 캐릭터별 댓글: 아래 페르소나 성격에 매칭되는 **본문 내용 맞춤형** 1줄짜리 댓글을 작성하라.
   ⚠️ **중요: 아래 예시 문장을 절대 그대로 복사하지 말 것! 반드시 본문의 구체적 키워드(인물, 사건, 장소 등)를 언급하며 새로 창작하라.**
   - **빈냥 (빈정대는 날개 달린 고양이)**:
     - 성격: 매사 시니컬하고 빈정거리며 삐딱함. 본문 키워드를 직접 언급하며 비아냥.
     - 톤 참고(복사 금지): "~하는게 웃기네 ㅋㅋ", "~라니 ㅋㅋ 별거 아닌데 호들갑" 식 어조.
   - **헛개 (헛소리 차단하는 침 흘리는 개)**:
     - 성격: 단순, 직설, 일침. 본문 핵심을 한마디로 요약하는 댕댕이.
     - 톤 참고(복사 금지): "~하면 되지 뭘!", "~한다고? 그냥 ~해!" 식 직설 어조.
   - **까막 (까칠한 분석파 까마귀)**:
     - 성격: 이성적이고 예리하며 학구적. 본문 내용을 데이터/논리적으로 지적.
     - 톤 참고(복사 금지): "~의 원인은 ~에 있죠", "~를 보면 ~가 명확합니다" 식 분석 어조.

[출력 JSON 포맷]
반드시 아래와 같은 JSON 구조로만 답변하라. 마크다운 기호(```json)를 포함하지 말고 순수 JSON 문자열만 리턴하라.
{{
    "title": "여기에 호기심을 극대화하는 자극적 제목",
    "summary": "여기에 독자가 들어와서 궁금하게 만드는 클리프행어 요약문 (2~3줄, 마지막은 궁금증 유발형으로 종결)",
    "comments": {{
        "binnyang": "빈냥의 시니컬 비꼼 댓글 (1줄)",
        "heotgae": "헛개의 단순직설 일침 댓글 (1줄)",
        "kkamak": "까막의 이성적 예리분석 댓글 (1줄)"
    }}
}}

원문 제목: {t}
원문 사실 데이터:
{c}
"""
    return _generate_comments_llm_chain(title, facts_content, make_prompt, model_choice)

def draw_character_card(title, summary, comments, output_path):
    """
    [댓글형 카드 이미지 드로잉]
    PIL(Pillow) 라이브러리를 이용하여 X(트위터) 다크모드 형태의 댓글 스레드 레이아웃 이미지를 생성합니다.
    """
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    import datetime
    import os
    
    width = 1080
    temp_height = 3000
    background_color = (255, 255, 255) # #FFFFFF (White Mode)
    
    image = Image.new("RGB", (width, temp_height), background_color)
    draw = ImageDraw.Draw(image)
    
    # 한국어 픽셀 매칭 줄바꿈 헬퍼
    def wrap_text_korean(text, font, max_width_px):
        if not text:
            return []
        lines = []
        for paragraph in text.split('\n'):
            current_line = ""
            for char in paragraph:
                test_line = current_line + char
                # draw.textlength를 이용해 픽셀 단위 정밀한 줄바꿈 계산
                w = draw.textlength(test_line, font=font)
                if w <= max_width_px:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = char
            if current_line:
                lines.append(current_line)
        return lines

    font_path_reg = r"C:\Windows\Fonts\malgun.ttf"
    font_path_bold = r"C:\Windows\Fonts\malgunbd.ttf"
    
    try:
        # 가독성을 극대화하기 위해 폰트 크기 업그레이드
        font_title = ImageFont.truetype(font_path_bold, 44)
        font_body = ImageFont.truetype(font_path_reg, 28)
        font_name = ImageFont.truetype(font_path_bold, 26)
        font_date = ImageFont.truetype(font_path_reg, 18)
        font_comment = ImageFont.truetype(font_path_reg, 26)
        font_emoji = ImageFont.truetype(font_path_reg, 36)
        font_more = ImageFont.truetype(font_path_bold, 26)
    except Exception:
        font_title = font_body = font_name = font_date = font_comment = font_emoji = font_more = ImageFont.load_default()
        
    x_margin = 50
    current_y = 60
    
    # 1. 제목 그리기 (최대 너비 980px 내에서 정밀 래핑)
    title_max_width = width - 2 * x_margin
    wrapped_title = wrap_text_korean(title, font_title, title_max_width)
    for line in wrapped_title:
        draw.text((x_margin, current_y), line, font=font_title, fill=(0, 0, 0))
        current_y += 60  # 44pt 폰트에 맞춰 행간을 60px로 조절
        
    current_y += 24
    
    # 2. 본문 요약 그리기 (최대 너비 980px 내에서 정밀 래핑)
    summary_max_width = width - 2 * x_margin
    wrapped_summary = wrap_text_korean(summary, font_body, summary_max_width)
    for line in wrapped_summary:
        draw.text((x_margin, current_y), line, font=font_body, fill=(50, 50, 50))
        current_y += 42  # 28pt 폰트에 맞춰 행간을 42px로 조절
        
    current_y += 40
    # 구분선
    draw.line([(x_margin, current_y), (width - x_margin, current_y)], fill=(226, 232, 240), width=2)
    current_y += 40
    
    # 오늘 날짜
    date_str = datetime.datetime.now().strftime("%Y.%m.%d")
    
    # 3. 캐릭터 스레드 정보 정의
    character_profiles = {
        "binnyang": {
            "name": "빈냥",
            "bg": (245, 243, 255),
            "border": (224, 215, 253),
            "emoji": "🐱",
            "image_filename": "binnyang.jpg",
            "text": comments.get("binnyang", "")
        },
        "heotgae": {
            "name": "헛개",
            "bg": (254, 243, 199),
            "border": (252, 211, 77),
            "emoji": "🐶",
            "image_filename": "heotgae.png",
            "text": comments.get("heotgae", "")
        },
        "kkamak": {
            "name": "까막",
            "bg": (241, 245, 249),
            "border": (203, 213, 225),
            "emoji": "🐦",
            "image_filename": "kkamak.png",
            "text": comments.get("kkamak", "")
        }
    }
    
    # 댓글 렌더링
    for char_id, info in character_profiles.items():
        avatar_size = 70
        avatar_x = x_margin
        avatar_y = current_y
        
        avatar_img = None
        if info["image_filename"]:
            static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "images")
            avatar_path = os.path.join(static_dir, info["image_filename"])
            if os.path.exists(avatar_path):
                try:
                    avatar_src = Image.open(avatar_path).convert("RGBA")
                    avatar_src = ImageOps.fit(avatar_src, (avatar_size, avatar_size), Image.Resampling.LANCZOS)
                    
                    mask = Image.new("L", (avatar_size, avatar_size), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
                    
                    avatar_img = Image.new("RGBA", (avatar_size, avatar_size), (0, 0, 0, 0))
                    avatar_img.paste(avatar_src, (0, 0), mask=mask)
                except Exception:
                    pass

        # 아바타 드로잉
        if avatar_img:
            image.paste(avatar_img, (avatar_x, avatar_y), mask=avatar_img)
            draw.ellipse([avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size], outline=info["border"], width=2)
        else:
            draw.ellipse([avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size], fill=info["bg"], outline=info["border"], width=1)
            draw.text((avatar_x + 15, avatar_y + 13), info["emoji"], font=font_emoji, fill=(0, 0, 0))
        
        name_x = avatar_x + avatar_size + 20
        # 이름 그리기
        draw.text((name_x, avatar_y + 4), info["name"], font=font_name, fill=(51, 51, 51))
        
        # 일자 그리기
        date_y = avatar_y + 40
        draw.text((name_x, date_y), date_str, font=font_date, fill=(136, 136, 136))
        
        # 우측 끝 더보기 기호
        draw.text((width - x_margin - 30, avatar_y + 4), "•••", font=font_more, fill=(200, 200, 200))
        
        # 댓글 텍스트 그리기 (너비: x_margin부터 width-x_margin까지 확보하여 빈 공간 최소화)
        comment_y = avatar_y + 85
        comment_max_width = width - x_margin - name_x - 10  # 오른쪽 마진 10px 남겨두고 최대로 확장
        wrapped_comment = wrap_text_korean(info["text"], font_comment, comment_max_width)
        for c_line in wrapped_comment:
            draw.text((name_x, comment_y), c_line, font=font_comment, fill=(15, 15, 15))
            comment_y += 38  # 26pt 폰트에 맞춰 행간 조절
            
        current_y = max(avatar_y + avatar_size + 30, comment_y + 35)
        
        # 구분선
        draw.line([(x_margin, current_y), (width - x_margin, current_y)], fill=(241, 245, 249), width=2)
        current_y += 35
            
    # Crop to content height
    content_img = image.crop((0, 0, width, current_y))
    
    # Create a 1:1 square canvas
    square_size = max(width, current_y)
    square_image = Image.new("RGB", (square_size, square_size), background_color)
    
    # Paste content onto square_image, centered horizontally and vertically
    paste_x = (square_size - width) // 2
    paste_y = (square_size - current_y) // 2
    square_image.paste(content_img, (paste_x, paste_y))
    
    square_image.save(output_path, "PNG")
    return output_path

def search_web_image(keyword: str):
    """
    [실시간 웹 이미지 검색]
    MyMemory 번역 API와 Wikimedia Commons API를 활용하여 주어진 키워드에 대한 최적의 실제 사진 URL을 반환합니다.
    WAF 차단이 없고 100% 안정적으로 동작합니다.
    """
    import requests
    import urllib.parse
    
    # 1. 한글 키워드 -> 영문 번역
    en_keyword = keyword
    try:
        translate_url = "https://api.mymemory.translated.net/get"
        params = {
            "q": keyword,
            "langpair": "ko|en"
        }
        res = requests.get(translate_url, params=params, timeout=5)
        if res.status_code == 200:
            translated = res.json().get("responseData", {}).get("translatedText", "")
            # 알파벳, 숫자, 공백만 남기기
            cleaned = "".join(c for c in translated if c.isalnum() or c.isspace()).strip()
            if cleaned:
                en_keyword = cleaned
    except Exception as e:
        print(f"[Translation Warning] Failed to translate '{keyword}': {e}")

    # 2. Wikimedia Commons 이미지 검색
    wiki_url = "https://commons.wikimedia.org/w/api.php"
    wiki_params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"File:{en_keyword}",
        "gsrnamespace": 6,
        "gsrlimit": 3,
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json"
    }
    headers = {
        "User-Agent": "Trends_Copy_Bot/1.0"
    }
    
    try:
        res = requests.get(wiki_url, params=wiki_params, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            pages = data.get("query", {}).get("pages", {})
            urls = []
            for page_id, page_info in pages.items():
                imageinfo = page_info.get("imageinfo", [])
                if imageinfo:
                    img_url = imageinfo[0].get("url")
                    if img_url:
                        ext = img_url.lower().split('.')[-1]
                        if ext in ['jpg', 'jpeg', 'png', 'webp']:
                            urls.append(img_url)
            if urls:
                print(f"[Wikimedia Image Search] Found image for '{en_keyword}': {urls[0]}")
                return urls[0]
    except Exception as e:
        print(f"[Wikimedia Warning] Image search failed for '{en_keyword}': {e}")
        
    return None


def draw_story_card(text, image_url, output_path, img_scale=1.0, img_offset_x=0, img_offset_y=0):
    """
    [실화 인증 기물형 카드 이미지 드로잉]
    상단에 현장감 있는 기물/공간 이미지(1080x400)를 배치하고,
    하단에 텍스트 문단 구조와 줄바꿈을 시원시원하게 유지하여 동적 세로형 카드를 생성합니다.
    """
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    import os
    import requests
    from io import BytesIO
    import config

    width = 1080
    temp_height = 3000
    background_color = (255, 255, 255) # White Mode
    img_height = 400 # 상단 이미지 고정 높이
    
    image = Image.new("RGB", (width, temp_height), background_color)
    draw = ImageDraw.Draw(image)
    
    # 상단 이미지 영역을 흰색으로 먼저 클리어 (색이 다른 문제 해결)
    draw.rectangle([0, 0, width, img_height], fill=(255, 255, 255))
    
    # 1. 상단 이미지 드로잉
    image_drawn = False
    if image_url:
        try:
            # 로컬 파일 경로 매칭 시도
            local_path = None
            if image_url.startswith("/static/"):
                local_path = config.BASE_DIR / image_url.lstrip('/')
            elif not image_url.startswith("http"):
                local_path = config.BASE_DIR / image_url
                
            if local_path and os.path.exists(local_path):
                img_raw = Image.open(local_path)
            else:
                # 외부 URL인 경우 다운로드
                headers = {'User-Agent': 'Mozilla/5.0'}
                res = requests.get(image_url, headers=headers, timeout=10)
                img_raw = Image.open(BytesIO(res.content))
                
            # 투명도가 존재하는 이미지(RGBA) 대응
            if img_raw.mode in ('RGBA', 'LA') or (img_raw.mode == 'P' and 'transparency' in img_raw.info):
                alpha_bg = Image.new("RGBA", img_raw.size, (255, 255, 255, 255))
                alpha_bg.paste(img_raw, (0, 0), img_raw.convert("RGBA"))
                img_src = alpha_bg.convert("RGB")
            else:
                img_src = img_raw.convert("RGB")
                
            # 원본 비율 유지 스케일링 & 오프셋
            orig_w, orig_h = img_src.size
            scale_factor = 1080.0 / orig_w
            base_w = 1080
            base_h = int(orig_h * scale_factor)
            
            # 배율(scale) 적용
            new_w = int(base_w * img_scale)
            new_h = int(base_h * img_scale)
            
            img_resized = img_src.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            # 가운데 기준 좌표 계산
            default_x = (1080 - new_w) // 2
            default_y = (img_height - new_h) // 2
            
            # 사용자 오프셋 반영
            paste_x = default_x + img_offset_x
            paste_y = default_y + img_offset_y
            
            # 흰색 배경의 상단 캔버스에 paste 후 메인 이미지에 병합
            temp_canvas = Image.new("RGB", (1080, img_height), (255, 255, 255))
            temp_canvas.paste(img_resized, (paste_x, paste_y))
            image.paste(temp_canvas, (0, 0))
            image_drawn = True
        except Exception as e:
            print(f"Error loading card image: {e}")
            
    if not image_drawn:
        # 이미지가 없을 때도 완전한 흰색 배경 유지
        draw.rectangle([0, 0, 1080, img_height], fill=(255, 255, 255))
        try:
            font_placeholder = ImageFont.truetype(r"C:\Windows\Fonts\malgunbd.ttf", 36)
        except Exception:
            font_placeholder = ImageFont.load_default()
        draw.text((width // 2, img_height // 2), "📷 실화 인증 기물 이미지 영역 (여기에 드래그/복붙 및 설정 가능)", font=font_placeholder, fill=(200, 200, 200), anchor="mm")

    # 2. [수정] 이미지 넣는 곳 경계 회색선 제거 (전체 카드 완전한 화이트 통일)
    # draw.line 제거

    # 3. 하단 텍스트 영역 렌더링
    font_path_bold = r"C:\Windows\Fonts\malgunbd.ttf"
    try:
        # 가독성이 높은 36pt 볼드체 사용
        font_text = ImageFont.truetype(font_path_bold, 36)
    except Exception:
        font_text = ImageFont.load_default()

    # 단일 라인 글자 래핑 헬퍼 (단락 쪼개기는 루프에서 직접 처리)
    def wrap_single_line(txt, font, max_width_px):
        if not txt:
            return []
        current_line = ""
        lines = []
        for char in txt:
            test_line = current_line + char
            w = draw.textlength(test_line, font=font)
            if w <= max_width_px:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = char
        if current_line:
            lines.append(current_line)
        return lines

    # 텍스트 마진 및 초기 Y축 세팅
    x_margin = 80
    current_y = img_height + 60 # 구분선 밑 60px 아래부터 텍스트 배치 시작
    text_max_width = width - 2 * x_margin
    line_height = 54 # 36pt 맑은고딕에 알맞은 행간
    paragraph_spacing = 30 # 문단(단락)과 문단 사이 추가 간격
    
    # 텍스트를 문단 단위로 쪼개서 유지한 상태로 줄바꿈 드로잉
    paragraphs = text.split('\n')
    for i, p_text in enumerate(paragraphs):
        p_clean = p_text.strip()
        if not p_clean:
            # 사용자가 입력한 빈 줄(줄바꿈 두 번 등)인 경우
            current_y += 35
            continue
            
        # 래핑된 여러 줄 구하기
        wrapped_lines = wrap_single_line(p_clean, font_text, text_max_width)
        for line in wrapped_lines:
            draw.text((x_margin, current_y), line, font=font_text, fill=(15, 23, 42))
            current_y += line_height
            
        # 하나의 문단이 끝난 후, 다음 문단과의 사이에 추가 공간 부여
        if i < len(paragraphs) - 1:
            current_y += paragraph_spacing

    # 4. 콘텐츠가 종료되는 세로 지점에서 최종 여백 80px을 주고 동적으로 크롭
    final_height = current_y + 80
    final_height = max(final_height, 800)
    
    # 최종 세로 카드로 크롭
    final_image = image.crop((0, 0, width, final_height))
    final_image.save(output_path, "PNG")
    return output_path

def generate_character_comments_from_draft(title, draft_content, model_choice="gemini"):
    """
    [재구성 초안 기반 댓글형 카드 텍스트 생성]
    이미 작성된 X 콘텐츠 초안(draft_content)을 기반으로, 
    가독성을 극대화하기 위한 첫 끌어당김(HOOK)용 큰 제목,
    내용을 더 짧고 임팩트 있게 축약한 요약문(2~3줄, 호기심 유발),
    그리고 빈냥, 헛개, 까막 캐릭터들의 댓글 반응을 창작하여 JSON으로 추출합니다.
    """
    def make_prompt(t, c):
        return f"""너는 제공된 'X 콘텐츠 초안'을 바탕으로, 사람들의 호기심과 가독성을 극대화하기 위한 '초압축 이미지 카드용 텍스트'를 제작하는 전문 콘텐츠 에디터다.

[미션 및 단계]
1. 제목 (훅): 
   - 이미지 카드 최상단에 들어갈 시선 강탈형 제목이다.
   - 초안 내용의 핵심 주제를 활용해 사람들이 궁금해서 들어오고 싶게 만드는 강력한 자극적 제목 1개 (예: "~~의 충격적인 진실", "한 번쯤 봐야 할 ~~ 이야기" 등)를 작성하라.

2. 짧은 본문 (초압축 요약): 
   - 초안의 핵심 메시지와 내용을 단 2~3줄 이내로 매우 직관적이고 읽기 쉽게 요약(초압축)하되, 결론이나 핵심 팁의 직전 부분에서 텍스트를 끊어 궁금증을 유발하는 클리프행어(cliffhanger) 형식으로 작성하라.
   - 예시: "초안에서 밝힌 화제의 공부법 핵심입니다. 매일 10분 투자로 뇌를 깨운다는데, 절대 해서는 안 될 치명적 실수 하나는 바로..."

3. 캐릭터 댓글 반응: 초안의 **구체적 내용(인물, 사건, 키워드)**에 대해 아래 3대 캐릭터가 각자 관점으로 반응하는 1줄 댓글을 작성하라.
   ⚠️ **중요: 아래 톤 참고 문장을 절대 그대로 복사하지 말 것! 반드시 초안의 구체적 키워드를 언급하며 새로 창작하라.**
   - **빈냥**: 시니컬하고 빈정대는 고양이. 초안의 핵심 소재를 직접 언급하며 비꼼. 톤 참고(복사 금지): "~하는게 웃기다 ㅋㅋ" 식.
   - **헛개**: 단순 직설 댕댕이. 초안 핵심을 한마디로 정리. 톤 참고(복사 금지): "~하면 되지! 뭘 복잡하게!" 식.
   - **까막**: 분석파 까마귀. 초안 내용을 데이터/논리로 지적. 톤 참고(복사 금지): "~의 원인은 ~에 있습니다" 식.

[출력 JSON 포맷]
반드시 아래와 같은 JSON 구조로만 답변하라. 마크다운 기호(```json)를 포함하지 말고 순수 JSON 문자열만 리턴하라.
{{
    "title": "초안 키워드를 활용한 초강력 훅 제목",
    "summary": "초안 핵심 2~3줄 요약 + 클리프행어 종결",
    "comments": {{
        "binnyang": "본문 키워드 포함 시니컬 댓글",
        "heotgae": "본문 키워드 포함 직설 댓글",
        "kkamak": "본문 키워드 포함 분석 댓글"
    }}
}}

[입력 데이터]
원본 글감 제목: {title}
X 콘텐츠 초안 내용:
{draft_content}
"""
    return _generate_comments_llm_chain(title, draft_content, make_prompt, model_choice)


def _extract_image_text_via_gemini(images, model_choice="gemini"):
    """
    [이미지 내 텍스트 전사 추출]
    Gemini 멀티모달 API를 이용하여 이미지 속에 포함된 모든 텍스트(OCR)와 도표 수치 등을 
    요약이나 축약 없이 있는 그대로 길고 상세하게 텍스트로 트랜스크립션하여 반환합니다.
    """
    client, model_name, mode_type = get_llm_client(model_choice)
    if not client or mode_type != "cloud_gemini":
        return ""
        
    prompt_text = """너는 입력된 이미지들(카드뉴스, 본문 캡쳐, 자료사진 등) 속에 포함된 모든 텍스트 정보(OCR)와 도표, 그래프의 수치 및 시각적 맥락을 있는 그대로 100% 한 글자도 빠짐없이 텍스트로 추출하여 전사(Transcription)하는 '멀티모달 이미지 전사 엔진'이다.
      
[지시사항]
- 이미지 내의 텍스트를 절대로 요약하거나, 임의로 축약하거나, 재구성하지 마십시오.
- 글자 크기가 작거나 구석에 있는 텍스트라도 빠짐없이 길고 상세하게 받아 적으십시오.
- 도표나 그래프가 있다면 그 행과 열의 수치 및 데이터 팩트를 있는 그대로 상세히 서술하여 기록하십시오.
- 어조는 객관적이어야 하며, 너의 주관적 생각이나 서론, 결론, 설명은 모두 배제하고 오직 이미지 내 텍스트 추출 데이터만 출력하십시오.
"""
    try:
        user_content = []
        user_content.append({
            "type": "text",
            "text": prompt_text
        })
        for img in images:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{img['mime_type']};base64,{img['base64_data']}"
                }
            })
            
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a multimodal transcription engine. Extract and transcribe all text from the images as-is. Do not summarize or explain.",
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            temperature=0.1,
            timeout=60.0,
            max_tokens=3000,
        )
        result = response.choices[0].message.content.strip()
        return clean_thinking_process(result)
    except Exception as e:
        log_workbench("error", "IMAGE_OCR_FAIL", f"이미지 텍스트 추출 실패: {e}")
        return ""
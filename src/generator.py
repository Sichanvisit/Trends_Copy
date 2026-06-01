import os
import datetime
import requests
from openai import OpenAI
import config

import json
from pathlib import Path

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

def build_prompt(original_title, original_content, form_name, style_names, extra_instruction=""):
    """
    LLM API에 전달할 정밀한 X 스타일용 시스템/유저 프롬프트 빌드
    """
    styles_str = ", ".join(style_names)
    
    prompt = f"""당신은 SNS 플랫폼 'X(구 트위터)'에서 고도로 다듬어진 바이럴 콘텐츠를 생산하는 최고의 작가이자 에디터입니다.

[요청 사항]
제공된 '원문 글감'을 기반으로, 지정된 '양식(Form)'과 '스타일(Style)'에 최적화된 X 콘텐츠 초안을 작성해주세요.

[지정 옵션]
- **변환 양식 (Form)**: {form_name}
- **적용 스타일 (Style)**: {styles_str}
- **추가 지시사항**: {extra_instruction if extra_instruction else "없음"}

[X(트위터) 글쓰기 규칙 - 반드시 준수]
1. 문장 간의 간격(공백 라인)을 넓게 배치하여 스크롤 시 가독성을 극대화하세요.
2. 짧고 임팩트 있는 문장 구조를 사용하세요. (~다. 혹은 명사형 종결 추천)
3. 억지로 교훈을 주려 하지 마세요. 담담한 현실 묘사, 날카로운 심리 포착, 혹은 냉소적인 유머가 핵심입니다.
4. 해시태그는 절대 사용하지 마세요.

[원문 정보]
제목: {original_title}
본문:
{original_content[:2000]}

---
위 지침을 완벽히 흡수하여 X에 올릴 실시간 초안만 간결하게 출력하세요. (설명이나 부연설명은 절대 금지)
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
    # 커스텀 양식/스타일 명칭 매핑
    form_name = custom_form if custom_form else forms.get(form_id, ("자유 재구성", ""))[0]
    selected_style_names = [custom_style] if custom_style else [styles.get(sid, ("기본", ""))[0] for sid in style_ids]
    
    log_workbench("info", "GEN_START", f"초안 변환 프로세스 가동 (글감: '{title[:25]}...', 양식: {form_name}, 스타일: {', '.join(selected_style_names)})")
    
    client, model_name, mode_type = get_llm_client()
    
    if client:
        try:
            log_workbench("info", "AI_PROBE_SUCCESS", f"AI 엔진 감지 성공 ({mode_type} - {model_name})")
            prompt_text = build_prompt(title, content, form_name, selected_style_names, extra_instruction)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a professional SNS copywriter specialized in X/Twitter viral content."},
                    {"role": "user", "content": prompt_text}
                ],
                temperature=0.7,
                max_tokens=800,
                timeout=15.0
            )
            draft_content = response.choices[0].message.content.strip()
            log_workbench("info", "GEN_SUCCESS", f"AI 모델 '{model_name}'을 사용해 초안 변환 생성 성공")
            return draft_content, False
        except Exception as e:
            log_workbench("error", "GEN_FAIL", f"인공지능 호출 실패. 템플릿 엔진으로 긴급 폴백합니다. (에러: {e})")
            
    # API 키가 없거나 실패 시 Template Generator 실행
    log_workbench("info", "TEMPLATE_GEN_START", "Template Generator 오프라인 모드 호출")
    draft_content = run_template_generator(title, content, form_id, style_ids, extra_instruction, custom_form, custom_style)
    log_workbench("info", "GEN_SUCCESS", "Template Generator를 사용해 X 초안 변환 성공 (오프라인)")
    return draft_content, True

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
                timeout=12.0
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

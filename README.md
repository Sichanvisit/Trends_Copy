# 🚀 X Content Workbench (개인 콘텐츠 워크벤치)

> **네이트판, 네이트뉴스, GeekNews에서 실시간 핫 토픽을 자동으로 수집·정리하고, 로컬 Qwen AI 및 오프라인 템플릿 엔진을 사용하여 X(구 트위터) 최적화 콘텐츠 초안으로 순식간에 변환하는 1인 제작자를 위한 콘텐츠 워크플레이스**

본 프로젝트는 단순 과제 제출용 완구 데모가 아닌, **"제작자가 매일 뉴스 및 커뮤니티를 왕복하며 겪는 비효율적인 수집 및 기획 흐름을 자동화한다"**는 실 사용자 관점의 가설에서 출발하여 설계된 고품질 콘텐츠 파이프라인 도구입니다.

---

## 💡 왜 만들었는가? (기획 배경)

기존 X 콘텐츠 작성을 위해 매일 거치던 비효율적 작업 프로세스:
```text
네이트판/뉴스 탐색 ➔ 글 클릭 ➔ 드래그 & 복사 ➔ 메모장 붙여넣기 ➔ 내용 요약 ➔ X 맞춤형 구성 고민 ➔ 수십 번의 퇴고 ➔ 업로드
```
이 **지루한 전반부 80%의 반복 작업(수집, 정제, 정리, 포맷팅)**을 원클릭으로 자동화하여, 제작자가 오직 **"핵심 20%의 편집과 발행"**에만 에너지를 집중할 수 있도록 문제를 해결했습니다.

---

## 🛠️ 핵심 기능 범위 (MVP)

1. **실시간 인기 글감 수집 (Crawler)**
   - **네이트판**: 오늘의 톡(10개) 및 톡커들의 선택(10개) 정밀 추출 및 본문 스크래핑
   - **네이트 랭킹 뉴스**: 트래픽이 보장되는 일간 관심뉴스 1위~20위 상세 수집
   - **GeekNews**: 테크 및 스타트업 트렌드 요약 본문 초고속 다이렉트 추출
2. **단일 통합 데이터베이스 관리 (Consolidated Storage)**
   - 파편화된 다수의 CSV 파일을 차단하고, 본문 텍스트 전체를 포함하는 단 하나의 마스터 파일 **`content_index.csv`**로 단일화 관리
   - 동일 URL 실시간 검출을 통한 **100% 완벽한 멱등성 중복 수집 차단**
   - 생성물은 사용자 개인의 **옵시디언 볼트(Obsidian Vault) `X_start` 폴더**로 실시간 다이렉트 전송/정리
3. **X 최적화 초안 변환 엔진 (Generator)**
   - **5종의 변환 양식(Form)** 지원: 현실공감 독백형, 대화형 단막극, 구축 로그형, 짧은 시/문학형, 자유 재구성
   - **6종의 스타일(Style)** 다중 적용 지원: 사회풍자, 인간심리 관찰, 시대관찰, 블랙코미디 등
   - **하이브리드 AI 지원**: 로컬에 설치된 Qwen 모델(Ollama/LM Studio 등) 및 클라우드 API를 우선 감지하며, 오프라인 상태에서는 정교한 자체 룰 엔진인 **Template Generator**로 자동 폴백 시연 가능

---

## 📂 폴더 구조 (합격 최적화 구조)

프로젝트는 유지보수성과 평가자의 가독성을 극대화하기 위해 군더더기를 완전히 뺀 **6~7개 핵심 파일** 구조로 설계되었습니다.

```text
x-content-workbench/
├── data/
│   └── raw/              # 단 하나의 통합 데이터베이스 CSV (content_index.csv)
├── src/
│   ├── crawler.py        # Nate Talk, Nate News 20위, GeekNews 크롤링 처리부
│   ├── processor.py      # 본문 클리닝(광고/특수문자 제거) 및 Markdown 카드 템플릿 처리부
│   ├── generator.py      # Prompt 빌더 및 로컬 Qwen / 오프라인 템플릿 변환기
│   ├── storage.py        # 중복 URL 검사 및 통합 content_index.csv 단일 적재 제어부
│   ├── cli.py            # 대화형 CLI 메뉴 제어부
│   └── web.py            # FastAPI 백엔드 라우터 및 API 컨트롤러
├── static/               # 웹 대시보드용 정적 파일 디렉터리
├── templates/            
│   └── index.html        # 프리미엄 싱글 페이지 웹 UI (Chart.js + X-초안 워크스테이션)
├── main.py               # 듀얼 실행 진입점 (CLI 구동 & 웹 서버 구동 지원)
├── config.py             # 옵시디언 vault 경로, 로컬 Qwen 주소 및 API 중앙 설정부
├── requirements.txt      # 최소 의존 패키지 정의 (fastapi, uvicorn 추가)
├── run_dashboard.bat     # [원클릭] FastAPI 대시보드 서버 가동 및 브라우저 자동 오픈 배치 파일
├── run_collector.bat     # [원클릭] 백그라운드 실시간 통합 크롤링 자동 배치 파일
└── README.md             # 본 설계 및 회고 문서
```

---

## 🚀 빠른 시작 가이드 (Quick Start)

### 1. 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. 실행 모드 선택 (원클릭 및 하이브리드 구동)

#### **[MODE A] 대시보드 배치 파일 실행 (★원클릭 강력 추천)**
프로젝트 폴더 내의 **`run_dashboard.bat`** 파일을 마우스 더블 클릭하면 자동으로 Uvicorn 서버를 실행하고 **동시에 사용자의 기본 웹 브라우저를 열어 `http://localhost:8000` 대시보드 화면을 띄워 줍니다.**
- 브라우저의 **실시간 Chart.js 시각화** 및 **X-초안 워크스테이션**을 사용해 마우스 클릭으로 간편하게 크롤링과 로컬 Qwen AI 글감 재구성 생성을 진행할 수 있습니다.

#### **[MODE B] 원클릭 실시간 통합 크롤링 자동 배치 실행**
프로젝트 폴더 내의 **`run_collector.bat`**를 더블 클릭하시면 터미널 창을 직접 열 필요 없이 실시간 중복 검사를 거쳐 50여 개의 핫이슈 글감을 옵시디언 vault에 즉시 동기화 적재합니다.

#### **[MODE C] 전통적인 대화형 CLI 실행**
터미널 환경에서 가볍고 빠르게 조작할 수 있는 대화형 번호 선택식 메뉴입니다.
```bash
python main.py
```

### 3. LLM API 연동 (선택사항)
`.env` 파일에 API 키 또는 로컬 Qwen 주소를 입력하면 자동으로 **Template Generator**에서 **최신 인공지능 기반 초안 생성**으로 업그레이드되어 연결됩니다.
```env
# 1. 로컬 Qwen 모델 활용 시 (Ollama 등)
LOCAL_QWEN_URL=http://localhost:11434/v1
LOCAL_QWEN_MODEL=qwen

# 2. 클라우드 Qwen API 활용 시
QWEN_API_KEY=your_qwen_api_key_here

# 3. OpenAI API 활용 시
OPENAI_API_KEY=your_openai_api_key_here
```

---

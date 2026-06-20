import os
from pathlib import Path
from dotenv import load_dotenv

# .env 로드
load_dotenv()

# 기본 디렉터리 경로 설정
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
STYLE_LIBRARY_FILE = RAW_DATA_DIR / "style_library.json"

# 최종 초안 및 마크다운 카드를 저장할 옵시디언 뷰 경로 지정 (실제 개인 세컨드 브레인 폴더)
GENERATED_DIR = Path(r"C:\Users\bhs33\Desktop\옵시디언(시찬)\Sichan\10_AI_Engineering\00_Career_&_insight\X_start")
BODY_DIR = GENERATED_DIR / "본문"
RECONSTRUCTED_DIR = GENERATED_DIR / "본문재구성"

# 폴더 생성 자동 보장
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
BODY_DIR.mkdir(parents=True, exist_ok=True)
RECONSTRUCTED_DIR.mkdir(parents=True, exist_ok=True)

# API 설정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

# 로컬 Qwen 모델 설정 (Ollama/LM Studio 대응)
LOCAL_QWEN_URL = os.getenv("LOCAL_QWEN_URL", "http://localhost:11434/v1")
LOCAL_QWEN_MODEL = os.getenv("LOCAL_QWEN_MODEL", "qwen3.5:4b-instruct")

# 기본 선택값 (디버깅용)
DEFAULT_MODEL = "gpt-4o-mini"

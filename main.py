import sys
from pathlib import Path

# src 디렉터리를 sys.path에 추가하여 모듈 임포트 경로 확보
sys.path.append(str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    # '--web' 매개변수가 주어지면 FastAPI 서버 구동
    if "--web" in sys.argv:
        import uvicorn
        import io
        
        # Windows 한글 깨짐 방지 입출력 설정
        if sys.platform.startswith('win'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
            
        print("=" * 60)
        print("   🌐 Trends_Copy - FastAPI 실시간 대시보드 기동 🌐")
        print("   - 로컬 Qwen AI 재구성 엔진 및 옵시디언 자동 저장 연동 완료 -")
        print("   - 대시보드 주소: http://127.0.0.1:8000")
        print("=" * 60)
        
        uvicorn.run("src.web:app", host="127.0.0.1", port=8000, reload=True)
    else:
        # 기본 구동 시에는 대화형 CLI 메뉴 루프 기동
        from src.cli import main_menu_loop
        try:
            main_menu_loop()
        except KeyboardInterrupt:
            print("\n\n[!] 사용자에 의해 프로그램이 강제 중단되었습니다. 종료합니다.")
            sys.exit(0)

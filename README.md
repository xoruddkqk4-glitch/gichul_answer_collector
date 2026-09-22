# 모의고사 영어 정답 수집기

Windows에서 `시작.bat`을 실행하거나 `python server.py`를 실행하세요. 브라우저에서 `http://localhost:8765`를 열면 됩니다. 필요한 Python 라이브러리가 없으면 `python -m pip install -r requirements.txt`를 실행하세요. (또는 내장된 `vendor/` 디렉터리를 통해 별도 설치 없이 바로 실행 가능합니다.)

학년, 시행 연도, 월을 여러 개 선택하고 **정답 찾기**를 누르면 [EBSi 기출문제 목록](https://www.ebsi.co.kr/ebs/xip/xipc/previousPaperList.ebs?targetCd=D300)에서 각 영어 정답표를 조회합니다. 조회된 결과마다 **JSON 저장**을 누를 수 있습니다. **찾은 정답 모두 저장**은 결과가 여러 개면 각 JSON을 담은 ZIP 파일 하나를 다운로드합니다.

일반 시험은 `고3-[2026-09].json` 형식으로 저장합니다. A형과 B형이 모두 있으면 둘 다 조회하여 `고2-[2012-09]-A.json`, `고2-[2012-09]-B.json`처럼 구분해 저장합니다. 홀수형과 짝수형이 있으면 홀수형만 저장하고 파일명은 일반 형식을 따릅니다.

EBSi 목록은 2006년부터 제공되므로 2002~2005년 자료는 여기서 찾을 수 없습니다. 정답을 자동 판독할 수 없는 일부 스캔 PDF는 오류로 표시합니다.

## 주요 기능
- **2단계 하이브리드 정답 추출 엔진**:
  - 1순위: 해설 PDF 텍스트 파싱 (`pypdf` 및 `PyMuPDF` 다중 엔진 지원)
  - 2순위 Fallback: EBSi 정답표 이미지 격자 검출(Pillow) 및 템플릿 매칭 OCR (`templates.json`)
- **문제지 및 해설 PDF 다운로드**: EBSi CDN 링크를 안전하게 중계하여 단일 다운로드 및 일괄 ZIP 압축 다운로드 제공
- **경량 프론트엔드**: 외부 프레임워크나 번들러 없이 순수 바닐라 JS 및 자체 구현 PKZIP 2.0 인코더로 브라우저 내 압축 수행

## 업데이트 이력

## [2026-09-22 19:45] 업데이트 이력 (Commit ID: 137c88e)
- **수정 내용**: 
  - 에이전트 실행 규칙 및 커스텀 스킬(`ask`, `git-commit`, `scratchpad`)을 워크스페이스에 적용 (`AGENTS.md` 생성)
  - `.gitignore` 파일 생성 (`__pycache__` 및 임시 설정 제외)
  - 원격 GitHub 저장소(`https://github.com/xoruddkqk4-glitch/gichul_answer_collector`) 연결 및 최초 커밋/푸시 동기화
- **검증 결과**:
  - Python 정적 구문 검사(`python -m py_compile server.py extractor.py pdf_download.py`) 통과 (exit code 0)
  - Git remote 및 브랜치(`main`) 설정 정상 검증 완료

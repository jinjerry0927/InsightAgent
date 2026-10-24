# 검증 근거

## 기록 원칙

실행한 검증과 정적 코드 조사, 예정 검증을 구분한다. 실행하지 않은 테스트·API·화면을 성공으로 기록하지 않는다. 출력에는 비밀값을 포함하지 않는다.

## 2026-10-24 — Phase 3 재검토·Phase 4 NVIDIA 어댑터

사용자 요청으로 Phase 3 검토 승인을 반영하고 Phase 4를 구현했다. 아래 과거 기록은 각 단계의 당시 상태다.

| 실제 실행 명령 | 결과 |
| --- | --- |
| 변경 전 `.\.venv\Scripts\python.exe -m pytest -q --tb=short` | Phase 3 전체 34개 재검증 통과, 기존 PR #3 push·PR CI 모두 SUCCESS 확인 |
| `uv pip compile requirements.in --python .venv/Scripts/python.exe --default-index https://pypi.org/simple --generate-hashes --output-file requirements.txt --quiet` | 새 직접 의존성 openai·python-dotenv 추가 해결, 기존 12개 버전 유지 |
| `uv pip sync requirements.txt --python .venv/Scripts/python.exe --default-index https://pypi.org/simple --require-hashes --only-binary :all:` | 15개 추가 설치·총 27개. uv 캐시 rename의 Windows 일시 접근 거부 경고 후 자체 재시도로 설치 성공, 종료 코드 0 |
| `uv pip check --python .venv/Scripts/python.exe` | 27개 패키지 호환성 확인, 종료 코드 0 |
| `.\.venv\Scripts\python.exe -X utf8 scripts/check_environment.py` | 기존 CSV→pandas→DuckDB→pandas·문자·Decimal·시각·NULL·CTE 검사 PASS |
| `.\.venv\Scripts\python.exe -X utf8 -m pytest -q --tb=short` | 신규 49개·기존 34개, 전체 83개 통과, 종료 코드 0 |
| `.\.venv\Scripts\python.exe -m compileall -q scripts tests` | 컴파일 성공, 종료 코드 0 |
| `.\.venv\Scripts\python.exe -X utf8 -m scripts.check_nvidia` | configuration 오류: 키 미설정. attempts=0·usage=null, 애플리케이션 종료 코드 2 확인, 실제 네트워크 요청 없음 |

### 검증 범위·초기 실패와 수정

- 실제 SDK openai 3.37.0과 그 하위 HTTP 라이브러리 httpx2의 MockTransport를 사용했다. 외부 서버·실 키를 테스트에 사용하지 않았다.
- 올바른 요청 주소·모델 교체·Authorization·문맥·토큰 상한·thinking 비활성화, 사용량·시간 반환, 설정 우선순위·보간 금지·입력 제한을 확인했다.
- 400·401·403·404·408·429·500·503·307과 연결 실패·시간 초과에서 전송 1회·추가 재시도 없음. 리다이렉트도 새 요청을 만들지 않는다.
- 빈 답변·잘못된 choices·비정상 종료·잘린 출력·잘못된 JSON·음수 사용량을 거부하며, 제공된 사용량이 없는 경우 null로 유지한다. 잘린 응답에 제공된 사용량도 보존한다.
- 첫 신규 테스트 실행은 38개 통과·10개 실패였다. 9개는 traceback 소스 줄에 테스트의 프롬프트 리터럴 자체가 표시되어 생긴 잘못된 탐지였고 변수로 전달해 수정했다. 1개는 Python 3.11.0 traceback의 한글 다중 행 호출 위치 처리에서 UnicodeDecodeError가 발생했다. 한국어 메시지를 변수로 분리한 뒤 48개 통과, 사용량 검사 1개를 추가해 전체 83개 통과했다.
- provider 오류 본문·키·프롬프트가 공개 예외·기본 로그·CLI 보고서에 섞이지 않는지 합성 비밀 표식으로 확인했다. 디버그 CLI는 SDK HTTP 디버그 로그도 비활성화한다.
- 로컬 `.env`는 비밀값 없이 준비했으며 Git 제외 대상이다. 실제 키 입력·계정 이용 권한·호스팅 파라미터 수용·실제 사용량·시간은 미검증이다. 실 연결 결과 없이 Phase 4 전체 완료로 표현하지 않는다.
- 최소 실제 시험은 고정 문장 1회·출력 최대 64토큰이다. 키가 준비되면 `--live` 결과를 기록한다. Phase 5와 실제 SQL 생성·실행 연동은 미구현이다.
- 게시 전 변경 파일 12개의 UTF-8·마지막 줄·공백·코드 펜스·상대 문서 링크·충돌 표식·비밀값 패턴을 검사해 통과했다. `.env`와 연결 결과 JSON이 Git 제외 대상이며 `.env`가 추적되지 않는 것도 확인했다. 모든 형태의 비밀값 부재를 보장하는 검사는 아니다.

## 2026-10-24 — Phase 3 승인 KPI·기준 SQL

사용자의 "Phase 3 시작하자" 요청으로 직전 KPI 기준을 승인 반영했다. Phase 2를 기반으로 `codex/phase-3-baseline-metrics` 브랜치를 만들고, SQL 4개·실행기·CSV 독립 계산·테스트·집계 보고서를 추가했다. 아래 기존 기록은 각 단계의 당시 상태다.

| 실제 실행 명령 | 결과 |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest tests/test_metrics.py -q --tb=short` | 신규 23개 첫 실행 통과, 종료 코드 0 |
| `.\.venv\Scripts\python.exe -m pytest -q --tb=short` | 기존 적재 테스트 포함 전체 34개 통과, 종료 코드 0 |
| `.\.venv\Scripts\python.exe -X utf8 -m scripts.run_baselines --start 2016-09-01 --end 2018-11-01` | SQL 상태 ok, 원본 CSV 독립 계산 일치, 입력 CSV 9개·DB 지문 유지, 종료 코드 0 |
| `.\.venv\Scripts\python.exe -m compileall -q scripts tests` | 컴파일 성공, 종료 코드 0 |

### 합성 기대값과 경계 조건

- 직접 계산한 8개 주문 중 delivered 6개만 포함한다. 1월 상품금액 41.00·주문 3건, 2월 18.00·주문 3건을 기대값으로 사용한다.
- 배송비·다중 결제·추가 리뷰·취소·진행 중 주문이 상품금액에 섞이지 않는다.
- 기간 시작 포함·종료 제외, 실제 0원·데이터 부재, 품목·금액 결측, 분모 0을 구분한다.
- 누락 상품·카테고리 NULL·미번역·동일 영어명·TOP 5 동률 정렬에서 금액·카테고리 단위를 보존한다.
- 같은 예정일의 늦은 시각은 정상 배송이며, 배송일 NULL은 분모에서 제외한다.
- 대표 리뷰는 주문별 최신 응답·생성 시각·ID 순이다. NULL 시각, 여러 주문에 재사용된 review_id, 무효 최신 평점, 리뷰 없음도 검사한다.
- 원본 CSV 참조값과 SQL 결과의 1센트 차이와 금액의 float 변환을 의도적으로 주입해 오류 탐지를 검증했다. 이는 기대된 pytest 검사이며 실패한 테스트가 아니다.
- 잘못된 기간·시간대·조회 이름·TOP 제한, 보고서 출력의 원본·DB 덮어쓰기를 거부한다.

### 실제 데이터 독립 대조

- SQL은 검토된 파일과 바인딩된 기간만 사용하고 DB 연결은 읽기 전용이다. AI SQL 안전성 검증기는 아직 구현하지 않았다.
- 별도 CSV 순회·Decimal·날짜 계산으로 범위·관측수·월별 거래액·주문수·전체/상위 카테고리·배송·대표 리뷰의 값과 순서를 확인했다.
- 결과의 Decimal 금액은 정확히 비교하고, 평균 평점·비율은 1e-12 허용오차로 비교한다.
- 실제 원본 구매 99,441건 중 delivered 96,478건, 제외 상태 2,963건이다. 상품금액 13,221,498.11은 배송비 제외·원본 단위다.
- 배송 비교 가능 96,470건 중 날짜 기준 지연 6,534건, 날짜 결측 제외 8건이다.
- 전체 카테고리 합계가 월별 상품금액 합계와 일치했다. 원본 지문은 DB에 저장된 적재 manifest와도 일치했다.
- 행별 고객·주문·리뷰 식별자와 리뷰 텍스트를 게시하지 않고 [BASELINE_RESULTS](BASELINE_RESULTS.md)에 집계만 기록했다.
- 최초 Phase 3 테스트·실제 대조에서 실패는 없었다. 이후 금액 타입 검사를 강화했고 같은 범위의 검증을 재실행했다.

게시 전 문서·코드 25개 파일과 내부 링크 34개, YAML 구문·공백·비밀값 패턴 검사에서 오류 0을 확인했다. 원격 검증 결과·커밋은 Phase 3 PR Checks에서 확인한다. 기존 PR을 자동 병합하거나 NVIDIA API를 호출하지 않았다. 사용자에게 현재 수동 설치·업로드·테스트를 요구하지 않는다.

## 2026-10-24 — 실제 데이터 구축·GitHub 게시

사용자가 파일 준비 완료와 GitHub 업로드·활용을 요청했다. 초기 문서·환경 12개 파일을 main의 `482f7dc` 커밋으로 게시했고, 데이터 구축은 `codex/phase-2-data-foundation`에서 수행했다. 아래 환경 설정 기록은 당시 시점으로 보존한다.

### 실제 명령과 결과

| 실행 명령·수단 | 실제 결과 |
| --- | --- |
| GitHub get_repo·branches 조회 | 공개 저장소·쓰기 권한 확인, 초기 branches는 빈 목록 |
| `uv pip check --python .venv/Scripts/python.exe` | 설치된 12개 패키지 의존성 일관성 확인, 종료 코드 0 |
| `.\.venv\Scripts\python.exe scripts/check_environment.py` | 환경 연결·타입 검증 PASS, 종료 코드 0 |
| 게시 대상 12개 파일 비밀값 패턴 검사 | 실제 키 형태·개인 키 헤더 발견 0. 모든 형태의 비밀값 부재를 보장하는 검사는 아님 |
| `git diff --cached --check` | 공백 오류 없음 |
| `git commit -m "docs: initialize InsightAgent design and verified Python environment"` | 초기 커밋 482f7dc 생성 |
| `git -c credential.interactive=false push -u origin main` | main 게시·추적 브랜치 설정 성공 |
| `git switch -c codex/phase-2-data-foundation` | Phase 2 작업 브랜치 생성 |
| `.\.venv\Scripts\python.exe -m pytest -q --tb=short` | 최종 11 passed, 종료 코드 0 |
| `.\.venv\Scripts\python.exe -m scripts.build_database --source-dir data/raw --output data/processed/insightagent.duckdb` | CSV 9개 적재·원본 지문·타입·행 수 검사 성공, 종료 코드 0 |
| `.\.venv\Scripts\python.exe -m scripts.profile_data` | 9개 테이블의 로컬 JSON·집계 Markdown 생성, 종료 코드 0 |
| `.\.venv\Scripts\python.exe -m compileall -q scripts tests` | 컴파일 성공, 종료 코드 0 |
| Kaggle 공개 페이지 브라우저 조회 | Version 2·CSV 9개·CC BY-NC-SA 4.0 표시 확인. 로컬과 공식 배포 체크섬 비교는 아님 |
| GitHub Actions 공식 태그 조회 | checkout v5·setup-python v6의 실제 커밋 확인 후 workflow에 SHA 고정 |

### 테스트 범위와 수정 기록

- 합성 CSV의 한글·우편번호 앞자리 0·Decimal·날짜·NULL 보존과 원본 SHA-256 유지.
- 잘못된 날짜·금액·소수 2자리 초과·정수 소수부 손실 시 중단과 임시 DB 정리.
- 기존 출력 보존, 누락 파일·잘못된 헤더·입력 폴더 모호성 거부.
- 반복 고객 ID·중복 리뷰를 삭제하지 않고 보고, 연결되지 않는 키 노출.
- 상품 2행·결제 2행·리뷰 2행의 단순 연결이 8행임을 기대값으로 검증.
- 첫 실행은 7 failed·4 passed였다. DuckDB 2.0 Relation의 fetchone 제거, 미완료 결과와 다음 관계 작업 충돌을 확인했다.
- 최소 재현에서 Python read_csv 관계는 0행인데 SQL read_csv는 같은 합성 CSV를 1행으로 읽는 차이를 확인했다. 소스가 같은지 확인하고 SQL 스테이징 경로로 일원화했다.
- 수정 3회 이내에 해결했고 최종 11개 테스트가 통과했다. 실제 원본 적재는 테스트 통과 후 실행했다.
- 리뷰 언어 표본 조회의 최초 출력은 Windows cp949 인코딩 오류로 중단됐다. `python -X utf8 -`로 재조회해 짧은 본문 5개가 포르투갈어임을 확인했다. 원본 데이터 변경은 없었다.

### 실제 데이터 근거

- 고객·주문 각 99,441행, 지리정보 1,000,163행, 상품 행 112,650행, 결제 103,886행, 리뷰 99,224행, 상품 32,951행, 판매자 3,095행, 번역 71행.
- 전체 컬럼 타입·NULL·고유값·날짜 범위·키 후보·연결 오류·월별 분포는 [DATA_PROFILE](DATA_PROFILE.md)에 생성했다.
- 단순 LEFT JOIN 예상 행 수 119,143과 실제 JOIN COUNT(*)가 일치했다.
- 원본 지문·적재 전후 행 수를 대조하고 원본·DB를 Git 제외 대상으로 유지했다.
- KPI 정의는 [METRICS](METRICS.md)의 승인 대기 초안이며 금액 KPI·배송 지연율을 실행하지 않았다.

### GitHub 검증 범위

Actions는 원본·API 키 없이 Windows/Python 3.11에서 의존성 검사·환경 연결·합성 pytest·컴파일을 수행하도록 구성했다. 여기의 11 passed는 로컬 실행 기록이다. 원격 실행 결과·커밋·로그는 해당 PR의 Checks와 Actions 실행 이력을 근거로 확인한다. 오류 보고와 PR 양식도 추가했다. 자동 병합·배포는 설정하지 않았다.

초기 원격 실행 40047503466은 작업 시작 전 workflow 구문 오류로 실패했다. 설치 명령 끝의 `:all:`을 YAML의 매핑 기호로 해석하는 문제를 기존 전역 PyYAML로 재현했고, `run: >-` 명령 블록으로 수정했다. 프로젝트 의존성을 추가하지 않았다. 연결된 GitHub 커넥터의 Issue 쓰기는 403이어서 이미 로그인된 GitHub CLI를 사용한다. 추가 계정 권한 부여나 토큰 변경은 하지 않았다.

## 2026-10-24 — Phase 1 재검토·Phase 2 환경 설정

사용자가 Phase 1 재검토 후 Phase 2 환경 설정 시작을 요청했다. 기존 원격·문서를 유지하면서 `.python-version`, `requirements.in`, `requirements.txt`, `scripts/check_environment.py`와 로컬 `.venv`를 추가했다. 아래 2026-10-23 기록은 당시 상태로 보존한다.

### Phase 1 검토

- 커밋 `365d0617c1a4567ffee1b19b40c27feb4206bfcf`의 원본 6개 파일을 GitHub 커넥터로 다시 읽었다: ToolRegistry, RunSqlTool, DuckDBRunner, Agent, AgentConfig, RunSqlToolArgs.
- 주요 설명과 실제 정의·분기를 대조했다. 도구 스키마와 DB 스키마의 차이, 실행 후 SELECT 분기, 기본 인자 변환의 NoOp, 반복 라운드 상한 설명이 원본과 일치했다.
- 역분석 문서에 필수 항목 대응표, 조사 시점 명시, WITH 조회의 결과 표시 주의점을 보완했다.
- Vanna 예제·실 LLM·공격 재현은 여전히 실행하지 않았다. Phase 1의 정적 역분석 완료 범위와 실행 미검증을 구분했다.

### 실제 실행 명령과 결과

| 실행 명령 | 결과 |
| --- | --- |
| `uv venv .venv --python 'C:\Users\James\AppData\Local\Programs\Python\Python311\python.exe' --no-python-downloads` | 기존 CPython 3.11.0으로 프로젝트 가상환경 생성, 종료 코드 0 |
| `uv pip compile requirements.in --python .venv/Scripts/python.exe --default-index https://pypi.org/simple --generate-hashes --output-file requirements.txt --quiet` | 직접·하위 의존성 버전과 해시 기록 생성, 종료 코드 0 |
| `uv pip sync requirements.txt --python .venv/Scripts/python.exe --default-index https://pypi.org/simple --require-hashes --only-binary :all:` | 총 12개 패키지 설치, 종료 코드 0 |
| `uv pip check --python .venv/Scripts/python.exe` | 12개 패키지의 의존성 메타데이터 일관성 확인, 종료 코드 0 |
| `.\.venv\Scripts\python.exe scripts/check_environment.py` | CSV→pandas→DuckDB→pandas, 한글·Decimal·날짜·NULL·CTE 조회 검사 PASS, 종료 코드 0 |
| `.\.venv\Scripts\python.exe -m pytest --version` | pytest 9.1.1 출력, 종료 코드 0. 테스트 모음을 실행한 것은 아님 |
| `.\.venv\Scripts\python.exe -m compileall -q scripts` | 환경 확인 스크립트 컴파일 성공, 종료 코드 0 |
| `git check-ignore --no-index -v .venv/Scripts/python.exe scripts/__pycache__/check_environment.cpython-311.pyc` | 가상환경과 Python 캐시 제외 규칙 확인 |
| `New-Item -ItemType Directory -Force -Path data/raw, data/processed` | 로컬 데이터용 빈 폴더 생성, 원본·DB 파일은 없음 |

직접 패키지 버전은 DuckDB 2.0.0, pandas 3.1.0, pytest 9.1.1이다. 전체 12개 버전·해시는 [requirements.txt](../requirements.txt)를 따른다. 전역 Python 설치를 변경하거나 Vanna·UI·LLM 패키지를 추가하지 않았다.

환경 검사의 합성 데이터는 3행이다. 한글 그룹 2행의 Decimal 합계 12.75, 날짜 최솟값 2024-01-01, 날짜 NULL 1개와 조회 반환 3행을 기대값으로 검사했다. 이는 Olist 통계·KPI 값이 아니다. 가상환경 경로 확인도 스크립트에 포함되어 있다.

문서·스크립트·설정 12개 파일의 UTF-8·줄바꿈·공백·충돌 마커·코드 블록, 내부 링크 13개와 Git 제외 규칙 5개를 Python으로 검사했다. 오류 0, 종료 코드 0이었다. 원격은 기존 origin과 main을 유지하며 커밋·push는 수행하지 않았다.

### 데이터 준비 상태와 남은 검증

- 사용자가 원본 "미다운로드" 상태를 확인했다.
- Kaggle 공개 페이지의 Download 메뉴에서 **Download dataset as zip** 항목을 실제 브라우저로 확인했다. 수동 절차를 README에 기록했으며 다운로드·로그인·API 키 설정은 수행하지 않았다.
- 실제 데이터 품질·테이블 관계·적재·KPI는 아직 검증 대상이다.
- SQL 안전성·NVIDIA 연결·브라우저 분석 앱은 이후 승인된 Phase의 검증 대상이다.
- 환경 설정은 완료했지만 Phase 2 전체 완료 조건은 아직 충족하지 않았다.

## 2026-10-23 — 환경과 저장소

| 실행 명령·수단 | 실제 결과 |
| --- | --- |
| `python --version` | Python 3.11.0 |
| `git --version` | Git 2.52.0.windows.1 |
| `uv --version` | uv 0.10.6 |
| `python -m pip --version` | pip 22.3, 현재 선택된 Python 3.11 환경 |
| Python의 `sys.prefix != sys.base_prefix` | False, 현재 Python은 프로젝트 가상환경 아님 |
| `importlib.metadata.version()` | pandas 3.0.2, pytest 9.1.1, python-dotenv 1.2.2 확인 |
| 같은 패키지 조회 | duckdb, streamlit, plotly, openai, vanna 미설치 |
| `git status --short --branch` (연결 전) | `No commits yet on master`, 작업 파일 없음 |
| `git log -1` (초기 확인) | 실패: 현재 브랜치에 아직 커밋이 없음. 손상이나 병합 오류가 아님 |
| GitHub 커넥터 `get_repo` | InsightAgent 공개 저장소, 기본 브랜치 main, archived=false |
| `git -c credential.interactive=false ls-remote --symref https://github.com/jinjerry0927/InsightAgent.git` | 종료 코드 0, 참조 출력 없음. 원격 커밋 없음 |
| `git remote add origin https://github.com/jinjerry0927/InsightAgent.git` | 종료 코드 0, 로컬 원격 등록 |
| `git branch -m main` | 종료 코드 0, 로컬 브랜치 main |
| `git remote -v` 및 `git status --short --branch` | origin URL 일치, main에 아직 커밋 없음 |

환경 결과는 해당 시점의 선택된 Python 기준이다. 패키지 메타데이터 존재가 전체 실행 호환성을 보장하지는 않는다.

## 2026-10-23 — Phase 1 정적 조사

| 조회 수단·대상 | 실제 확인 내용 |
| --- | --- |
| GitHub 커넥터 `get_repo`, vanna-ai/vanna | 공개·archived=true·기본 브랜치 main |
| `fetch`, `/repos/vanna-ai/vanna/git/ref/heads/main` | 커밋 `365d0617c1a4567ffee1b19b40c27feb4206bfcf` |
| 같은 커밋의 재귀 Git 트리 | truncated=false, 분석 대상 파일 위치 확인 |
| `fetch_file`, 고정 커밋의 pyproject.toml | version=2.0.2 |
| 공식 Quick Start 열람, 고정 커밋의 quickstart.ipynb 읽기 | Chinook·도구 등록·LLM·서버 예제 확인. 저장된 실행 출력 없음 |
| 고정 커밋의 Agent·ToolRegistry·RunSqlTool·DuckDBRunner·시각화·프롬프트·legacy 소스 읽기 | 데이터 흐름·권한 경계·SQL 처리·문맥·오류·반복 한도 정적 확인 |
| README와 ToolRegistry 정의 대조 | README의 register 예제와 실제 register_local_tool 정의 차이 확인 |
| `importlib.metadata.version('vanna')` | PackageNotFoundError를 처리하여 `vanna: not installed` 출력 |

소스 위치·라인·해석은 [REVERSE_ENGINEERING.md](REVERSE_ENGINEERING.md)에 기록했다. GitHub 쓰기 API, Git push, 실 LLM 호출은 사용하지 않았다.

## 2026-10-23 — 문서 검증

문서와 `.gitignore` 작성 후 다음 검증을 실제 수행했다.

| 실행 명령·수단 | 실제 결과 |
| --- | --- |
| `python -`로 표준입력 검증 코드 실행: UTF-8 읽기, 마지막 줄바꿈, 후행 공백, 충돌 마커, 코드 블록 닫힘, 상대 링크 대상 검사 | 파일 8개·내부 Markdown 링크 11개 검사, 오류 0, 종료 코드 0 |
| 문서의 고정 커밋 GitHub blob URL을 읽은 원본 Git 트리·파일 본문과 대조 | 소스 참조 24개, 커밋·경로·행 범위 오류 0. 웹 링크의 HTTP 응답을 전부 다시 검사한 결과는 아님 |
| `git check-ignore --no-index --quiet <경로>`를 Python subprocess에서 8개 예상 결과와 대조 | 실패 0. `.env`, `.env.local`, 가상환경, 원본·생성 DB는 제외됨. `.env.example`, 테스트용 CSV, 검증 문서는 제외되지 않음 |
| `git -c core.autocrlf=false diff --no-index --check -- /dev/null <각 파일>`를 8개 파일에 실행 | 공백 진단·경고 출력 0. 신규 파일과 빈 파일의 차이로 각각 종료 코드 1 |

`--no-index`는 차이가 있으면 종료 코드 1을 반환하므로 마지막 결과를 테스트 실패나 빌드 실패로 해석하지 않는다. 별도의 Python 공백·문서 검사도 종료 코드 0으로 통과했다. 최초 Git 보조 검사에서는 Windows의 LF→CRLF 변환 안내가 있었으며, 저장소 설정을 바꾸지 않고 위 명령의 일회성 옵션으로 재확인했다.

확인용 경로는 실제 파일 생성이나 `.env` 내용 열람 없이 문자열로 검사했다. 커밋·push는 수행하지 않았고, 작성 문서는 로컬의 미추적 파일 상태다.

## 2026-10-23 시점에 실행하지 않은 검증과 이유

- Vanna 공개 예제 실행: 현재 Vanna·샘플 DB가 없으며 Quickstart는 추가 패키지와 Anthropic 설정이 필요하다. 이번 범위에서 설치·다른 제공자 실 API 호출을 하지 않았다.
- InsightAgent 빌드·pytest·Streamlit 실행: 아직 애플리케이션 코드, 테스트, 의존성 정의, 데이터가 없다. 문서 검사를 앱 테스트 성공으로 대체하지 않는다.
- 실 데이터 프로파일링·SQL 정확도: Olist 원본이 아직 확보되지 않았다.
- NVIDIA 실 API·요금·사용량: 인증과 실제 호출을 수행하지 않았다.
- SQL 공격·쓰기 차단·리소스 제한: 이번 결과는 정적 조사다. 자체 구현 후 Phase 5에서 차단 테스트가 필요하다.

## 사용자가 직접 확인할 방법

PowerShell의 저장소 폴더에서:

```powershell
uv pip check --python .venv/Scripts/python.exe
.\.venv\Scripts\python.exe scripts/check_environment.py
git remote -v
git status --short --branch
Get-Content -Encoding utf8 .\docs\PROJECT_PLAN.md
Get-Content -Encoding utf8 .\docs\REVERSE_ENGINEERING.md
git check-ignore --no-index -v .env .venv/probe data/raw/probe.csv data/processed/probe.duckdb
```

마지막 명령의 probe 경로는 규칙 확인용 문자열이다. 파일을 만들지 않는다. `.env` 내용이나 API 키를 출력할 필요가 없다.

## 다음 실행 검증

현재 데이터·지표 테스트 34개와 실제 CSV 독립 대조를 실행·통과했다. 다음은 Phase 3 결과 사용자 검토이며, NVIDIA 실 API는 Phase 4의 별도 승인 범위다.

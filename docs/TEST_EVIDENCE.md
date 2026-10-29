# 검증 근거

## 기록 원칙

실행한 검증과 정적 코드 조사, 예정 검증을 구분한다. 실행하지 않은 테스트·API·화면을 성공으로 기록하지 않는다. 출력에는 비밀값을 포함하지 않는다.

## 2026-10-30 — Phase 5 최종 검토·Phase 6 대시보드

사용자의 "마지막 검토 진행하고 Phase 6까지 진행하자" 요청으로 검토와 화면 구현을 진행했다. Phase 5 코드의 상태·예산·AST·KPI 구조·별도 조회를 다시 확인했고, 마지막 187개 테스트·기존 CI·실제 DB 4개 지표 대조에서 진행을 막는 문제를 발견하지 못했다. Phase 5 분석 엔진은 변경하지 않고 UI 서비스에서 재사용했다.

| 실제 명령·점검 | 결과 |
| --- | --- |
| 변경 전 `.\.venv\Scripts\python.exe -X utf8 -m pytest -q --tb=short` | Phase 5 전체 187개 재검증 통과, 종료 코드 0 |
| 변경 전 `.\.venv\Scripts\python.exe -X utf8 -m scripts.verify_agent` | 실제 DB 4개 지표·Phase 3 일치·DB 지문 유지·API 시도 0회 |
| `uv pip compile requirements.in --constraint requirements.txt --python .venv/Scripts/python.exe --default-index https://pypi.org/simple --generate-hashes --output-file requirements.txt --quiet` | 승인 스택 Streamlit 1.66.1·Plotly 7.1.0 추가. 기존 27개 정확한 버전 유지, 총 53개 |
| `uv pip sync requirements.txt --python .venv/Scripts/python.exe --default-index https://pypi.org/simple --require-hashes --only-binary :all:` | 26개 하위/직접 패키지 추가 설치, 종료 코드 0 |
| `.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_dashboard.py tests/test_charts.py tests/test_app.py -q --tb=short` | 초기 UI 31개 통과. 부분 합계 표시 검사 1개 추가 후 신규 32개 |
| `.\.venv\Scripts\python.exe -X utf8 -m pytest -q --tb=short` | 최종 기능 검사 219개 통과(기존 187·UI 신규 32), 종료 코드 0 |
| `.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_app.py -q --tb=short` | 표시 보완 후 AppTest 16개 재검증 통과 |
| `.\.venv\Scripts\python.exe -m compileall -q app.py scripts tests` | 컴파일 통과, 종료 코드 0 |
| `uv pip check --python .venv/Scripts/python.exe` | 53개 패키지 호환성 확인, 종료 코드 0 |
| `.\.venv\Scripts\python.exe -X utf8 -m streamlit run app.py --server.port 8501` | 실제 localhost 서버에서 UI 검증. 사용 통계 비활성화·상세 예외 숨김·127.0.0.1 설정 적용 |

### 의미 있는 UI 검사

- 포함 마지막 날짜의 변환으로 합성 1월 31일 23:59:59 주문을 포함하고 2월 1일은 제외해 상품금액 41.00·주문 3건이 일치한다.
- 정확한 Decimal 표시, 실제 0과 NULL, 미관측 월 gap, 같은 카테고리 번역명의 원문 코드 분리, 리뷰 표본/NULL, 월별 비율 단순 평균을 배제한 가중 지연율을 검증했다.
- 초기 렌더링에서 분석 0회, 재실행·모드 변경 후 요청 추가 없음, 명시적 AI 제출 1회만 호출, 수정 허용 여부에 따른 예산 1/0/1 또는 2/1/2를 확인했다.
- 데이터 부재·역전 날짜·차단/실패/확인 요청/미지원/한도 종료를 수치·차트로 꾸미지 않는다. 행 상한의 부분 결과는 전체 합계 카드 없이 표시한다. 알 수 없는 API 사용량과 원시 예외 비노출도 검사했다.

### 실제 브라우저와 최소 API

Playwright 스킬의 CLI 절차로 Chrome의 UI 스냅샷·클릭·날짜 입력·크기 변경·스크린샷을 확인했다. Windows에서는 스킬의 bash 래퍼와 같은 `npx.cmd --yes --package @playwright/cli playwright-cli` 명령을 사용했다. 스냅샷의 실제 ref/역할을 바탕으로 조작했으며 Playwright를 프로젝트 의존성으로 추가하지 않았다.

- 기준 모드의 월별·카테고리·배송·리뷰 카드와 Plotly를 실제 DB에서 확인했다. 2024년 기간의 no_data와 역전 날짜 오류를 브라우저에서도 확인했다.
- 1280×720 초기 검토에서 긴 상품금액이 4열 카드에서 잘렸다. 2열로 조정한 뒤 1440×1000·390×844에서 정확한 금액 전체 표시를 확인했다.
- 직접 숨겨진 radio input을 클릭한 자동화는 포인터 가로채기 timeout을 반환했다. 표시된 라벨로 선택해 정상 동작을 확인했다. 네이티브 날짜 input의 자동 fill 중 aria-hidden/focus 경고 2개가 있었으나 해당 검증 세션의 JavaScript 오류는 0개였다. 전체 보조기술/접근성 인증을 수행한 것으로 표현하지 않는다.
- 실제 AI 입력은 "2017년 월별 매출과 주문수를 보여줘." 1개다. 수정 허용을 끈 기본 설정에서 분석 버튼을 한 번 누르고 결과·사용량 탭을 확인했다. 이후 탭·화면 크기 변경에서 추가 분석은 요청하지 않았다.

| 화면에서 확인한 실제 결과 | 값 |
| --- | --- |
| 선택 기간 | 2017-01-01~2017-12-31, 양끝 포함 |
| 상태·금액·주문·상품 행 | success · 5962902.01(원본 단위) · 43428 · 49556 |
| API 시도·SQL 수정·후보 조회 | 1 · 0 · 1 |
| 입력·출력·총 토큰 | 1923 · 335 · 2258 |
| 표시된 모델·조회 시간 | 약 4.33초 · 약 0.85초 |
| 별도 Phase 3 SQL 대조 | 월별 12행의 총액·주문수 일치 |

실 API 질문 결과 스냅샷은 2026-10-30 01:11 KST에 기록했다. API 키는 인증에만 사용하고 모델 문맥·화면·증거 파일에 넣지 않았다. 모델에는 질문·스키마·승인 KPI/SQL 예시만 보냈으며 결과 행·원본/리뷰는 전송하지 않았다. 추가 실제 API 요청은 하지 않았다.

로컬 증거는 `output/playwright/phase6-browser-evidence.json`, `phase6-monthly-result.png`, `phase6-no-data.png`, `phase6-ai-usage.png`, `phase6-ai-desktop.png`, `phase6-mobile.png` 및 DOM 스냅샷이다. 공개 후보에 원본·DB·키·로컬 브라우저 산출물을 올리지 않는다. 실제 계정 인증/한도 오류를 일부러 유발하지 않았고, 해당 화면은 모의 AppTest·기존 어댑터 테스트로 검증했다.

미검증: 실제 모델의 다른 지표/많은 한국어 표현, 여러 브라우저·보조기술, 공유 서버·로그인·공개 배포·금전 비용/잔여 한도. 로컬 MVP 화면까지만 완료했으며 Phase 7은 착수하지 않았다.

게시 전 변경 18개 파일의 UTF-8·마지막 줄·공백·상대 링크·펜스·충돌·비밀값 패턴 검사와 공개 후보 58개 파일의 실제 키 문자열 비포함 검사를 통과했다. TOML·workflow YAML 문법과 root app.py의 CI 컴파일 포함, 기존 27개 버전 유지, `.env`·Streamlit secrets·로컬 브라우저 산출물 Git 제외를 확인했다. `git diff --check`도 통과했다. 비밀값 검사에서 값 자체는 출력하지 않았다.

## 2026-10-30 — Phase 5 분석 에이전트·SQL 정책·실행 제한

사용자가 설명 후 즉시 Phase 5 진행을 요청해 Phase 4 검토와 착수 승인을 반영했다. 새 패키지는 추가하지 않았으며 기존 DuckDB 2.0.0의 네이티브 JSON AST를 사용했다. 아래 이전 날짜 기록은 당시의 상태다.

| 실제 명령 | 결과 |
| --- | --- |
| `.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_sql_guard.py tests/test_query_executor.py tests/test_agent.py -q --tb=short` | 초기 신규 96개 통과. 이후 KPI 구조·실제 worker 통합·메모리/CLI 검사를 추가 |
| `.\.venv\Scripts\python.exe -X utf8 -m pytest -q --tb=short` | 기존 83개·신규 104개, 총 187개 통과, 종료 코드 0 |
| `.\.venv\Scripts\python.exe -m compileall -q scripts tests` | 컴파일 통과, 종료 코드 0 |
| `uv pip check --python .venv/Scripts/python.exe` | 기존 27개 패키지 호환성 확인, 의존성 변경 없음 |
| `.\.venv\Scripts\python.exe -X utf8 -m scripts.verify_agent` | 실제 Olist DB의 4개 지표 모두 에이전트·worker 경로 결과가 Phase 3 기준 SQL과 일치, 원본 DB 지문 유지, 실제 API 0회 |
| `.\.venv\Scripts\python.exe -X utf8 -m scripts.ask --live "2017년 1월 월별 매출과 주문수를 보여줘." --start 2017-01-01 --end 2017-02-01 --max-llm-calls 1 --max-sql-repairs 0` | 실제 한국어 모델 SQL 생성 → 검증 → 조회 success, Phase 3 결과 일치, 종료 코드 0 |

### 오프라인 검증의 실제 범위

- 단일 SELECT·CTE와 기본 함수·기간 바인딩·정규화 왕복, 고정 엔진 버전과 범위별 CTE 해석을 검사했다.
- 쓰기·다중 문장·COPY/ATTACH/SET/확장·파일/HTTP·테이블 함수·시스템 테이블·동적 SQL·범위 밖 CTE·재귀/UNION/교차 조인·알 수 없는 함수/형식·과대 SQL을 차단했다. 주석/문자열 속 명령은 실행하지 않으며 키워드 오탐도 방지했다.
- 읽기 전용 원본의 DELETE, 외부 파일 읽기, 설정 재활성화를 실제 엔진에 직접 요청해 거부를 확인했다. 제한된 뷰의 리뷰 텍스트 조회는 바인딩 실패하며 원문·경로를 오류 응답으로 보내지 않는다.
- 별도 프로세스 timeout 종료·DB 지문 보존, API 키/PYTHONPATH 없는 자식 환경, 행 상한·셀/JSON 상한·빈 기간 커버리지를 확인했다. 16MB 엔진에서 고정된 대형 해시 집계가 OutOfMemory로 종료되는 것도 테스트했다. 이 고정 자원 테스트는 엔진 경계 확인을 위해 애플리케이션 문법을 우회한 신뢰하는 테스트 쿼리다.
- 생성→검사→조회→종료, 기간 확인, 범위 밖 요청, 안전한 1회 수정, 반복 실패 종료, 낮춘 예산·상한 초과 설정 거부, 지표 변경 금지, API 인증/429/시간 초과/잘린 출력·DB 자원 오류의 즉시 종료를 검사했다.
- 안전하지만 잘못된 주문 상태를 사용한 SQL을 실행 전 KPI 구조 대조로 탐지하고, 1회 수정 뒤에만 조회하는 경로를 확인했다. Decimal이 아닌 금액·모델 JSON 중복 키/추가 필드/잘못된 형식도 성공으로 넘기지 않았다.
- 초기 통합 점검에서 `enable_progress_bar`를 연결의 전역 config로 지정해 worker가 execution 오류로 종료했다. 해당 옵션을 연결 후 신뢰하는 SET으로 옮긴 뒤 실제 조회·전체 테스트가 통과했다. 원시 오류는 모델에 전송하지 않았다.

### 실제 데이터와 모델 검증

실 API 없는 실제 DB 대조 기간은 `[2016-09-01, 2018-11-01)`이다. monthly_sales 23행·category_sales 5행·delivery_delays 23행·review_delay 2행이 기존 Phase 3 SQL과 일치했다. 고정 모의 SQL을 사용한 경로 검사이며 새로운 한국어 모델 성능이나 독립 KPI 계산 검증으로 표현하지 않는다. 로컬 근거는 `data/processed/phase5_offline_verification.json`이다.

실제 모델 검증 결과 기록 시각은 2026-10-30 00:25:54 KST(2026-10-29 15:25:54 UTC)다. 원래 NVIDIA 모델·주소를 확인한 후 한국어 질문 1개·모델 최대 1회·출력 최대 1024토큰·SQL 수정 0회로 실행했다. 질문·필요한 스키마·승인 KPI와 SQL 예시만 모델에 전달했으며 조회 결과·원본·리뷰를 전송하지 않았다.

| 실제 결과 | 값 |
| --- | --- |
| 상태·지표 | success · monthly_sales |
| LLM 호출·실 API 시도·SQL 수정·후보 DB 조회 | 1 · 1 · 0 · 1 |
| 모델 소요 시간 | 5.417324초 (조회 프로세스 시간과 별개) |
| 입력·출력·총 토큰 | 1926 · 335 · 2261 |
| 2017년 1월 배송 완료 주문·상품 행 | 750 · 913 |
| 상품금액·결측 주문/가격 | 111798.36(원본 단위) · 0/0 |
| Phase 3 동일 기간 결과 대조 | 일치 |

로컬 근거 `data/processed/phase5_live_check.json`에는 SQL·제한된 집계·상태·사용량이 있으며 Git 제외 대상이다. API 키는 인증 헤더에만 사용하고 문맥·결과 파일·로그·공개 파일에 넣지 않았다. 추가 실제 API 호출은 하지 않았다.

미검증: 실제 모델의 나머지 3개 지표·다양한 한국어 표현, UI·다중 사용자·공개 배포·OS 권한 샌드박스·계정 잔여 한도·금전 비용. DB memory_limit은 전체 RSS 상한이 아니며 별도 프로세스와 설정만으로 완전한 OS 권한 격리를 주장하지 않는다. 초기 지원 범위는 승인 KPI 4개와 바인딩된 기간 변경이다. Phase 6은 착수하지 않았다.

게시 전 변경 파일 19개의 UTF-8·마지막 줄·공백·문서 상대 링크·펜스·충돌 표식·비밀값 패턴 검사를 통과했다. 공개 후보 50개 파일에 로컬 키 문자열이 없음을 값 출력 없이 확인했다. `.env`·실제/오프라인 결과 JSON은 Git 제외 대상이며 requirements 두 파일의 변경은 없다. `git diff --check`도 통과했다.

## 2026-10-29 — Phase 4 설정 검토·최소 실제 연결

사용자가 API 설정 완료를 알려 기존 Phase 4의 남은 연결 검증을 수행했다. 애플리케이션 코드·의존성 변경 없이 문서 상태와 증거만 갱신한다. 아래 이전 날짜의 키 미설정 기록은 당시 상태다.

| 실제 실행 명령·점검 | 결과 |
| --- | --- |
| `load_settings()` 결과의 비밀값 없는 검토 | 설정 유효·키 존재·계획한 NVIDIA 주소/모델 일치. HTTP 단계별 타임아웃 30초·일반 출력 상한 1024토큰 |
| `git check-ignore .env`; `git ls-files -- .env` | .env는 제외 대상, 추적 파일 없음. 파일 내용·키 값 출력 없음 |
| `.\.venv\Scripts\python.exe -X utf8 -m pytest -q --tb=short` | 전체 83개 통과, 종료 코드 0 |
| `uv pip check --python .venv/Scripts/python.exe` | 27개 패키지 호환성 확인, 종료 코드 0 |
| `.\.venv\Scripts\python.exe -X utf8 -m scripts.check_nvidia --live` | 상태 ok·기대 답변 일치·요청 1회·자동 재시도 0회, 종료 코드 0 |

실제 연결 시각은 2026-10-29 14:49:27 UTC(23:49:27 KST)다. 모델은 `nvidia/nemotron-3.5-lightning-30b-a3b`, 주소는 `https://integrate.api.nvidia.com/v1`이며 고정 연결 문장만 보냈다. 최대 출력 64토큰·비스트리밍·thinking 비활성화 설정을 유지했다.

| 실제 반환 메타데이터 | 값 |
| --- | --- |
| 소요 시간(초) | 1.038514 |
| prompt_tokens | 23 |
| completion_tokens | 2 |
| total_tokens | 25 |
| attempts / automatic_retries | 1 / 0 |
| status / expected_reply | ok / true |

로컬 메타데이터는 `data/processed/nvidia_connection_check.json`에 기록했다. API 키·원시 응답·원시 오류는 출력·저장하지 않았으며, 원본 CSV·DB·리뷰·스키마·집계를 전송하지 않았다. 로컬 보고서와 `.env`는 Git에서 제외한다. 추가 실제 호출은 수행하지 않았다.

현재 키의 모델 접근과 해당 요청의 수용·응답을 검증했다. 한국어 SQL 생성 정확도·SQL 안전성·자연어 분석 앱·계정 잔여 한도·금전 비용은 이번 시험 범위 밖이다. Phase 4 구현·검증은 완료했고 사용자 최종 검토를 기다린다. Phase 5는 착수하지 않았다.

게시 전 변경 문서 6개의 UTF-8·공백·펜스·상대 링크·충돌 표식·비밀값 패턴을 검사했고, 추적 파일 37개에 로컬 API 키 문자열이 포함되지 않음을 값 출력 없이 확인했다. `.env`와 실제 연결 JSON의 Git 제외 및 `git diff --check`도 통과했다. 문서 검사와 위 애플리케이션 회귀 테스트를 구분한다.

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

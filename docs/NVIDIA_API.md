# NVIDIA API 연동

Phase 4 검증일: 2026-10-29. 이후 사용자 요청으로 검토 승인을 반영했다. 2026-10-30 Phase 5 에이전트에서 이 어댑터를 재사용했으며 상세 결과는 [PHASE5_AGENT](PHASE5_AGENT.md)에 있다.

## 구현 범위와 공식 근거

`scripts/llm_client.py`는 텍스트 질문과 제한된 시스템 문맥을 받아 NVIDIA의 텍스트 답변·사용량·소요 시간을 반환한다. DB·CSV를 읽거나 생성 SQL을 실행하는 기능은 없다. 에이전트·SQL 안전성 검사는 별도 [Phase 5 구성 요소](PHASE5_AGENT.md)로 구현했다.

- [NVIDIA Build 모델 예제](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b): OpenAI 호환 Python 클라이언트, 모델 식별자, API 기본 주소와 chat completions 호출을 확인했다.
- [NVIDIA API Reference](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-5-lightning-30b-a3b): 해당 모델의 API 문서 위치를 확인했다.
- [NVIDIA 배포 모델 카드](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16/blob/28ae02f54748b2784572c929585adff2d0d62130/README.md): `enable_thinking=False`로 직접 답변하는 예제를 확인했다. 이번 어댑터는 이 설정과 비스트리밍 호출을 사용한다. 2026-10-29 실제 호스팅 API가 해당 요청을 수용하고 기대 답변을 반환했다.

조사한 모델 카드의 지원 언어 목록에는 한국어가 명시되지 않았다. Phase 5에서 실제 한국어 질문 1개를 기준 SQL과 대조했으며 다양한 표현·다른 지표 성능은 추가 평가 대상이다. 영어 연결 문장 성공으로 대신하지 않는다.

의존성은 공식 예제의 `openai`와 로컬 설정을 읽는 `python-dotenv`를 추가했다. 각각 3.37.0·1.2.4로 해결되었으며, 기존 데이터 패키지 버전은 유지했다. 하위 의존성 포함 총 27개를 `requirements.txt`에 버전·해시로 고정했다. OpenAI 서비스 대신 명시한 NVIDIA 주소로 요청한다.

## 로컬 설정

이 PC의 `.env`는 사용자가 키 설정을 완료했고 실제 호출까지 검증했다. 추가 설정은 필요 없다. 아래는 새 체크아웃·키 교체 시의 안내다. `.env`가 없을 때 `.env.example`을 복사한다. `.env`는 Git에서 제외되며 키를 채팅·Issue·PR에 붙이지 않는다.

1. [모델 페이지](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b)에서 로그인하고 **Generate API Key**로 키를 발급한다. 계정별 이용 조건·잔여 한도는 해당 화면에서 확인한다.
2. 프로젝트 `.env`의 `NVIDIA_API_KEY=` 뒤에 키를 저장한다.
3. 설정이 완료되었다고 알려주면 Codex가 승인된 최소 연결 시험을 수행한다. 수동 실행 명령도 아래에 제공한다.

다음 이름과 제한은 **프로젝트에서 정의한 설정**이다. NVIDIA 계정 한도를 변경하는 설정이 아니다.

| 변수 | 기본값·규칙 |
| --- | --- |
| `NVIDIA_API_KEY` | 필수. 코드·설정 객체 repr·결과 보고서에 출력하지 않음 |
| `NVIDIA_BASE_URL` | `https://integrate.api.nvidia.com/v1`. 인증정보·쿼리·fragment 없는 HTTPS 주소. 변경한 주소로 키와 질문이 전달되므로 신뢰하는 제공자만 설정 |
| `NVIDIA_MODEL` | `nvidia/nemotron-3.5-lightning-30b-a3b` |
| `NVIDIA_TIMEOUT_SECONDS` | 30. 0 초과 120 이하. SDK 네트워크 단계별 타임아웃이며 전체 작업의 엄격한 벽시계 제한은 아님 |
| `NVIDIA_MAX_TOKENS` | 1024. 요청별 출력 상한, 프로젝트 허용값 1~4096 |

프로세스 환경변수가 프로젝트 `.env`보다 우선한다. 빈 환경변수도 우선하므로 잘못된 설정을 파일 값으로 조용히 대체하지 않는다. 다른 상위 폴더의 `.env`는 탐색하지 않으며 `${...}` 보간·프로세스 환경 변경도 하지 않는다.

## 연결 확인과 호출 예산

```powershell
# 설정만 검증. 키가 없으면 오류로 끝나며 네트워크 요청은 0회.
.\.venv\Scripts\python.exe -X utf8 -m scripts.check_nvidia

# 명시적인 실제 연결 시험: 요청 최대 1회, 출력 최대 64토큰.
.\.venv\Scripts\python.exe -X utf8 -m scripts.check_nvidia --live
```

실제 시험은 고정 문장 `Reply with the single word OK.`만 보낸다. 고객·리뷰·스키마·집계는 보내지 않는다. 출력은 `min(64, NVIDIA_MAX_TOKENS)`, SDK 재시도는 0회, 리다이렉트도 따라가지 않는다. 실패 후 다른 모델·설정으로 자동 재호출하지 않는다. 이 Phase의 실제 시험 예산은 1회이며 추가 시도는 오류와 필요한 조치를 먼저 검토한다. 계정의 금전 비용·크레딧을 코드에서 조회하거나 보장하지 않는다.

`--live` 결과만 로컬 `data/processed/nvidia_connection_check.json`에 저장한다. 상태·요청 시도 수·소요 시간·제공자가 반환한 토큰 사용량·기대 답변 일치 여부를 기록하며 응답 본문·키·원시 오류는 저장하지 않는다. 사용량이 없으면 `null`로 두고 0으로 추정하지 않는다. 잘린 답변도 사용량이 반환되면 기록한다. `expected_reply=false`인 정상 텍스트 응답은 전송 성공과 지시 준수 여부를 구분해 보여준다.

## 오류 계약과 제한

| 코드 | 의미·동작 |
| --- | --- |
| `configuration`, `invalid_input` | 키·설정·입력 문제. API 요청 0회 |
| `authentication` | HTTP 401·403. 즉시 종료, 키·권한 점검 |
| `quota` | HTTP 429. 즉시 종료, 계정 한도 확인 |
| `timeout`, `connection` | 시간 초과·네트워크 오류. 즉시 종료 |
| `request`, `server` | 잘못된 요청·모델 미제공·리다이렉트·서버 오류. HTTP 상태만 기록하고 종료 |
| `output_limit` | 토큰 상한으로 잘린 답변. 불완전한 SQL로 이어지지 않도록 폐기 |
| `empty_response`, `invalid_response`, `unsupported_response` | 빈 답변·잘못된 형식·도구 호출·필터 등. 성공으로 처리하지 않음 |

질문과 시스템 문맥 합계는 24,000자 이내이며 초과 시 임의 자르기 없이 거부한다. 이 길이 제한만으로 원본 데이터 전송을 허용하지 않는다. Phase 5 호출자는 승인된 스키마·KPI·예시와 질문만 문맥으로 구성한다. 반환 텍스트를 검증 전 SQL로 실행해서는 안 된다. 질문당 총 호출 제한은 Phase 5 상태 관리에서 별도로 적용한다.

## 검증 상태

- 설치된 실제 SDK의 HTTP 전송을 메모리 대체해 요청·응답 직렬화와 실패 처리를 검사했다. 합성 키만 사용하며 인터넷·실 API가 필요 없다.
- Phase 4 신규 테스트 49개, 기존 적재·SQL 포함 총 83개 통과. 2026-10-29 전체 83개와 의존성 일관성을 다시 검증했다. 환경 연동·컴파일은 2026-10-24 통과 기록이 있다.
- 실제 연결: 2026-10-29 23:49:27 KST, 요청 1회·재시도 0회·약 1.04초, 입력 23·출력 2·총 25토큰, 기대 답변 일치. 현재 키의 모델 접근과 요청 파라미터 수용을 확인했다.
- 연결 상태·사용량은 로컬 `data/processed/nvidia_connection_check.json`과 [검증 기록](TEST_EVIDENCE.md)에 보관한다. 실제 키·응답 본문·로컬 JSON은 Git에 올리지 않는다. 한국어 SQL 정확도·계정 잔여 한도·금전 비용은 미검증이다.
- 상세 명령과 초기 실패·수정은 [TEST_EVIDENCE](TEST_EVIDENCE.md)를 참조한다.

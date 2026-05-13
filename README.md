# 증권 리포트

네이버 증권 뉴스를 수집하고 Gemini API로 투자 관점 요약을 생성해 매일 아침 이메일로 발송하는 서버리스 뉴스레터 자동화 프로젝트입니다.

## 주요 기능

- 최근 24시간 네이버 증권 뉴스 수집
- 섹션, 언론사, 조회수 기반 랭킹
- 자카드 유사도 기반 중복 기사 제거
- 환율, 주요 지수 등 매크로 컨텍스트 주입
- Top 5 심층 분석과 나머지 기사 Quick View 생성
- Jinja2 HTML 템플릿 기반 SMTP 발송
- GitHub Actions 스케줄 실행

## 리포트 구성

- `Top 5 Deep Dive`: 랭킹 상위 5개 기사의 상세 요약, 투자 관점, 수혜 섹터, 리스크를 보여줍니다.
- `Quick View`: 상위 5개를 제외한 주요 기사들을 한 줄 요약과 긍정/중립/부정 신호로 빠르게 훑어보는 섹션입니다.

## 로컬 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env`에 값을 채운 뒤 실행합니다.

```powershell
python main.py
```

메일 발송 없이 HTML만 확인하려면:

```powershell
python main.py --dry-run --allow-ai-fallback
```

결과 HTML은 `out/newsletter.html`에 생성됩니다.

로컬 프록시 인증서 문제로 크롤링이 막힐 때만 다음처럼 SSL 검증을 끌 수 있습니다.

```powershell
python main.py --dry-run --allow-ai-fallback --no-verify-ssl
```

## 환경 변수

| 이름 | 설명 |
| --- | --- |
| `GEMINI_API_KEY` | Google AI Studio에서 생성한 Gemini API 키 |
| `GEMINI_MODEL` | 기본값 `gemini-2.5-flash` |
| `ALLOW_AI_FALLBACK` | Gemini 실패 시 기본 요약으로 발송할지 여부. 기본값 `false` |
| `NEWS_LIMIT` | 분석 대상 기사 수. 기본값 `50` |
| `MAX_PAGES` | 네이버 증권 섹션별 수집 페이지 수. 기본값 `4` |
| `MAIL_USER` | 발신 이메일 |
| `MAIL_PWD` | SMTP 앱 비밀번호 |
| `MAIL_TO` | 수신 이메일. 쉼표로 다중 지정 가능 |
| `SMTP_HOST` | 기본값 `smtp.gmail.com` |
| `SMTP_PORT` | 기본값 `587` |
| `HTTP_VERIFY_SSL` | 크롤링 요청의 SSL 검증 여부. 기본값 `true` |

사내 프록시나 로컬 인증서 체인 문제로 네이버 요청이 실패할 때만 `HTTP_VERIFY_SSL=false`를 사용할 수 있습니다. GitHub Actions에서는 기본값을 유지하는 편이 안전합니다.

## GitHub Secrets

GitHub 저장소의 `Settings > Secrets and variables > Actions`에 다음 값을 추가합니다.

필수 Secrets:

- `GEMINI_API_KEY`
- `MAIL_USER`
- `MAIL_PWD`
- `MAIL_TO`

선택 Secrets:

- `SMTP_HOST`
- `SMTP_PORT`

선택 Variables:

- `GEMINI_MODEL`: 기본값 `gemini-2.5-flash`
- `ALLOW_AI_FALLBACK`: `true`로 설정하면 Gemini 오류가 나도 기본 요약 리포트를 발송합니다.
- `NEWS_LIMIT`: Gemini 호출량을 줄이고 싶으면 `20` 또는 `30`으로 낮출 수 있습니다.
- `MAX_PAGES`: 크롤링 시간을 줄이고 싶으면 `2` 정도로 낮출 수 있습니다.

## 장애 대응

GitHub Actions 로그에 `GEMINI_API_KEY is required`가 나오면 GitHub Secrets에 `GEMINI_API_KEY`가 없거나 이름이 잘못 등록된 것입니다. 기존 `OPENAI_API_KEY`는 더 이상 사용하지 않습니다.

Gemini quota, rate limit, billing 오류가 나오면 Google AI Studio 또는 Google Cloud 쪽에서 API 키의 사용량 제한과 결제 상태를 확인해야 합니다.

메일 발송 자체를 먼저 검증하려면 GitHub Variables에 `ALLOW_AI_FALLBACK=true`를 등록한 뒤 수동 실행하세요. 이 경우 AI 심층 분석 대신 원문 기반 기본 요약으로 발송됩니다.

## 운영 메모

이 프로젝트는 DB를 사용하지 않습니다. 실행 시점 기준 최근 24시간 기사만 처리하므로 GitHub Actions 스케줄이 실패하면 해당 실행분만 누락됩니다. 크롤링 대상 HTML 구조가 바뀔 수 있으므로 수집량이 급감하면 `stockinsight/collector.py`의 선택자와 URL을 확인해야 합니다.

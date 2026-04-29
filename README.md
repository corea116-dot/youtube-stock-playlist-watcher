# YouTube Stock Playlist Watcher

특정 YouTube 재생목록에 새 영상이 올라왔는지 확인하고, 영상에서 언급된 종목/섹터/이유를 정리해 이메일로 보내기 위한 Python 자동화 프로젝트입니다.

> 현재 단계는 **GitHub Actions 자동 실행 설정을 추가한 단계**입니다.

## 이 프로젝트의 목표

- 특정 YouTube 재생목록의 새 영상을 감지합니다.
- 새 영상의 제목, 설명, 자막을 분석합니다.
- 영상에서 언급된 추천 종목, 관심 종목, 섹터, 언급 이유를 정리합니다.
- 정리된 내용을 이메일로 보냅니다.
- 새 영상이 없으면 이메일을 보내지 않습니다.
- 이미 처리한 영상은 다시 처리하지 않습니다.

## 중요한 원칙

이 프로젝트는 **투자 조언 생성 도구가 아닙니다**.

프로그램은 영상에서 실제로 언급된 내용을 정리하는 용도로만 사용합니다. 영상에 나오지 않은 종목, 매수/매도 판단, 수익률 전망을 새로 만들어내지 않도록 설계할 예정입니다.

## 비밀값 관리 방식

API 키, 이메일 비밀번호, 토큰 같은 비밀값은 코드에 직접 넣지 않습니다.

현재 설정 코드는 Python 실행 환경에 등록된 환경변수를 읽습니다. 나중에 GitHub Actions에서 실행할 때는 **GitHub Secrets** 값을 환경변수로 넘기게 만들 예정입니다.

로컬 테스트용으로 `.env` 파일을 만들 수는 있지만, `.env` 파일은 GitHub에 올리지 않습니다. `.env.example`은 실제 값이 아니라 “어떤 이름의 값이 필요한지” 보여주는 참고용 파일입니다.

필요한 비밀값 이름은 `.env.example` 파일에 예시로 정리되어 있습니다.

## 환경변수 목록

환경변수는 프로그램 밖에서 넣어주는 설정값입니다. 비밀번호나 API 키를 코드에 직접 쓰지 않기 위해 사용합니다.

| 이름 | 역할 | 필수 여부 |
| --- | --- | --- |
| `YOUTUBE_API_KEY` | YouTube Data API로 재생목록 영상을 읽을 때 필요한 키 | 필수 |
| `GEMINI_API_KEY` | 영상 내용을 요약할 때 사용할 Google Gemini API 키 | 필수 |
| `PLAYLIST_IDS` | 여러 YouTube 재생목록 ID를 쉼표로 연결한 값 | 권장, `PLAYLIST_ID`가 없으면 필수 |
| `PLAYLIST_ID` | 감시할 YouTube 재생목록 ID 1개. 기존 방식 호환용 | 선택, `PLAYLIST_IDS`가 없으면 사용 |
| `SMTP_HOST` | 이메일을 보낼 SMTP 서버 주소 | 필수 |
| `SMTP_PORT` | SMTP 서버 포트 번호. 숫자여야 합니다. | 필수 |
| `SMTP_USER` | SMTP 로그인 계정. 보통 이메일 주소입니다. | 필수 |
| `SMTP_PASS` | SMTP 비밀번호 또는 앱 비밀번호 | 필수 |
| `EMAIL_TO` | 요약 메일을 받을 이메일 주소 | 필수 |
| `MAX_VIDEOS_TO_CHECK` | 한 번 실행할 때 확인할 최근 영상 개수 | 선택, 기본값 5 |
| `GEMINI_MODEL` | 요약에 사용할 Gemini 모델 이름 | 선택, 기본값 `gemini-2.5-flash-lite` |

초보자 기준으로는 `.env.example` 파일을 보고 어떤 이름의 비밀값이 필요한지 확인하면 됩니다. 실제 값은 `.env.example`에 넣지 말고, 로컬에서는 `.env`, GitHub에서는 GitHub Secrets에 넣습니다.

## YouTube API Key와 Playlist ID 설명

### YouTube API Key란?

`YOUTUBE_API_KEY`는 이 프로그램이 YouTube Data API에 “재생목록 영상 목록을 알려달라”고 요청할 때 사용하는 키입니다.

초보자 기준으로는 집 열쇠라기보다 “Google Cloud에서 발급받은 API 사용 허가 번호”에 가깝습니다. 이 값은 비밀값이므로 코드에 직접 쓰거나 GitHub에 공개하면 안 됩니다.

이 프로젝트에서는 YouTube Data API의 `playlistItems.list` 요청을 사용해 재생목록 안의 영상 제목, 설명, 게시일, 영상 ID를 가져옵니다.

### Playlist ID란?

Playlist ID는 감시할 YouTube 재생목록의 고유 ID입니다.

재생목록 주소가 아래와 같다면:

```text
https://www.youtube.com/playlist?list=PL_example_123
```

`list=` 뒤에 있는 값이 Playlist ID입니다.

```text
PL_example_123
```

### 여러 재생목록 등록하기

여러 재생목록을 동시에 감시하려면 GitHub Secrets 또는 로컬 환경변수에 `PLAYLIST_IDS`를 등록합니다.

값은 전체 URL이 아니라 `list=` 뒤의 재생목록 ID만 쉼표로 연결합니다.

예:

```text
PLAYLIST_IDS=PLabc123,PLdef456,PLghi789
```

공백이 조금 들어가도 프로그램이 안전하게 처리합니다.

```text
PLAYLIST_IDS=PLabc123, PLdef456, PLghi789
```

기존처럼 재생목록 1개만 감시하려면 `PLAYLIST_ID`를 사용할 수 있습니다. 하지만 여러 개를 사용할 가능성이 있다면 `PLAYLIST_IDS` 사용을 권장합니다.

### 한 번에 몇 개의 영상을 확인하나요?

`MAX_VIDEOS_TO_CHECK` 값만큼 각 재생목록의 최근 영상을 확인합니다. 값을 따로 설정하지 않으면 기본값은 `5`입니다.

예를 들어 `MAX_VIDEOS_TO_CHECK=5`이고 재생목록이 3개라면 최대 15개 영상을 확인할 수 있습니다.

YouTube Data API의 한 번 요청 제한 때문에 내부적으로 한 번에 최대 50개까지만 요청합니다. 이 프로젝트는 설정한 `MAX_VIDEOS_TO_CHECK`보다 많은 영상을 반환하지 않습니다.

## 자막/대본 수집 기능

영상 자막은 `youtube-transcript-api` 패키지를 사용해 가져옵니다.

현재 단계에서 만든 함수:

```python
get_transcript_text(video_id: str) -> str | None
```

동작 방식:

- YouTube 영상 ID를 받아 자막 텍스트를 가져옵니다.
- 한국어 자막이 있으면 한국어를 우선 사용합니다.
- 한국어 자막이 없으면 영어 자막을 사용합니다.
- 자막이 없거나 가져오기에 실패하면 `None`을 반환합니다.
- 자막 실패 때문에 프로그램 전체가 멈추지 않도록 설계했습니다.

### 자막 수집 기능의 한계

YouTube 영상이라고 해서 항상 자막을 가져올 수 있는 것은 아닙니다.

자막을 가져오지 못할 수 있는 경우:

- 영상에 한국어/영어 자막이 없는 경우
- 영상이 비공개, 삭제, 연령 제한 상태인 경우
- 영상 소유자가 자막 접근을 제한한 경우
- YouTube가 일시적으로 자막 접근을 막는 경우
- GitHub Actions 같은 클라우드 실행 환경의 IP가 YouTube에서 차단되는 경우

이 경우 프로그램은 에러로 완전히 멈추지 않고 `None`을 반환합니다. 자막이 없으면 곧바로 제목/설명만 분석하지 않고, 먼저 Gemini의 public YouTube URL 직접 분석 기능을 사용합니다.

## Gemini 분석 기능

영상 제목, 설명, 자막 텍스트 또는 public YouTube URL을 Google Gemini API에 보내 종목/섹터/언급 이유를 구조화합니다.

현재 단계에서 만든 함수:

```python
analyze_video(
    video: dict,
    transcript_text: str | None,
) -> dict
```

기존 전체 실행 흐름과의 호환을 위해 아래 함수도 유지합니다.

```python
analyze_video_content(
    title: str,
    description: str,
    transcript_text: str | None,
) -> dict
```

분석 결과에는 다음 항목이 들어갑니다.

- 영상에서 추천으로 언급된 종목
- 영상에서 관심 종목 또는 지켜볼 종목으로 언급된 항목
- 영상에서 언급된 섹터 또는 테마
- 각 항목의 언급 이유
- 리스크
- 분석 기준
- 영상 내용에서 확인 가능한 근거
- 불확실한 항목
- 투자 조언이 아니라 영상 요약이라는 안내 문구

중요한 제한:

- 이 기능은 투자 조언을 새로 만들지 않습니다.
- 영상에 없는 종목, 티커, 매수/매도 판단, 목표가를 추측하지 않도록 프롬프트를 구성했습니다.
- 자막이 있으면 자막 기반으로 분석합니다.
- 자막이 없으면 Gemini에 public YouTube URL을 직접 전달해 영상/음성 내용을 분석하도록 시도합니다.
- Gemini YouTube URL 직접 분석도 실패하면 제목/설명/태그/댓글 기반 제한 분석으로 fallback합니다.
- 댓글 기반 분석은 영상 발언이 아니라 시청자 반응/보조 단서이므로 정확도가 낮을 수 있습니다.
- 댓글도 가져오지 못하면 최후에만 제목/설명/태그 기반 제한 분석을 사용합니다.
- Gemini YouTube URL 직접 분석은 public YouTube 영상에서만 동작합니다. 비공개, 삭제, 연령 제한, 접근 제한 영상에서는 실패할 수 있습니다.
- videos.list와 commentThreads.list를 추가로 사용할 수 있어 YouTube API quota 사용량이 이전보다 늘어날 수 있습니다.
- 실제 분석을 실행하려면 `GEMINI_API_KEY` 환경변수가 필요합니다.

### Gemini API Key 발급 방법

Gemini API Key는 Google AI Studio에서 만들 수 있습니다.

초보자 기준 순서:

1. 브라우저에서 Google AI Studio에 접속합니다.
2. Google 계정으로 로그인합니다.
3. `Get API key` 또는 API 키 메뉴를 엽니다.
4. 새 API 키를 만듭니다.
5. 만든 키는 코드나 README에 붙여넣지 말고 GitHub Secrets의 `GEMINI_API_KEY`에 등록합니다.

이 프로젝트의 기본 Gemini 모델은 무료 티어에서 가볍게 쓰기 위한 `gemini-2.5-flash-lite`입니다. 다른 모델을 쓰고 싶으면 GitHub Secrets의 `GEMINI_MODEL` 값을 바꾸면 됩니다.

## 이메일 발송 기능

분석 결과는 SMTP를 사용해 이메일로 보냅니다.

현재 단계에서 만든 함수:

```python
send_analysis_email(analyses: list[dict]) -> None
```

동작 방식:

- 분석 결과가 비어 있으면 이메일을 보내지 않고 로그만 남깁니다.
- 분석 결과가 있으면 HTML 이메일과 plain text 대체 본문을 함께 만듭니다.
- 이메일 제목은 `[YouTube 종목 분석] 새 영상 분석 결과`입니다.
- SMTP 발송에 실패해도 프로그램 전체가 갑자기 죽지 않게 로그를 남기고 종료합니다.

이메일 본문에는 영상별로 다음 내용을 넣습니다.

- 영상 제목
- 영상 URL
- 요약
- 언급 종목
- 언급 섹터
- 언급 이유
- 리스크 또는 불확실한 항목
- confidence
- 투자 조언이 아니라 영상 내용 요약이라는 안내문

### Gmail SMTP를 사용할 때 주의할 점

Gmail SMTP를 사용할 경우 일반 Gmail 로그인 비밀번호를 코드에 넣으면 안 됩니다.

대신 Google 계정에서 **App Password**를 만들어 `SMTP_PASS` 값으로 사용해야 합니다. App Password도 비밀번호이므로 코드에 직접 쓰거나 GitHub에 공개하면 안 됩니다.

GitHub Actions에서 실행할 때는 아래 SMTP 관련 값을 GitHub Secrets에 등록해야 합니다.

```text
SMTP_HOST
SMTP_PORT
SMTP_USER
SMTP_PASS
EMAIL_TO
```

예를 들어 Gmail을 사용한다면 일반적으로 다음과 비슷합니다.

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_gmail_app_password
EMAIL_TO=receiver@example.com
```

위 값은 예시입니다. 실제 비밀번호나 App Password는 `.env.example`이 아니라 로컬 환경변수 또는 GitHub Secrets에만 넣어야 합니다. `.env` 파일은 `.gitignore`에 의해 Git에 올라가지 않도록 유지합니다.

## 전체 실행 흐름

`main.py`는 지금까지 만든 기능을 아래 순서로 연결합니다.

1. 환경변수 설정값을 읽습니다.
2. `PLAYLIST_IDS` 또는 `PLAYLIST_ID`에 설정된 YouTube 재생목록에서 최근 영상을 가져옵니다.
3. `data/processed_videos.json`에 이미 기록된 영상은 제외합니다.
4. 같은 영상이 여러 재생목록에 있어도 `video_id` 기준으로 한 번만 분석합니다.
5. 새 영상이 없으면 `No new videos` 로그를 남기고 이메일 없이 종료합니다.
6. 새 영상마다 자막을 가져옵니다.
7. 자막이 있으면 자막 기반으로 Gemini 분석을 실행합니다.
8. 자막이 없으면 Gemini YouTube URL 직접 분석을 먼저 시도합니다.
9. URL 직접 분석도 실패하면 제목/설명/태그/댓글 기반 제한 분석을 시도합니다.
10. 댓글도 없거나 실패하면 제목/설명/태그 기반 제한 분석을 사용합니다.
11. 분석에 성공한 결과가 있으면 이메일을 보냅니다.
12. 이메일 발송이 성공한 경우에만 해당 `video_id`를 처리 완료로 기록합니다.

특정 영상 하나에서 자막 수집이나 분석이 실패해도, 가능한 경우 다른 새 영상 처리는 계속 진행합니다.

## GitHub에 올리고 자동 실행하기

### 1. GitHub에 새 repository 만들기

GitHub 웹사이트에서 새 repository를 만듭니다.

초보자 기준 순서:

1. GitHub에 로그인합니다.
2. 오른쪽 위 `+` 버튼을 누릅니다.
3. `New repository`를 선택합니다.
4. repository 이름을 입력합니다.
5. 공개 여부를 선택합니다.
6. `Create repository`를 누릅니다.

### 2. 로컬 프로젝트를 GitHub에 push하기

GitHub가 새 repository를 만든 뒤 보여주는 주소를 사용합니다.

예시:

```bash
git remote add origin https://github.com/YOUR_NAME/YOUR_REPOSITORY.git
git branch -M main
git push -u origin main
```

의미:

- `git remote add origin ...`: 내 컴퓨터의 프로젝트와 GitHub repository를 연결합니다.
- `git branch -M main`: 기본 브랜치 이름을 `main`으로 맞춥니다.
- `git push -u origin main`: 현재 커밋들을 GitHub에 올립니다.

### 3. GitHub Secrets 등록하기

API 키, SMTP 비밀번호, Gmail App Password 같은 비밀값은 GitHub Secrets에 등록해야 합니다.

등록 위치:

```text
GitHub repository 페이지
→ Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

등록해야 하는 Secrets:

```text
YOUTUBE_API_KEY
GEMINI_API_KEY
PLAYLIST_IDS
PLAYLIST_ID
SMTP_HOST
SMTP_PORT
SMTP_USER
SMTP_PASS
EMAIL_TO
MAX_VIDEOS_TO_CHECK
GEMINI_MODEL
```

주의:

- 실제 값은 코드, README, `.env.example`에 넣지 마세요.
- `.env` 파일은 로컬 테스트용으로만 사용하고 GitHub에 올리지 마세요.
- GitHub Actions는 Secrets 값을 환경변수로 받아 실행합니다.

### 4. Actions 탭에서 수동 실행하기

수동 실행 방법:

1. GitHub repository에서 `Actions` 탭을 엽니다.
2. 왼쪽에서 `Watch YouTube Playlist` workflow를 선택합니다.
3. `Run workflow` 버튼을 누릅니다.
4. 초록색 실행 항목을 눌러 로그를 확인합니다.

로그에는 Secret 값이 출력되지 않도록 했습니다. 대신 “시작”, “의존성 설치”, “프로그램 실행”, “변경사항 커밋 여부” 같은 단계만 보이게 됩니다.

### 5. 자동 실행 시간

현재 GitHub Actions는 매일 한국시간 오후 6시에 실행되도록 설정했습니다.

GitHub Actions의 cron은 UTC 기준입니다.

```yaml
schedule:
  - cron: "0 9 * * *"
```

의미:

- `09:00 UTC`에 실행
- 한국시간은 UTC보다 9시간 빠르므로 한국시간 `18:00`, 즉 오후 6시에 실행

자동 실행 시간을 바꾸려면 `.github/workflows/watch.yml` 파일의 `cron` 값을 바꾸면 됩니다.

예를 들어 한국시간 오전 8시에 실행하고 싶다면 UTC 전날 오후 11시이므로:

```yaml
schedule:
  - cron: "0 23 * * *"
```

### 6. `processed_videos.json`이 자동 commit되는 이유

`data/processed_videos.json`은 이미 처리한 YouTube 영상 ID를 기억하는 파일입니다.

GitHub Actions는 매번 새 컴퓨터처럼 깨끗한 환경에서 실행됩니다. 그래서 이 파일의 변경사항을 GitHub repository에 다시 저장하지 않으면, 다음 실행 때 같은 영상을 또 새 영상으로 착각할 수 있습니다.

그래서 workflow는 실행 후 `data/processed_videos.json`이 바뀌었는지 확인합니다.

- 변경사항이 있으면 `Update processed videos`라는 커밋으로 저장하고 push합니다.
- 변경사항이 없으면 `No changes to commit.`이라고 출력하고 넘어갑니다.

## 이미 처리한 영상 기록 파일

이미 처리한 영상 ID는 아래 파일에 기록합니다.

```text
data/processed_videos.json
```

초기 내용은 다음과 같습니다.

```json
{
  "processed_video_ids": []
}
```

의미:

- `processed_video_ids`는 이미 처리한 YouTube 영상 ID 목록입니다.
- 처음에는 처리한 영상이 없으므로 빈 목록 `[]`입니다.
- 나중에 영상 하나를 성공적으로 처리하면 해당 영상 ID가 이 목록에 추가됩니다.
- 이 기록 덕분에 같은 영상을 반복해서 분석하거나 이메일로 다시 보내지 않을 수 있습니다.

## 초보자용 로컬 준비 흐름

아래 명령어들은 나중에 로컬에서 테스트할 때 사용합니다. 지금 단계에서는 구조만 준비되어 있으므로 실제 기능 실행은 아직 되지 않습니다.

### 1. Python 버전 확인

```bash
python3 --version
```

내 Mac에 Python 3가 설치되어 있는지 확인하는 명령어입니다.

### 2. 가상환경 만들기

```bash
python3 -m venv .venv
```

이 프로젝트 전용 Python 공간을 만듭니다. Mac 전체 Python 환경을 건드리지 않기 위해 사용합니다.

### 3. 가상환경 켜기

```bash
source .venv/bin/activate
```

현재 터미널에서 이 프로젝트 전용 Python 환경을 사용하겠다는 뜻입니다.

### 4. 프로젝트 설치하기

```bash
pip install -e .
```

현재 폴더의 Python 프로젝트를 실행 가능한 형태로 설치합니다.

### 5. 로컬에서 전체 흐름 실행하기

환경변수를 모두 준비한 뒤 아래 명령어로 실행할 수 있습니다.

```bash
python -m playlist_watcher.main
```

의미:

- YouTube 영상 목록 확인
- 새 영상만 분석
- 분석 결과 이메일 발송
- 이메일 발송 성공 시 처리 완료 기록

설치 후에는 아래 명령어도 사용할 수 있습니다.

```bash
playlist-watcher
```

초보자 주의사항:

- 실제 실행에는 YouTube API Key, Gemini API Key, SMTP 설정이 필요합니다.
- 일반 Gmail 비밀번호를 코드에 넣지 마세요.
- Gmail을 쓴다면 Gmail App Password를 `SMTP_PASS`로 사용하세요.
- 새 영상이 없으면 `No new videos` 로그가 나오고 이메일은 발송되지 않습니다.
- 아직 GitHub Actions 자동 실행은 연결하지 않았습니다.

## 현재 파일 구조

```text
youtube-stock-playlist-watcher/
├── README.md
├── pyproject.toml
├── .gitignore
├── .github/
│   └── workflows/
│       └── watch.yml
├── .env.example
├── data/
│   └── processed_videos.json
└── src/
    └── playlist_watcher/
        ├── __init__.py
        ├── analyzer.py
        ├── config.py
        ├── emailer.py
        ├── main.py
        ├── state.py
        ├── transcript.py
        └── youtube.py
```

## 다음 단계 예정

1. 실제 GitHub repository에 push
2. GitHub Secrets 등록
3. Actions 탭에서 수동 실행 테스트

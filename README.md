# YouTube Stock Playlist Watcher

특정 YouTube 재생목록에 새 영상이 올라왔는지 확인하고, 영상에서 언급된 종목/섹터/이유를 정리해 이메일로 보내기 위한 Python 자동화 프로젝트입니다.

> 현재 단계는 **분석 결과 이메일 발송 기능 준비 단계**입니다.  
> 아직 GitHub Actions 자동 실행, 전체 실행 연결 기능은 구현되어 있지 않습니다.

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
| `OPENAI_API_KEY` | 나중에 영상 내용을 요약할 때 사용할 OpenAI API 키 | 필수 |
| `PLAYLIST_ID` | 감시할 YouTube 재생목록 ID | 필수 |
| `SMTP_HOST` | 이메일을 보낼 SMTP 서버 주소 | 필수 |
| `SMTP_PORT` | SMTP 서버 포트 번호. 숫자여야 합니다. | 필수 |
| `SMTP_USER` | SMTP 로그인 계정. 보통 이메일 주소입니다. | 필수 |
| `SMTP_PASS` | SMTP 비밀번호 또는 앱 비밀번호 | 필수 |
| `EMAIL_TO` | 요약 메일을 받을 이메일 주소 | 필수 |
| `MAX_VIDEOS_TO_CHECK` | 한 번 실행할 때 확인할 최근 영상 개수 | 선택, 기본값 5 |
| `OPENAI_MODEL` | 나중에 요약에 사용할 OpenAI 모델 이름 | 선택, 기본값 있음 |

초보자 기준으로는 `.env.example` 파일을 보고 어떤 이름의 비밀값이 필요한지 확인하면 됩니다. 실제 값은 `.env.example`에 넣지 말고, 로컬에서는 `.env`, GitHub에서는 GitHub Secrets에 넣습니다.

## YouTube API Key와 Playlist ID 설명

### YouTube API Key란?

`YOUTUBE_API_KEY`는 이 프로그램이 YouTube Data API에 “재생목록 영상 목록을 알려달라”고 요청할 때 사용하는 키입니다.

초보자 기준으로는 집 열쇠라기보다 “Google Cloud에서 발급받은 API 사용 허가 번호”에 가깝습니다. 이 값은 비밀값이므로 코드에 직접 쓰거나 GitHub에 공개하면 안 됩니다.

이 프로젝트에서는 YouTube Data API의 `playlistItems.list` 요청을 사용해 재생목록 안의 영상 제목, 설명, 게시일, 영상 ID를 가져옵니다.

### Playlist ID란?

`PLAYLIST_ID`는 감시할 YouTube 재생목록의 고유 ID입니다.

재생목록 주소가 아래와 같다면:

```text
https://www.youtube.com/playlist?list=PL_example_123
```

`list=` 뒤에 있는 값이 Playlist ID입니다.

```text
PL_example_123
```

### 한 번에 몇 개의 영상을 확인하나요?

`MAX_VIDEOS_TO_CHECK` 값만큼 최근 재생목록 영상을 확인합니다. 값을 따로 설정하지 않으면 기본값은 `5`입니다.

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

이 경우 프로그램은 에러로 완전히 멈추지 않고 `None`을 반환하게 만들었습니다. 나중에 전체 흐름을 연결할 때는 자막이 없으면 제목/설명만 분석하는 방식으로 처리할 예정입니다.

## OpenAI 분석 기능

영상 제목, 설명, 자막 텍스트를 OpenAI API에 보내 종목/섹터/언급 이유를 구조화합니다.

현재 단계에서 만든 함수:

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
- 영상 내용에서 확인 가능한 근거
- 불확실한 항목
- 투자 조언이 아니라 영상 요약이라는 안내 문구

중요한 제한:

- 이 기능은 투자 조언을 새로 만들지 않습니다.
- 영상에 없는 종목, 티커, 매수/매도 판단, 목표가를 추측하지 않도록 프롬프트를 구성했습니다.
- 자막이 없으면 나중에 전체 흐름에서 제목과 설명만으로 분석하게 연결할 예정입니다.
- 실제 분석을 실행하려면 `OPENAI_API_KEY` 환경변수가 필요합니다.

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

## 현재 파일 구조

```text
youtube-stock-playlist-watcher/
├── README.md
├── pyproject.toml
├── .gitignore
├── .env.example
├── data/
│   └── processed_videos.json
└── src/
    └── playlist_watcher/
        ├── __init__.py
        ├── analyzer.py
        ├── config.py
        ├── emailer.py
        ├── state.py
        ├── transcript.py
        └── youtube.py
```

## 다음 단계 예정

1. 전체 실행 흐름을 연결하는 `main.py`
2. GitHub Actions 자동 실행 설정

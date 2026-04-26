# Project Agent Instructions

## Git 저장 규칙

- 각 단계 구현이 끝나면 반드시 검증을 먼저 실행한다.
- 검증이 성공한 경우에만 git status를 확인한다.
- 변경사항이 있으면 git add . 를 실행한다.
- 그 다음 단계 내용을 요약한 커밋 메시지로 git commit을 실행한다.
- 커밋 메시지는 영어로 짧고 명확하게 작성한다.
  예:
  - Add transcript fetching
  - Add OpenAI analyzer
  - Add email sender
  - Wire main workflow
- 검증이 실패하면 커밋하지 않는다.
- 커밋 후에는 커밋 해시와 변경 파일 목록을 초보자 기준으로 설명한다.
- 기능 구현 없이 문서만 바꾼 경우도 검증 가능한 범위에서 확인 후 커밋한다.
- API 키, 비밀번호, 토큰, .env 파일은 절대 커밋하지 않는다.

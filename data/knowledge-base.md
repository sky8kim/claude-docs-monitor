# 🧠 Claude Code 종합 지식베이스 (NEXUS용)

> KAI가 숙지하고 김회장님에게 효율적으로 안내하기 위한 정리 문서
> 최종 업데이트: 2026-02-27 | 자동 모니터링 시스템 연동

---

## 1. Claude Code 핵심 개념

Claude Code는 Anthropic의 터미널 기반 AI 코딩 에이전트. 단순한 코딩 도구가 아니라 **컴퓨터 자동화 프레임워크**로, 파일 조작, 명령 실행, Git 관리, 외부 서비스 연결, 서브에이전트 위임까지 가능.

### 5대 핵심 시스템

| 시스템 | 역할 | 김회장님 활용 포인트 |
|--------|------|---------------------|
| **Configuration** | 설정 계층 관리 | CLAUDE.md로 NEXUS 프로젝트 규칙 정의 |
| **Permissions** | 도구별 권한 제어 | 자동화 작업시 불필요한 확인 제거 |
| **Hooks** | 이벤트 기반 자동 실행 | 파일 저장 후 자동 린팅, 커밋 후 자동 테스트 |
| **MCP** | 외부 서비스 연결 | 노션, Gmail, 더망고 연동 |
| **Subagents** | 작업 위임 + 격리 | 병렬 작업 처리, 탐색과 구현 분리 |

---

## 2. 설정 파일 체계

### 우선순위 (높은 → 낮은)

1. **Managed Settings** — 조직 정책 (재정의 불가)
   - Mac: `/Library/Application Support/ClaudeCode/managed-settings.json`
2. **User Settings** — 개인 전역 설정
   - `~/.claude/settings.json`
3. **Project Settings** — 프로젝트별 설정
   - `.claude/settings.json` (git에 포함)
   - `.claude/settings.local.json` (로컬 전용)

### CLAUDE.md — AI의 기억 파일

Claude가 매 세션마다 자동으로 읽는 마크다운 파일. 프로젝트 규칙, 코딩 표준, 워크플로 지침을 여기에 작성.

**파일 위치별 적용 범위:**

- `~/.claude/CLAUDE.md` — 모든 프로젝트에 적용 (글로벌)
- `프로젝트루트/CLAUDE.md` — 해당 프로젝트에만 적용
- `하위폴더/CLAUDE.md` — 해당 폴더 작업시 추가 로드

**Best Practice:**
- 150줄 이하로 유지
- 안정적인 컨텍스트만 넣기 (프로젝트 구조, 코딩 표준, 도구 선호도)
- `#` 키를 누르면 세션 중 CLAUDE.md 자동 업데이트 가능
- `/clear` 해도 CLAUDE.md 내용은 유지됨

### Rules — 모듈형 지침

`.claude/rules/*.md` 파일로 토픽별 규칙을 분리 관리. frontmatter로 특정 경로에만 적용 가능.

---

## 3. 확장 기능 상세

### 3-1. Skills (스킬)

마크다운 파일로 작성하는 재사용 가능한 지식/워크플로.

**종류:**
- **슬래시 커맨드** — `/deploy`, `/review` 등 수동 호출
- **자동 로드** — Claude가 관련 작업 감지시 자동 활성화

**위치:**
- `.claude/commands/` — 프로젝트 커맨드
- `~/.claude/commands/` — 개인 글로벌 커맨드

**예시 — 자동 커밋 스킬:**
```markdown
---
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git commit:*)
description: Create a git commit with context
---
## Context
- Current status: !`git status`
- Current diff: !`git diff HEAD`
- Current branch: !`git branch --show-current`

Create a meaningful commit message based on the changes above.
```

**김회장님 활용:**
- 더망고 상품 등록 워크플로 스킬
- NEXUS 배포 스킬
- 코드 리뷰 스킬

### 3-2. Subagents (서브에이전트)

별도의 컨텍스트 윈도우에서 독립적으로 실행되는 AI 에이전트.

**핵심 장점:**
- 메인 대화의 컨텍스트 오염 방지
- 병렬 실행으로 속도 향상
- 전문 분야별 에이전트 구성 가능

**정의 방법 (.claude/agents/):**
```markdown
---
name: code-reviewer
description: Reviews code for quality and security
tools: ["Read", "Grep", "Glob", "Bash"]
model: sonnet
---
You are a senior code reviewer...
```

**모델 전략:**
- **Opus** — 복잡한 추론 필요시 (아키텍처 설계, 어려운 디버깅)
- **Sonnet** — 일반 구현 작업 (기본값)
- **Haiku** — 탐색, 파일 검색, 간단한 질문 (비용 5x 절약)

**비용 최적화 팁:**
```json
// ~/.claude/settings.json
{
  "model": "sonnet",
  "env": {
    "CLAUDE_CODE_SUBAGENT_MODEL": "haiku",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "50"
  }
}
```

### 3-3. Hooks (훅)

특정 이벤트에서 자동 실행되는 쉘 스크립트. **프롬프트와 달리 100% 실행 보장.**

**이벤트 종류:**
- `PreToolUse` — 도구 실행 전 (차단/수정 가능)
- `PostToolUse` — 도구 실행 후 (린팅, 검증)
- `SessionStart` / `SessionEnd` — 세션 시작/종료
- `UserPromptSubmit` — 사용자 입력 제출시
- `Stop` / `SubagentStop` — 에이전트 완료시
- `WorktreeCreate` / `WorktreeRemove` — 워크트리 생성/삭제

**CLAUDE.md vs Hooks:**
- CLAUDE.md의 "rm -rf 사용 금지" → 컨텍스트 압력으로 무시될 수 있음
- Hooks의 rm -rf 차단 → 매번 100% 실행됨
- **규칙은 CLAUDE.md, 강제 실행은 Hooks**

### 3-4. MCP (Model Context Protocol)

외부 서비스와 연결하는 표준 프로토콜.

**설정 위치:**
- `.mcp.json` — 프로젝트 (git에 포함)
- `.claude/settings.local.json` — 프로젝트 로컬
- `~/.claude/settings.local.json` — 사용자 전역

**김회장님 관련 MCP:**
- 노션 — 자료 관리
- Gmail — 이메일
- Google Calendar — 일정
- Playwright/Chrome — 브라우저 자동화 (더망고 조작)
- PostgreSQL/SQLite — DB 연결

### 3-5. Plugins (플러그인)

Skills, Hooks, Subagents, MCP를 하나로 묶어 배포하는 패키지.

```bash
# 마켓플레이스에서 설치
/plugin marketplace add affaan-m/everything-claude-code
/plugin install everything-claude-code@everything-claude-code
```

---

## 4. 작업 모드와 단축키

| 모드 | 설명 | 전환 방법 |
|------|------|-----------|
| Normal | 각 작업마다 승인 필요 | 기본값 |
| Plan | 계획 설명 후 승인 대기 | Shift-Tab |
| Auto Accept | 모든 작업 자동 수락 | Shift-Tab |

**필수 단축키:**
- `Shift-Tab` — 모드 전환
- `Esc` — 이전 채팅 목록
- `Ctrl+C` — 중단/나가기
- `Ctrl+F` — 백그라운드 에이전트 종료 (2번 누르면 확인)
- `#` — CLAUDE.md 업데이트 프롬프트

**필수 슬래시 명령:**
- `/help` — 도움말
- `/model` — 모델 변경
- `/clear` — 컨텍스트 초기화 (토큰 절약)
- `/compact` — 컨텍스트 압축
- `/cost` — 현재 세션 비용 확인
- `/resume` — 이전 대화 재개
- `/status` — 로그인/플랜 상태
- `/allowed-tools` — 화이트리스트 설정

---

## 5. Remote Control (2026.02 신기능)

터미널에서 시작한 세션을 **모바일/웹에서 원격 제어**하는 기능.

**실행:**
```bash
claude remote-control
# 또는
/remote-control
```

**핵심:**
- 코드는 로컬 머신에서 실행 (클라우드로 안 감)
- QR 코드 스캔으로 모바일 연결
- 실시간 파일 변경 승인/거절 가능
- 여러 세션 동시 관리 가능
- 요구사항: Claude Code v2.1.52+, Max 구독

**김회장님 활용:**
- MacBook에서 작업 시작 → 이동 중 모바일로 모니터링
- 여러 원격 PC의 작업을 중앙에서 관제

---

## 6. 실전 최적화 팁

### 토큰/비용 절약
- `/clear` — 관련 없는 작업 사이에 사용
- `/compact` — 논리적 중단점에서 사용
- Haiku를 탐색용 서브에이전트에 배정 (40-50% 비용 절감)
- `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50` — 자동 압축 임계치

### 효율적 워크플로
- 복잡한 작업은 여러 세션으로 분리
- 세션 간 핸드오프: 계획을 파일에 작성 → `/clear` → 새 세션에서 파일 참조
- `claude --continue` (마지막 세션 이어서) 또는 `claude --resume` (선택)
- Git worktree로 병렬 작업 격리: `claude --worktree`

### 보안 주의사항
- `.env` 파일 접근 차단 설정 필수
- 프로젝트 `.claude/settings.json`의 hooks는 보안 위험 있음 (CVE-2026-21852)
- `permissions.deny`로 민감한 명령 차단

### 주 1회 개선 루프
- `/insights` 실행 → 패턴 분석
- 반복 실수 → Hook으로 차단
- 반복 워크플로 → Skill로 추출
- CLAUDE.md 주기적 업데이트

---

## 7. 구독 플랜별 사용량

| 플랜 | 가격 | Claude Code 사용 | 모델 |
|------|------|-----------------|------|
| Pro | $20/월 | 제한적 | Sonnet |
| Max 5x | $100/월 | ~225 메시지/5시간 | 50%까지 Opus, 나머지 Sonnet |
| Max 20x | $200/월 | ~900 메시지/5시간 | Opus 우선 |
| API | 종량제 | 무제한 | 선택 가능 |

---

## 8. NEXUS 프로젝트 맞춤 적용 가이드

### 추천 CLAUDE.md 구조 (글로벌)
```markdown
# NEXUS System - KAI Configuration

## 시스템 정보
- 운영자: 김회장님 (1인 개발자 겸 사업가)
- 시스템: NEXUS (넥서스)
- 사업자: 55개 간이사업자 (해외구매대행)
- 핵심 도구: 더망고, n8n, Antigravity

## 코딩 규칙
- 한국어 주석 우선
- 바이브코딩: 절차별 검토 및 단계 확인
- 결과 보고는 간결하게
- 중간 허용은 절차 관련만 최소한

## 프로젝트 구조
- nexus-manager: NEXUS 관리 대시보드
- cc-system: 바이브 코딩 시스템
```

### 추천 서브에이전트 구성
- **planner** — 작업 분해 및 계획 수립
- **code-reviewer** — 코드 품질/보안 검토
- **security-auditor** — 보안 취약점 분석
- **explorer** — 코드베이스 탐색 (Haiku 모델로 비용 절감)

### 추천 Hooks
- PostToolUse(Write) → 자동 린팅
- Stop → 작업 완료 요약을 노션에 기록
- SessionStart → NEXUS 프로젝트 상태 로드

---

> 이 문서는 Claude Docs Monitor가 변경사항을 감지할 때마다 업데이트됩니다.
> 노션 DB: claude-docs-monitor
> GitHub: sky8kim/claude-docs-monitor


---

## 📋 변경 이력 (자동 업데이트)

> 마지막 업데이트: 2026-03-01 02:50 UTC

---

### 🔄 2026-03-01 02:50 UTC

- **[Claude Code]** Claude Code Overview ([링크](https://docs.anthropic.com/en/docs/claude-code/overview))
- **[Claude Code]** Claude Code Quickstart ([링크](https://code.claude.com/docs/ko/quickstart))
- **[Claude Code]** Claude Code CLI Reference ([링크](https://docs.anthropic.com/en/docs/claude-code/cli-reference))
- **[Claude Code]** Claude Code MCP ([링크](https://docs.anthropic.com/en/docs/claude-code/mcp))
- **[Claude Code]** Claude Code Settings ([링크](https://docs.anthropic.com/en/docs/claude-code/settings))
- **[API]** Claude API Changelog ([링크](https://docs.anthropic.com/en/docs/about-claude/models))
- **[API]** Claude API Tool Use ([링크](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview))
- **[API]** Claude API MCP Connector ([링크](https://docs.anthropic.com/en/docs/build-with-claude/mcp-connector))
- **[News]** Anthropic News ([링크](https://www.anthropic.com/news))
- **[Release]** Claude Code GitHub Releases ([링크](https://github.com/anthropics/claude-code/releases))

**요약:** - [Claude Code] Claude Code Overview
- [Claude Code] Claude Code Quickstart
- [Claude Code] Claude Code CLI Reference
- [Claude Code] Claude Code MCP
- [Claude Code] Claude Code Settings
- [API] Claude API Changelog
- [API] Claude API Tool Use
- [API] Claude API MCP Connector
- [News] Anthropic News
- [Release] Claude Code GitHub Releases

---

### 🔄 2026-02-28 02:24 UTC

- **[Claude Code]** Claude Code CLI Reference ([링크](https://docs.anthropic.com/en/docs/claude-code/cli-reference))
- **[Claude Code]** Claude Code MCP ([링크](https://docs.anthropic.com/en/docs/claude-code/mcp))
- **[Claude Code]** Claude Code Settings ([링크](https://docs.anthropic.com/en/docs/claude-code/settings))
- **[API]** Claude API Changelog ([링크](https://docs.anthropic.com/en/docs/about-claude/models))
- **[API]** Claude API Tool Use ([링크](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview))
- **[API]** Claude API MCP Connector ([링크](https://docs.anthropic.com/en/docs/build-with-claude/mcp-connector))
- **[News]** Anthropic News ([링크](https://www.anthropic.com/news))
- **[Release]** Claude Code GitHub Releases ([링크](https://github.com/anthropics/claude-code/releases))

**요약:** - [Claude Code] Claude Code CLI Reference
- [Claude Code] Claude Code MCP
- [Claude Code] Claude Code Settings
- [API] Claude API Changelog
- [API] Claude API Tool Use
- [API] Claude API MCP Connector
- [News] Anthropic News
- [Release] Claude Code GitHub Releases

---

### 🔄 2026-02-28 01:08 UTC

- **[Claude Code]** Claude Code Overview ([링크](https://docs.anthropic.com/en/docs/claude-code/overview))
- **[Claude Code]** Claude Code Quickstart ([링크](https://code.claude.com/docs/ko/quickstart))
- **[Claude Code]** Claude Code CLI Reference ([링크](https://docs.anthropic.com/en/docs/claude-code/cli-reference))
- **[Claude Code]** Claude Code MCP ([링크](https://docs.anthropic.com/en/docs/claude-code/mcp))
- **[Claude Code]** Claude Code Settings ([링크](https://docs.anthropic.com/en/docs/claude-code/settings))
- **[API]** Claude API Changelog ([링크](https://docs.anthropic.com/en/docs/about-claude/models))
- **[API]** Claude API Tool Use ([링크](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview))
- **[API]** Claude API MCP Connector ([링크](https://docs.anthropic.com/en/docs/build-with-claude/mcp-connector))
- **[News]** Anthropic News ([링크](https://www.anthropic.com/news))
- **[Release]** Claude Code GitHub Releases ([링크](https://github.com/anthropics/claude-code/releases))

**요약:** - [Claude Code] Claude Code Overview
- [Claude Code] Claude Code Quickstart
- [Claude Code] Claude Code CLI Reference
- [Claude Code] Claude Code MCP
- [Claude Code] Claude Code Settings
- [API] Claude API Changelog
- [API] Claude API Tool Use
- [API] Claude API MCP Connector
- [News] Anthropic News
- [Release] Claude Code GitHub Releases

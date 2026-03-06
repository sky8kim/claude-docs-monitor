"""
Claude Docs Monitor v2 (방법C 풀세팅)
- 공식 문서 크롤링 → 변경 감지 → 노션 DB 저장 → 노션 지식베이스 업데이트
- → knowledge-base.md 자동 생성 → Gmail 알림
"""

import os
import json
import hashlib
import datetime
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from pathlib import Path
from difflib import unified_diff

# ============================================================
# 설정
# ============================================================

MONITOR_URLS = [
    {
        "name": "Claude Code Overview",
        "url": "https://docs.anthropic.com/en/docs/claude-code/overview",
        "category": "Claude Code"
    },
    {
        "name": "Claude Code Quickstart",
        "url": "https://code.claude.com/docs/ko/quickstart",
        "category": "Claude Code"
    },
    {
        "name": "Claude Code CLI Reference",
        "url": "https://docs.anthropic.com/en/docs/claude-code/cli-reference",
        "category": "Claude Code"
    },
    {
        "name": "Claude Code MCP",
        "url": "https://docs.anthropic.com/en/docs/claude-code/mcp",
        "category": "Claude Code"
    },
    {
        "name": "Claude Code Settings",
        "url": "https://docs.anthropic.com/en/docs/claude-code/settings",
        "category": "Claude Code"
    },
    {
        "name": "Claude API Changelog",
        "url": "https://docs.anthropic.com/en/docs/about-claude/models",
        "category": "API"
    },
    {
        "name": "Claude API Tool Use",
        "url": "https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview",
        "category": "API"
    },
    {
        "name": "Claude API MCP Connector",
        "url": "https://docs.anthropic.com/en/docs/build-with-claude/mcp-connector",
        "category": "API"
    },
    {
        "name": "Anthropic News",
        "url": "https://www.anthropic.com/news",
        "category": "News"
    },
    {
        "name": "Claude Code GitHub Releases",
        "url": "https://github.com/anthropics/claude-code/releases",
        "category": "Release"
    },
]

# 환경변수에서 설정 로드
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")
NOTION_KB_PAGE_ID = os.environ.get("NOTION_KB_PAGE_ID", "")  # 지식베이스 페이지 ID
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY_FOR_SUMMARY", "")

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# ============================================================
# 크롤링
# ============================================================

def fetch_page(url: str) -> str:
    """웹 페이지 텍스트 내용 가져오기"""
    headers = {
        "User-Agent": "ClaudeDocsMonitor/2.0 (docs change detection)"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  ⚠️  크롤링 실패: {url} → {e}")
        return ""


def get_hash(content: str) -> str:
    """콘텐츠 해시값 생성"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_previous_data() -> dict:
    """이전 크롤링 데이터 로드"""
    filepath = DATA_DIR / "previous_hashes.json"
    if filepath.exists():
        return json.loads(filepath.read_text())
    return {}


def save_current_data(data: dict):
    """현재 크롤링 데이터 저장"""
    filepath = DATA_DIR / "previous_hashes.json"
    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def save_page_content(name: str, content: str):
    """페이지 내용을 파일로 저장 (diff 비교용)"""
    safe_name = name.replace(" ", "_").replace("/", "_")
    filepath = DATA_DIR / f"{safe_name}.txt"
    filepath.write_text(content)


def load_page_content(name: str) -> str:
    """이전 저장된 페이지 내용 로드"""
    safe_name = name.replace(" ", "_").replace("/", "_")
    filepath = DATA_DIR / f"{safe_name}.txt"
    if filepath.exists():
        return filepath.read_text()
    return ""

# ============================================================
# 변경 감지
# ============================================================

def detect_changes() -> list:
    """모든 URL을 크롤링하고 변경사항 감지"""
    previous = load_previous_data()
    current = {}
    changes = []

    for item in MONITOR_URLS:
        name = item["name"]
        url = item["url"]
        category = item["category"]

        print(f"🔍 크롤링 중: {name}")
        content = fetch_page(url)

        if not content:
            current[name] = previous.get(name, "")
            continue

        current_hash = get_hash(content)
        prev_hash = previous.get(name, "")

        if prev_hash and current_hash != prev_hash:
            old_content = load_page_content(name)
            diff_text = generate_diff(old_content, content, name)

            changes.append({
                "name": name,
                "url": url,
                "category": category,
                "diff": diff_text,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })
            print(f"  🔴 변경 감지: {name}")
        elif not prev_hash:
            print(f"  🟡 최초 등록: {name}")
        else:
            print(f"  🟢 변경 없음: {name}")

        current[name] = current_hash
        save_page_content(name, content)

    save_current_data(current)
    return changes


def generate_diff(old: str, new: str, name: str) -> str:
    """변경 내역 diff 생성"""
    if not old:
        return "(최초 크롤링 - 전체 내용 새로 등록)"

    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)

    diff = unified_diff(old_lines, new_lines, fromfile=f"{name} (이전)", tofile=f"{name} (현재)", lineterm="")
    diff_text = "".join(list(diff)[:200])

    return diff_text if diff_text else "(미세한 변경)"

# ============================================================
# Claude API로 변경 요약 생성
# ============================================================

def summarize_changes(changes: list) -> str:
    """Claude API로 변경사항 요약"""
    if not ANTHROPIC_API_KEY:
        summary_parts = []
        for c in changes:
            summary_parts.append(f"📌 [{c['category']}] {c['name']}\n   URL: {c['url']}\n   시간: {c['timestamp']}")
        return "\n\n".join(summary_parts)

    try:
        changes_text = "\n\n---\n\n".join([
            f"문서: {c['name']}\nURL: {c['url']}\n카테고리: {c['category']}\nDiff:\n{c['diff'][:2000]}"
            for c in changes
        ])

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1500,
                "messages": [
                    {
                        "role": "user",
                        "content": f"""다음은 Claude 공식 문서의 변경사항입니다.
한국어로 핵심 변경 내용을 간결하게 요약해주세요.
각 변경사항마다:
1. 무엇이 바뀌었는지
2. 실무에 미치는 영향
3. 적용할 수 있는 팁

변경사항:
{changes_text}"""
                    }
                ]
            },
            timeout=60,
        )
        if resp.status_code != 200:
            print(f"⚠️  Claude API 오류 ({resp.status_code}): {resp.text[:200]}")
            return "\n".join([f"- [{c['category']}] {c['name']}" for c in changes])
        data = resp.json()
        return data["content"][0]["text"]
    except Exception as e:
        print(f"⚠️  Claude 요약 실패: {e}")
        return "\n".join([f"- [{c['category']}] {c['name']}" for c in changes])

# ============================================================
# 노션 DB 저장
# ============================================================

def save_to_notion(changes: list, summary: str):
    """변경사항을 노션 DB에 저장"""
    if not NOTION_API_KEY or not NOTION_DATABASE_ID:
        print("⚠️  노션 API 설정 없음 - 건너뜀")
        return

    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    changed_docs = ", ".join([c["name"] for c in changes])
    categories = list(set([c["category"] for c in changes]))

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "제목": {
                "title": [
                    {"text": {"content": f"📋 문서 변경 감지 ({now})"}}
                ]
            },
            "카테고리": {
                "multi_select": [{"name": cat} for cat in categories]
            },
            "감지 일시": {
                "date": {"start": datetime.datetime.now(datetime.timezone.utc).isoformat()}
            },
            "상태": {
                "select": {"name": "미확인"}
            },
        },
        "children": [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "📝 변경 요약"}}]
                }
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": summary[:2000]}}]
                }
            },
            {
                "object": "block",
                "type": "divider",
                "divider": {}
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "🔗 변경된 문서 링크"}}]
                }
            },
        ] + [
            {
                "object": "block",
                "type": "bookmark",
                "bookmark": {"url": c["url"]}
            }
            for c in changes
        ]
    }

    try:
        resp = requests.post(
            "https://api.notion.com/v1/pages",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if resp.status_code == 200:
            page_url = resp.json().get("url", "")
            print(f"✅ 노션 DB 저장 완료: {page_url}")
        else:
            print(f"⚠️  노션 DB 저장 실패: {resp.status_code} {resp.text[:300]}")
    except Exception as e:
        print(f"⚠️  노션 DB 저장 오류: {e}")

# ============================================================
# [NEW] 노션 지식베이스 페이지 업데이트
# ============================================================

def update_notion_knowledge_base(changes: list, summary: str):
    """노션 지식베이스 페이지에 변경 내용 추가"""
    if not NOTION_API_KEY or not NOTION_KB_PAGE_ID:
        print("⚠️  노션 지식베이스 페이지 ID 없음 - 건너뜀")
        return

    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    changed_names = ", ".join([c["name"] for c in changes])

    # 지식베이스 페이지에 블록 추가 (append)
    blocks = [
        {
            "object": "block",
            "type": "divider",
            "divider": {}
        },
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"text": {"content": f"🔄 업데이트 ({now})"}}],
                "color": "blue_background"
            }
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"text": {"content": f"변경 문서: {changed_names[:1500]}"}}
                ]
            }
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"text": {"content": summary[:2000]}}]
            }
        },
    ]

    # 변경된 문서 링크 추가
    for c in changes:
        blocks.append({
            "object": "block",
            "type": "bookmark",
            "bookmark": {"url": c["url"]}
        })

    try:
        resp = requests.patch(
            f"https://api.notion.com/v1/blocks/{NOTION_KB_PAGE_ID}/children",
            headers=headers,
            json={"children": blocks},
            timeout=30,
        )
        if resp.status_code == 200:
            print(f"✅ 노션 지식베이스 업데이트 완료")
        else:
            print(f"⚠️  노션 지식베이스 업데이트 실패: {resp.status_code} {resp.text[:300]}")
    except Exception as e:
        print(f"⚠️  노션 지식베이스 업데이트 오류: {e}")

# ============================================================
# [NEW] knowledge-base.md 자동 생성
# ============================================================

def generate_knowledge_base_md(changes: list, summary: str):
    """변경 내용을 반영한 knowledge-base.md 생성"""
    kb_path = DATA_DIR / "knowledge-base.md"
    changelog_path = DATA_DIR / "changelog.md"

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # 기존 changelog 로드 (있으면)
    existing_changelog = ""
    if changelog_path.exists():
        existing_changelog = changelog_path.read_text()

    # 새 변경 로그 추가
    new_entry = f"\n---\n\n### 🔄 {now}\n\n"
    for c in changes:
        new_entry += f"- **[{c['category']}]** {c['name']} ([링크]({c['url']}))\n"
    new_entry += f"\n**요약:** {summary[:1000]}\n"

    updated_changelog = new_entry + existing_changelog
    changelog_path.write_text(updated_changelog)

    # knowledge-base.md 전체 재생성
    # 기존 베이스 파일 읽기
    base_kb_path = Path(__file__).parent.parent / "knowledge-base-template.md"
    if base_kb_path.exists():
        base_content = base_kb_path.read_text()
    else:
        base_content = "# 🧠 Claude Code 종합 지식베이스 (NEXUS)\n\n> 템플릿 파일이 없습니다. knowledge-base-template.md를 추가해주세요.\n"

    # 베이스 + 변경 로그 결합
    full_content = base_content + f"\n\n---\n\n## 📋 변경 이력 (자동 업데이트)\n\n> 마지막 업데이트: {now}\n" + updated_changelog

    kb_path.write_text(full_content)
    print(f"✅ knowledge-base.md 생성 완료: {kb_path}")
    print(f"✅ changelog.md 업데이트 완료: {changelog_path}")

# ============================================================
# 이메일 알림 (업그레이드: 다운로드 링크 포함)
# ============================================================

def _clean_text(text: str) -> str:
    """이메일 호환을 위해 non-ASCII 공백 문자 정리"""
    return text.replace("\xa0", " ").replace("\u200b", "")


def send_email_alert(changes: list, summary: str):
    """Gmail로 변경 알림 발송 (GitHub 다운로드 링크 포함)"""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("⚠️  Gmail 설정 없음 - 건너뜀")
        return

    summary = _clean_text(summary)
    changes = [
        {k: _clean_text(v) if isinstance(v, str) else v for k, v in c.items()}
        for c in changes
    ]

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    github_kb_url = "https://github.com/sky8kim/claude-docs-monitor/blob/main/data/knowledge-base.md"
    github_raw_url = "https://raw.githubusercontent.com/sky8kim/claude-docs-monitor/main/data/knowledge-base.md"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(f"Claude 문서 변경 감지 ({len(changes)}건) - {now}", "utf-8")
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = GMAIL_ADDRESS

    changes_html = ""
    for c in changes:
        changes_html += f"""
        <tr>
            <td style="padding:8px;border:1px solid #333;background:#1a1a2e;color:#e0e0e0;">{c['category']}</td>
            <td style="padding:8px;border:1px solid #333;background:#1a1a2e;">
                <a href="{c['url']}" style="color:#4fc3f7;">{c['name']}</a>
            </td>
        </tr>"""

    html = f"""
    <html>
    <body style="background:#0d1117;color:#e0e0e0;font-family:sans-serif;padding:20px;">
        <div style="max-width:600px;margin:0 auto;background:#161b22;border-radius:12px;padding:24px;">
            <h1 style="color:#58a6ff;">🔔 Claude 문서 변경 감지</h1>
            <p style="color:#8b949e;">{now} | {len(changes)}건 변경</p>
            
            <h2 style="color:#f0883e;">📋 변경된 문서</h2>
            <table style="width:100%;border-collapse:collapse;">
                <tr>
                    <th style="padding:8px;border:1px solid #333;background:#21262d;color:#f0883e;">카테고리</th>
                    <th style="padding:8px;border:1px solid #333;background:#21262d;color:#f0883e;">문서</th>
                </tr>
                {changes_html}
            </table>
            
            <h2 style="color:#f0883e;margin-top:20px;">📝 변경 요약</h2>
            <div style="background:#1a1a2e;padding:16px;border-radius:8px;white-space:pre-wrap;line-height:1.6;">
{summary}
            </div>
            
            <h2 style="color:#f0883e;margin-top:20px;">📥 지식베이스 업데이트</h2>
            <div style="background:#1a1a2e;padding:16px;border-radius:8px;">
                <p>최신 knowledge-base.md가 자동 생성되었습니다.</p>
                <p>
                    <a href="{github_kb_url}" style="color:#4fc3f7;font-size:16px;">📄 GitHub에서 보기</a>
                    &nbsp;|&nbsp;
                    <a href="{github_raw_url}" style="color:#4fc3f7;font-size:16px;">⬇️ 다운로드</a>
                </p>
                <p style="color:#8b949e;font-size:12px;">
                    claude.ai 프로젝트 Knowledge에 이 파일을 교체하면 KAI가 최신 내용을 참조합니다.
                </p>
            </div>
            
            <p style="color:#8b949e;margin-top:20px;font-size:12px;">
                NEXUS Docs Monitor v2 | Powered by KAI
            </p>
        </div>
    </body>
    </html>
    """

    html = html.replace("\xa0", " ")
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, GMAIL_ADDRESS, msg.as_bytes())
        print(f"✅ 이메일 발송 완료: {GMAIL_ADDRESS}")
    except Exception as e:
        print(f"⚠️  이메일 발송 실패: {e}")

# ============================================================
# 메인 실행
# ============================================================

def main():
    print("=" * 60)
    print("🚀 NEXUS Claude Docs Monitor v2 실행")
    print(f"⏰ {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("=" * 60)

    # 1. 변경 감지
    changes = detect_changes()

    if not changes:
        print("\n✅ 변경사항 없음. 종료합니다.")
        return

    print(f"\n🔴 {len(changes)}건 변경 감지!")

    # 2. 변경 요약 생성
    print("\n📝 변경 요약 생성 중...")
    summary = summarize_changes(changes)
    print(summary)

    # 3. 노션 DB 저장
    print("\n📓 노션 DB 저장 중...")
    save_to_notion(changes, summary)

    # 4. [NEW] 노션 지식베이스 페이지 업데이트
    print("\n🧠 노션 지식베이스 업데이트 중...")
    update_notion_knowledge_base(changes, summary)

    # 5. [NEW] knowledge-base.md 자동 생성
    print("\n📄 knowledge-base.md 생성 중...")
    generate_knowledge_base_md(changes, summary)

    # 6. 이메일 알림
    print("\n📧 이메일 발송 중...")
    send_email_alert(changes, summary)

    # 7. 변경 로그 파일 저장 (최근 200건만 유지)
    log_file = DATA_DIR / "changes_log.json"
    existing_log = json.loads(log_file.read_text()) if log_file.exists() else []
    existing_log.extend(changes)
    existing_log = existing_log[-200:]
    log_file.write_text(json.dumps(existing_log, indent=2, ensure_ascii=False))

    print("\n✅ 모든 작업 완료!")


if __name__ == "__main__":
    main()

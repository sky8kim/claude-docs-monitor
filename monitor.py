"""
Claude Docs Monitor
- 공식 문서 크롤링 → 변경 감지 → 노션 저장 → 이메일 알림
"""

import os
import json
import hashlib
import datetime
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from difflib import unified_diff

# ============================================================
# 설정
# ============================================================

# 모니터링 대상 URL 목록
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
        "User-Agent": "ClaudeDocsMonitor/1.0 (docs change detection)"
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
            # 변경 감지됨
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
    diff_text = "".join(list(diff)[:200])  # 최대 200줄

    return diff_text if diff_text else "(미세한 변경)"

# ============================================================
# Claude API로 변경 요약 생성
# ============================================================

def summarize_changes(changes: list) -> str:
    """Claude API로 변경사항 요약"""
    if not ANTHROPIC_API_KEY:
        # API 키 없으면 간단 요약
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
        data = resp.json()
        return data["content"][0]["text"]
    except Exception as e:
        print(f"⚠️  Claude 요약 실패: {e}")
        return "\n".join([f"- [{c['category']}] {c['name']}" for c in changes])

# ============================================================
# 노션 저장
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

    # 노션 페이지 생성
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
            "변경 문서": {
                "rich_text": [
                    {"text": {"content": changed_docs[:2000]}}
                ]
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
            print(f"✅ 노션 저장 완료: {page_url}")
        else:
            print(f"⚠️  노션 저장 실패: {resp.status_code} {resp.text[:300]}")
    except Exception as e:
        print(f"⚠️  노션 저장 오류: {e}")

# ============================================================
# 이메일 알림
# ============================================================

def send_email_alert(changes: list, summary: str):
    """Gmail로 변경 알림 발송"""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("⚠️  Gmail 설정 없음 - 건너뜀")
        return

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 Claude 문서 변경 감지 ({len(changes)}건) - {now}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = GMAIL_ADDRESS

    # HTML 이메일 본문
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
            
            <p style="color:#8b949e;margin-top:20px;font-size:12px;">
                NEXUS Docs Monitor | Powered by KAI
            </p>
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, GMAIL_ADDRESS, msg.as_string())
        print(f"✅ 이메일 발송 완료: {GMAIL_ADDRESS}")
    except Exception as e:
        print(f"⚠️  이메일 발송 실패: {e}")

# ============================================================
# 메인 실행
# ============================================================

def main():
    print("=" * 60)
    print("🚀 NEXUS Claude Docs Monitor 실행")
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

    # 3. 노션 저장
    print("\n📓 노션 저장 중...")
    save_to_notion(changes, summary)

    # 4. 이메일 알림
    print("\n📧 이메일 발송 중...")
    send_email_alert(changes, summary)

    # 5. 변경 로그 파일 저장
    log_file = DATA_DIR / "changes_log.json"
    existing_log = json.loads(log_file.read_text()) if log_file.exists() else []
    existing_log.extend(changes)
    log_file.write_text(json.dumps(existing_log, indent=2, ensure_ascii=False))

    print("\n✅ 모든 작업 완료!")


if __name__ == "__main__":
    main()

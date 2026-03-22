"""
自主政策扫描器 — 可在 GitHub Actions 中独立运行
使用 Google Custom Search API 执行搜索，无需 AI Agent

环境变量:
  GOOGLE_CSE_API_KEY: Google Custom Search API Key
  GOOGLE_CSE_CX:     Custom Search Engine ID
"""
import json, os, re, hashlib, sys
from pathlib import Path
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.parse import quote_plus

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
CONFIG_FILE = DATA / "scan_config.json"
OUTPUT_FILE = DATA / "policy_scan.json"
TIMELINE_FILE = DATA / "policy_timeline.json"

API_KEY = os.environ.get("GOOGLE_CSE_API_KEY", "")
CX = os.environ.get("GOOGLE_CSE_CX", "")

CSE_URL = "https://www.googleapis.com/customsearch/v1?key={key}&cx={cx}&q={q}&num=5&lr=lang_zh-CN"


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def search_google(query: str, max_results: int = 5) -> list:
    """执行 Google Custom Search API 查询"""
    if not API_KEY or not CX:
        print(f"  ⚠ 无 API Key，跳过: {query[:50]}")
        return []
    url = CSE_URL.format(key=API_KEY, cx=CX, q=quote_plus(query))
    try:
        req = Request(url, headers={"User-Agent": "MHM-PolicyScanner/1.0"})
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        items = data.get("items", [])
        return [{
            "title": it.get("title", ""),
            "url": it.get("link", ""),
            "snippet": it.get("snippet", ""),
            "date": extract_date(it.get("snippet", "")),
        } for it in items[:max_results]]
    except Exception as e:
        print(f"  ❌ 搜索失败: {e}")
        return []


def extract_date(text: str) -> str:
    """从 snippet 中提取日期"""
    m = re.search(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    return datetime.now().strftime("%Y-%m")


def deduplicate(results: list) -> list:
    seen = set()
    out = []
    for r in results:
        h = hashlib.md5(re.sub(r"\s+", "", r["title"].lower()).encode()).hexdigest()[:12]
        if h not in seen:
            seen.add(h)
            out.append(r)
    return out


def run_scan():
    config = load_config()
    domains = config["scan_domains"]
    all_results = []
    now = datetime.now()

    print(f"\n🌐 自主政策扫描 | {now.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    for domain_key, domain_cfg in domains.items():
        label = domain_cfg["label"]
        emoji = domain_cfg["emoji"]
        keywords = domain_cfg["keywords"]
        print(f"\n{emoji} {label} — {len(keywords)} 个关键词")

        for i in range(0, len(keywords), 2):
            batch = keywords[i:i+2]
            query = " OR ".join(f'"{kw}"' for kw in batch) + " 2026"
            results = search_google(query)
            for r in results:
                r["domain"] = domain_key
                r["domain_label"] = label
                r["domain_emoji"] = emoji
            all_results.extend(results)
            print(f"  🔍 {query[:50]}... → {len(results)}条")

    # Competitor queries
    for prod_key, prod_cfg in config.get("competitors", {}).items():
        for rival in prod_cfg.get("rivals", []):
            for watch in rival.get("watch", [])[:2]:
                query = f'"{rival["name"]}" {watch} 2026'
                results = search_google(query)
                for r in results:
                    r["domain"] = "competitor_intel"
                    r["domain_label"] = "竞品情报"
                    r["domain_emoji"] = "🎯"
                all_results.extend(results)

    # Deduplicate
    unique = deduplicate(all_results)
    print(f"\n📊 去重后: {len(unique)} 条 (原始 {len(all_results)} 条)")

    # Check alerts
    from policy_scanner import check_alerts, categorize_results, build_scan_result
    report = build_scan_result(config, unique, now)

    # Save
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ 已保存: {OUTPUT_FILE}")

    return report


def update_timeline_status():
    """更新 policy_timeline.json 中各里程碑的状态"""
    if not TIMELINE_FILE.exists():
        return
    with open(TIMELINE_FILE, "r", encoding="utf-8") as f:
        tl = json.load(f)

    today = datetime.now().date()
    updated = 0
    for track in tl.get("policy_tracks", []):
        for ms in track.get("milestones", []):
            try:
                ms_date = datetime.strptime(ms["date"], "%Y-%m-%d").date()
            except:
                continue
            old_status = ms.get("status", "")
            if ms_date < today and old_status in ("即将执行", "待启动"):
                ms["status"] = "已落地"
                updated += 1
            elif ms_date == today and old_status == "即将执行":
                ms["status"] = "进行中"
                updated += 1

    if updated:
        tl["meta"]["generated"] = datetime.now().isoformat()
        with open(TIMELINE_FILE, "w", encoding="utf-8") as f:
            json.dump(tl, f, ensure_ascii=False, indent=2)
        print(f"✅ 时间线状态更新: {updated} 个里程碑")


if __name__ == "__main__":
    report = run_scan()
    update_timeline_status()
    print(f"\n🏁 扫描完成 | 总结果: {report['scan_metadata']['total_results']} | 预警: {report['scan_metadata']['total_alerts']}")

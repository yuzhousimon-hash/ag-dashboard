"""
全域政策扫描引擎 — 六纵三横情报收集系统
覆盖：国家医药政策 / 大健康 / 医药零售 / 电商 / 竞品情报 / 养老政策

用法:
  python policy_scanner.py                # 全量扫描，控制台输出
  python policy_scanner.py --json         # 输出JSON
  python policy_scanner.py --html         # 生成HTML报告
  python policy_scanner.py --domain pharma_retail  # 单域扫描
  python policy_scanner.py --days 3       # 自定义回溯天数
"""
import json, re, sys, hashlib
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import quote_plus

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
CONFIG_FILE = DATA / "scan_config.json"
OUTPUT_FILE = DATA / "policy_scan.json"
REPORT_DIR = DATA / "reports"

# ── Theme (consistent with proactive_engine.py) ──
MHM_GREEN = "#00a651"
WARN_YELLOW = "#f0ad4e"
WARN_RED = "#d9534f"
ACCENT_CYAN = "#2aa198"
BG_DARK = "#002b36"
BG_CARD = "#073642"
TEXT_WHITE = "#fdf6e3"
TEXT_LIGHT = "#93a1a1"
SEVERITY_COLORS = {
    "critical": WARN_RED,
    "high": WARN_YELLOW,
    "medium": ACCENT_CYAN,
    "low": MHM_GREEN,
}


def load_config():
    """加载扫描配置"""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_search_queries(config, domain_filter=None, lookback_days=7):
    """
    根据配置生成搜索查询列表
    每个query = domain + keyword组合，带时间过滤
    """
    domains = config["scan_domains"]
    queries = []

    for domain_key, domain_cfg in domains.items():
        if domain_filter and domain_key != domain_filter:
            continue

        keywords = domain_cfg["keywords"]
        # 将关键词分批组合，每次2-3个关键词
        for i in range(0, len(keywords), 2):
            batch = keywords[i:i+2]
            query_text = " OR ".join(f'"{kw}"' for kw in batch)

            queries.append({
                "domain": domain_key,
                "domain_label": domain_cfg["label"],
                "domain_emoji": domain_cfg["emoji"],
                "query": query_text,
                "keywords": batch,
                "lookback_days": lookback_days,
                "priority": domain_cfg["priority"],
            })

    # Sort by priority (lower = higher priority)
    queries.sort(key=lambda x: x["priority"])
    return queries


def generate_competitor_queries(config):
    """生成竞品搜索查询"""
    queries = []
    for product_key, product_cfg in config["competitors"].items():
        for rival in product_cfg["rivals"]:
            for watch_item in rival["watch"]:
                queries.append({
                    "domain": "competitor_intel",
                    "domain_label": f"竞品: {rival['name']}",
                    "domain_emoji": "🎯",
                    "query": f'"{rival["name"]}" {watch_item}',
                    "mhm_product": product_cfg["mhm_product"],
                    "rival_name": rival["name"],
                    "threat_level": rival["threat_level"],
                    "watch_dimension": watch_item,
                })
    return queries


def generate_wechat_queries(config, domain_filter=None):
    """
    生成微信公众号专项搜索查询
    策略：site:mp.weixin.qq.com + 关键词/账号名
    微信公众号是中国医药行业第一情报源，直接抓取不可行，
    但搜索引擎（尤其Google）会索引公开的WeChat文章
    """
    wechat_cfg = config.get("wechat_scan_strategy", {})
    if not wechat_cfg:
        return []

    queries = []

    # 1. 命名账号 + 域关键词交叉查询
    named_accounts = wechat_cfg.get("named_accounts", [])
    domains = config.get("scan_domains", {})

    for account in named_accounts:
        account_domains = account.get("domains", [])
        if domain_filter and domain_filter not in account_domains:
            continue

        for ad in account_domains:
            if domain_filter and ad != domain_filter:
                continue
            domain_cfg = domains.get(ad, {})
            # Pick top 2 keywords from the domain
            top_kws = domain_cfg.get("keywords", [])[:2]
            for kw in top_kws:
                queries.append({
                    "domain": ad,
                    "domain_label": f"📱 {account['name']}",
                    "domain_emoji": domain_cfg.get("emoji", "📱"),
                    "query": f'site:mp.weixin.qq.com "{account["name"]}" {kw}',
                    "source_type": "wechat",
                    "account_name": account["name"],
                    "priority": domain_cfg.get("priority", 5),
                })

    # 2. 跨域盘点类查询（捕捉年度/季度总结、深度分析、行业趋势文章）
    roundup_kws = wechat_cfg.get("cross_domain_roundup_keywords", [])
    for kw in roundup_kws:
        queries.append({
            "domain": "cross_domain",
            "domain_label": "📱 公众号深度",
            "domain_emoji": "📱",
            "query": f'site:mp.weixin.qq.com {kw}',
            "source_type": "wechat_roundup",
            "priority": 2,
        })

    return queries


def check_alerts(results, config):
    """检查扫描结果是否触发预警规则"""
    alerts = []
    alert_rules = config.get("alert_rules", [])

    for rule in alert_rules:
        trigger_kws = rule["trigger_keywords"]
        matched_results = []

        for r in results:
            title = r.get("title", "").lower()
            snippet = r.get("snippet", "").lower()
            combined = f"{title} {snippet}"

            for kw in trigger_kws:
                # Split keyword on space and check all parts present
                parts = kw.lower().split()
                if all(p in combined for p in parts):
                    matched_results.append(r)
                    break

        if matched_results:
            alerts.append({
                "rule_name": rule["name"],
                "severity": rule["severity"],
                "action": rule["action"],
                "color": SEVERITY_COLORS.get(rule["severity"], TEXT_LIGHT),
                "matched_count": len(matched_results),
                "matches": matched_results[:5],  # Top 5 matches
            })

    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda x: severity_order.get(x["severity"], 99))
    return alerts


def deduplicate_results(results):
    """基于标题相似度去重"""
    seen = set()
    unique = []
    for r in results:
        # Simple hash-based dedup on title
        title = r.get("title", "").strip()
        if not title:
            continue
        # Normalize: remove spaces, lowercase
        normalized = re.sub(r'\s+', '', title.lower())
        title_hash = hashlib.md5(normalized.encode()).hexdigest()[:12]
        if title_hash not in seen:
            seen.add(title_hash)
            unique.append(r)
    return unique


def categorize_results(results):
    """将结果按域分类汇总"""
    by_domain = {}
    for r in results:
        domain = r.get("domain", "unknown")
        if domain not in by_domain:
            by_domain[domain] = {
                "label": r.get("domain_label", domain),
                "emoji": r.get("domain_emoji", "📋"),
                "items": [],
            }
        by_domain[domain]["items"].append(r)
    return by_domain


def build_scan_result(config, scan_results, today=None):
    """组装最终扫描报告结构"""
    if today is None:
        today = datetime.now()

    # Deduplicate
    unique = deduplicate_results(scan_results)

    # Check alerts
    alerts = check_alerts(unique, config)

    # Categorize by domain
    by_domain = categorize_results(unique)

    # Calculate stats
    domain_stats = {}
    for dk, dv in by_domain.items():
        domain_stats[dk] = {
            "label": dv["label"],
            "emoji": dv["emoji"],
            "count": len(dv["items"]),
        }

    return {
        "scan_metadata": {
            "generated_at": today.strftime("%Y-%m-%d %H:%M"),
            "version": config.get("version", "1.0"),
            "total_results": len(unique),
            "total_alerts": len(alerts),
            "domains_scanned": len(by_domain),
        },
        "alerts": alerts,
        "domain_results": by_domain,
        "domain_stats": domain_stats,
        "competitor_highlights": [],  # Populated by competitor_tracker
    }


# ═══════════════════════════════════════════════════════
# 控制台输出
# ═══════════════════════════════════════════════════════
def print_console(report):
    lines = ["\n" + "═" * 60]
    lines.append("🌐 全域政策扫描引擎 | Policy Scanner v1.0")
    lines.append(f"扫描时间: {report['scan_metadata']['generated_at']}")
    lines.append(f"总结果: {report['scan_metadata']['total_results']} | "
                 f"预警: {report['scan_metadata']['total_alerts']} | "
                 f"域: {report['scan_metadata']['domains_scanned']}")
    lines.append("═" * 60)

    # Alerts
    if report["alerts"]:
        lines.append(f"\n🚨 预警触发 ({len(report['alerts'])}条)")
        lines.append("-" * 40)
        for a in report["alerts"]:
            icon = "🔴" if a["severity"] == "critical" else (
                "🟠" if a["severity"] == "high" else "🟡")
            lines.append(f"  {icon} [{a['rule_name']}] {a['matched_count']}条匹配 → {a['action']}")
            for m in a["matches"][:2]:
                lines.append(f"     📎 {m.get('title', 'N/A')[:60]}")

    # Domain results
    for dk, dv in report["domain_results"].items():
        lines.append(f"\n{dv['emoji']} {dv['label']} ({len(dv['items'])}条)")
        lines.append("-" * 40)
        for item in dv["items"][:5]:
            lines.append(f"  📌 {item.get('title', 'N/A')[:70]}")
            if item.get("url"):
                lines.append(f"     🔗 {item['url'][:80]}")

    lines.append("\n" + "═" * 60)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# HTML 报告
# ═══════════════════════════════════════════════════════
def generate_html(report):
    """生成HTML政策扫描报告"""
    meta = report["scan_metadata"]

    # Alert cards
    alert_html = ""
    for a in report["alerts"]:
        match_items = "".join(
            f'<li style="font-size:12px;color:{TEXT_LIGHT}">{m.get("title","N/A")[:80]}</li>'
            for m in a["matches"][:3]
        )
        alert_html += f'''
        <div style="background:{BG_CARD};border-left:4px solid {a['color']};
                    border-radius:6px;padding:10px 14px;margin:6px 0">
            <strong style="color:{a['color']}">[{a['severity'].upper()}] {a['rule_name']}</strong>
            <span style="color:{TEXT_LIGHT};font-size:12px"> — {a['matched_count']}条匹配</span>
            <ul style="margin:4px 0 0;padding-left:16px">{match_items}</ul>
        </div>'''

    # Domain sections
    domain_html = ""
    for dk, dv in report["domain_results"].items():
        rows = ""
        for item in dv["items"][:8]:
            url = item.get("url", "#")
            title = item.get("title", "N/A")[:80]
            snippet = item.get("snippet", "")[:120]
            date = item.get("date", "")
            rows += f'''<tr>
                <td style="padding:6px 8px;max-width:350px">
                    <a href="{url}" style="color:{ACCENT_CYAN};text-decoration:none">{title}</a>
                    <br><span style="font-size:11px;color:{TEXT_LIGHT}">{snippet}</span>
                </td>
                <td style="padding:6px 8px;font-size:11px;color:{TEXT_LIGHT};white-space:nowrap">{date}</td>
            </tr>'''

        domain_html += f'''
        <h3 style="color:{ACCENT_CYAN};margin:18px 0 6px">{dv['emoji']} {dv['label']}
            <span style="font-size:13px;color:{TEXT_LIGHT}">({len(dv['items'])}条)</span></h3>
        <table style="width:100%;border-collapse:collapse;background:{BG_CARD};border-radius:8px">
            <thead><tr style="border-bottom:2px solid {TEXT_LIGHT}">
                <th style="padding:8px;text-align:left;font-size:12px">标题 / 摘要</th>
                <th style="padding:8px;text-align:left;font-size:12px">日期</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table>'''

    # Stats bar
    stats_items = "".join(
        f'<div style="text-align:center;flex:1"><div style="font-size:20px;font-weight:bold;color:{MHM_GREEN}">'
        f'{s["count"]}</div><div style="font-size:11px;color:{TEXT_LIGHT}">{s["emoji"]} {s["label"]}</div></div>'
        for s in report["domain_stats"].values()
    )

    html = f'''<div style="font-family:'Segoe UI',Arial,sans-serif;max-width:800px;margin:0 auto;color:{TEXT_WHITE}">
    <h2 style="color:{MHM_GREEN};margin:0 0 8px">🌐 全域政策扫描报告</h2>
    <p style="color:{TEXT_LIGHT};font-size:12px;margin:0 0 15px">
        {meta['generated_at']} | 总 {meta['total_results']}条 | {meta['total_alerts']}条预警
    </p>

    <!-- Stats -->
    <div style="display:flex;gap:8px;background:{BG_CARD};border-radius:8px;padding:12px;margin-bottom:15px">
        {stats_items}
    </div>

    <!-- Alerts -->
    {'<h3 style="color:'+WARN_RED+';margin:15px 0 6px">🚨 预警 ('+str(len(report["alerts"]))+')</h3>' + alert_html if report["alerts"] else ''}

    <!-- Domain Results -->
    {domain_html}
</div>'''
    return html


# ═══════════════════════════════════════════════════════
# Agent入口：供外部Agent工具调用
# ═══════════════════════════════════════════════════════
def get_search_plan(domain_filter=None, lookback_days=7):
    """
    返回搜索计划（供Agent使用search_web执行）
    Agent工作流：
      1. 调用 get_search_plan() 获取查询列表
      2. 对每个query调用 search_web
      3. 收集结果后调用 process_results() 生成报告
    """
    config = load_config()
    queries = generate_search_queries(config, domain_filter, lookback_days)
    competitor_queries = generate_competitor_queries(config)
    wechat_queries = generate_wechat_queries(config, domain_filter)

    return {
        "policy_queries": queries,
        "competitor_queries": competitor_queries,
        "wechat_queries": wechat_queries,
        "total_queries": len(queries) + len(competitor_queries) + len(wechat_queries),
        "config": config,
    }


def process_results(raw_results, today_str=None):
    """
    处理Agent收集的原始搜索结果
    raw_results: list of dicts, each with:
      - domain, domain_label, domain_emoji
      - title, url, snippet, date (optional)
    """
    config = load_config()
    today = datetime.strptime(today_str, "%Y-%m-%d") if today_str else datetime.now()
    return build_scan_result(config, raw_results, today)


def save_report(report, fmt="json"):
    """保存报告"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d")

    if fmt == "json":
        out = OUTPUT_FILE
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        print(f"✅ JSON输出: {out}")
    elif fmt == "html":
        html = generate_html(report)
        out = REPORT_DIR / f"policy_scan_{ts}.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(f'<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
                    f'<body style="background:{BG_DARK};padding:20px">{html}</body></html>')
        print(f"✅ HTML报告: {out}")

    return str(out)


# ═══════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════
def main():
    args = sys.argv[1:]

    # Parse arguments
    domain_filter = None
    lookback_days = 7
    output_fmt = "console"

    if "--json" in args:
        output_fmt = "json"
    elif "--html" in args:
        output_fmt = "html"

    if "--domain" in args:
        idx = args.index("--domain")
        if idx + 1 < len(args):
            domain_filter = args[idx + 1]

    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            lookback_days = int(args[idx + 1])

    # Generate search plan
    plan = get_search_plan(domain_filter, lookback_days)

    print(f"\n🌐 全域政策扫描引擎 v1.0")
    print(f"域过滤: {domain_filter or '全部'} | 回溯: {lookback_days}天")
    print(f"政策查询: {len(plan['policy_queries'])}条 | 竞品查询: {len(plan['competitor_queries'])}条")
    print(f"\n{'='*60}")
    print("📋 搜索计划:")
    print(f"{'='*60}")

    for i, q in enumerate(plan["policy_queries"][:10], 1):
        print(f"  {i}. {q['domain_emoji']} [{q['domain_label']}] {q['query'][:60]}")

    if len(plan["policy_queries"]) > 10:
        print(f"  ... 及其他 {len(plan['policy_queries'])-10} 条查询")

    print(f"\n🎯 竞品查询: {len(plan['competitor_queries'])}条")
    for i, q in enumerate(plan["competitor_queries"][:5], 1):
        print(f"  {i}. {q['domain_label']}: {q['query'][:50]}")

    if len(plan["competitor_queries"]) > 5:
        print(f"  ... 及其他 {len(plan['competitor_queries'])-5} 条查询")

    print(f"\n💡 提示: 此引擎设计为Agent辅助执行。")
    print(f"   Agent使用 search_web 逐条执行查询，收集结果后调用 process_results() 生成报告。")
    print(f"   完整工作流请使用 /policy-scanner 命令。")


if __name__ == "__main__":
    main()

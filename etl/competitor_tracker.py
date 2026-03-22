"""
竞品情报追踪引擎 — 系统化监控MHM核心竞品动态
追踪维度：价格 / 准入 / 市场 / 学术 / 合规

用法:
  python competitor_tracker.py           # 控制台输出
  python competitor_tracker.py --json    # 输出JSON
  python competitor_tracker.py --product ginaton  # 单产品线

与 policy_scanner.py 联动：竞品查询由 scan_config.json 驱动
"""
import json, sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
CONFIG_FILE = DATA / "scan_config.json"
OUTPUT_FILE = DATA / "competitor_intel.json"

# ── Theme ──
MHM_GREEN = "#00a651"
WARN_YELLOW = "#f0ad4e"
WARN_RED = "#d9534f"
ACCENT_CYAN = "#2aa198"
BG_DARK = "#002b36"
BG_CARD = "#073642"
TEXT_WHITE = "#fdf6e3"
TEXT_LIGHT = "#93a1a1"

THREAT_COLORS = {
    "high": WARN_RED,
    "medium": WARN_YELLOW,
    "low": MHM_GREEN,
}


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_competitor_matrix(config, product_filter=None):
    """
    生成竞品监控矩阵
    返回结构化的竞品追踪计划供Agent执行
    """
    competitors = config.get("competitors", {})
    matrix = []

    for product_key, product_cfg in competitors.items():
        if product_filter and product_key != product_filter:
            continue

        product_entry = {
            "product_key": product_key,
            "mhm_product": product_cfg["mhm_product"],
            "mhm_specs": product_cfg["specs"],
            "rivals": [],
        }

        for rival in product_cfg["rivals"]:
            rival_entry = {
                "name": rival["name"],
                "manufacturers": rival.get("manufacturers", []),
                "specs": rival.get("specs", ""),
                "threat_level": rival["threat_level"],
                "threat_color": THREAT_COLORS.get(rival["threat_level"], TEXT_LIGHT),
                "watch_dimensions": rival["watch"],
                "search_queries": [],
            }

            # Generate search queries for each watch dimension
            for watch in rival["watch"]:
                rival_entry["search_queries"].append({
                    "query": f'"{rival["name"]}" {watch} 2026',
                    "dimension": watch,
                })

            product_entry["rivals"].append(rival_entry)

        matrix.append(product_entry)

    return matrix


def build_competitor_report(matrix, intel_data=None, today=None):
    """
    组装竞品情报报告
    intel_data: Agent收集的原始搜索结果 (list of dicts)
    """
    if today is None:
        today = datetime.now()

    # Organize intel by product line
    product_intel = {}
    if intel_data:
        for item in intel_data:
            pk = item.get("product_key", "unknown")
            if pk not in product_intel:
                product_intel[pk] = []
            product_intel[pk].append(item)

    return {
        "generated_at": today.strftime("%Y-%m-%d %H:%M"),
        "matrix": matrix,
        "intelligence": product_intel,
        "summary": {
            "total_rivals": sum(len(p["rivals"]) for p in matrix),
            "high_threat": sum(
                1 for p in matrix
                for r in p["rivals"]
                if r["threat_level"] == "high"
            ),
            "intel_items": len(intel_data) if intel_data else 0,
        },
    }


def print_console(report):
    """控制台输出竞品情报"""
    lines = ["\n" + "═" * 60]
    lines.append("🎯 竞品情报追踪引擎 | Competitor Tracker v1.0")
    lines.append(f"生成时间: {report['generated_at']}")
    lines.append(f"监控竞品: {report['summary']['total_rivals']} | "
                 f"高威胁: {report['summary']['high_threat']} | "
                 f"情报条目: {report['summary']['intel_items']}")
    lines.append("═" * 60)

    for product in report["matrix"]:
        lines.append(f"\n💊 {product['mhm_product']}")
        lines.append(f"   规格: {', '.join(product['mhm_specs'])}")
        lines.append("-" * 40)

        for rival in product["rivals"]:
            icon = "🔴" if rival["threat_level"] == "high" else (
                "🟡" if rival["threat_level"] == "medium" else "🟢")
            mfrs = ", ".join(rival["manufacturers"]) if rival["manufacturers"] else "—"
            lines.append(f"  {icon} {rival['name']} ({mfrs})")
            lines.append(f"     规格: {rival['specs']}")
            lines.append(f"     监控: {' | '.join(rival['watch_dimensions'])}")

        # Show intelligence if available
        pk = product["product_key"]
        if pk in report.get("intelligence", {}):
            lines.append(f"\n  📡 最新情报 ({len(report['intelligence'][pk])}条):")
            for item in report["intelligence"][pk][:3]:
                lines.append(f"     📌 {item.get('title', 'N/A')[:60]}")

    lines.append("\n" + "═" * 60)
    return "\n".join(lines)


def generate_html(report):
    """生成竞品情报HTML报告"""
    summary = report["summary"]

    product_sections = ""
    for product in report["matrix"]:
        rival_rows = ""
        for rival in product["rivals"]:
            mfrs = ", ".join(rival["manufacturers"]) if rival["manufacturers"] else "—"
            watches = "<br>".join(f"📎 {w}" for w in rival["watch_dimensions"])
            rival_rows += f'''<tr>
                <td style="padding:6px 8px;color:{rival['threat_color']};font-weight:bold">
                    {'🔴' if rival['threat_level']=='high' else '🟡' if rival['threat_level']=='medium' else '🟢'}
                    {rival['threat_level'].upper()}
                </td>
                <td style="padding:6px 8px">{rival['name']}</td>
                <td style="padding:6px 8px;font-size:11px;color:{TEXT_LIGHT}">{mfrs}</td>
                <td style="padding:6px 8px;font-size:11px">{rival['specs']}</td>
                <td style="padding:6px 8px;font-size:10px;color:{TEXT_LIGHT}">{watches}</td>
            </tr>'''

        product_sections += f'''
        <h3 style="color:{ACCENT_CYAN};margin:18px 0 6px">💊 {product['mhm_product']}</h3>
        <p style="font-size:11px;color:{TEXT_LIGHT};margin:0 0 8px">规格: {', '.join(product['mhm_specs'])}</p>
        <table style="width:100%;border-collapse:collapse;background:{BG_CARD};border-radius:8px">
            <thead><tr style="border-bottom:2px solid {TEXT_LIGHT}">
                <th style="padding:8px;text-align:left;font-size:11px">威胁</th>
                <th style="padding:8px;text-align:left;font-size:11px">竞品</th>
                <th style="padding:8px;text-align:left;font-size:11px">厂商</th>
                <th style="padding:8px;text-align:left;font-size:11px">规格</th>
                <th style="padding:8px;text-align:left;font-size:11px">监控维度</th>
            </tr></thead>
            <tbody>{rival_rows}</tbody>
        </table>'''

    html = f'''<div style="font-family:'Segoe UI',Arial,sans-serif;max-width:800px;margin:0 auto;color:{TEXT_WHITE}">
    <h2 style="color:{MHM_GREEN};margin:0 0 8px">🎯 竞品情报矩阵</h2>
    <p style="color:{TEXT_LIGHT};font-size:12px;margin:0 0 12px">
        {report['generated_at']} | 监控 {summary['total_rivals']} 竞品 | 高威胁 {summary['high_threat']}
    </p>
    <div style="display:flex;gap:12px;margin-bottom:15px">
        <div style="background:{BG_CARD};border-radius:8px;padding:12px;flex:1;text-align:center">
            <div style="font-size:24px;font-weight:bold;color:{MHM_GREEN}">{summary['total_rivals']}</div>
            <div style="font-size:11px;color:{TEXT_LIGHT}">竞品总数</div>
        </div>
        <div style="background:{BG_CARD};border-radius:8px;padding:12px;flex:1;text-align:center">
            <div style="font-size:24px;font-weight:bold;color:{WARN_RED}">{summary['high_threat']}</div>
            <div style="font-size:11px;color:{TEXT_LIGHT}">高威胁</div>
        </div>
        <div style="background:{BG_CARD};border-radius:8px;padding:12px;flex:1;text-align:center">
            <div style="font-size:24px;font-weight:bold;color:{ACCENT_CYAN}">{summary['intel_items']}</div>
            <div style="font-size:11px;color:{TEXT_LIGHT}">情报条目</div>
        </div>
    </div>
    {product_sections}
</div>'''
    return html


def save_report(report, fmt="json"):
    """保存竞品报告"""
    if fmt == "json":
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        print(f"✅ JSON输出: {OUTPUT_FILE}")
    elif fmt == "html":
        html = generate_html(report)
        out = DATA / "reports" / f"competitor_intel_{datetime.now().strftime('%Y%m%d')}.html"
        out.parent.mkdir(exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(f'<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
                    f'<body style="background:{BG_DARK};padding:20px">{html}</body></html>')
        print(f"✅ HTML报告: {out}")


def main():
    args = sys.argv[1:]
    config = load_config()

    product_filter = None
    if "--product" in args:
        idx = args.index("--product")
        if idx + 1 < len(args):
            product_filter = args[idx + 1]

    matrix = get_competitor_matrix(config, product_filter)
    report = build_competitor_report(matrix)

    if "--json" in args:
        save_report(report, "json")
    elif "--html" in args:
        save_report(report, "html")
    else:
        print(print_console(report))


if __name__ == "__main__":
    main()

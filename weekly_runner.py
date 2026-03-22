"""
政务准入 Dashboard 周对比 + 邮件推送
每周五运行：对比本周vs上周快照 → 生成变化摘要 → 输出HTML报告
注意: 邮件发送由 Agent 通过 Gmail MCP 执行，此脚本只生成报告内容
"""
import json, glob, os
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
SNAP_DIR = DATA / "snapshots"
REPORT_DIR = DATA / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ── Theme colors (match dashboard) ──
MHM_GREEN = "#00a651"
WARN_YELLOW = "#f0ad4e"
WARN_RED = "#d9534f"
BG_DARK = "#002b36"
BG_CARD = "#073642"
TEXT_WHITE = "#fdf6e3"
TEXT_LIGHT = "#93a1a1"

def load_snapshot(path):
    with open(path, "r", encoding="utf-8") as f:
        return {p["province"]: p for p in json.load(f)}

def compare_snapshots(curr_map, prev_map):
    changes = {"new_completions": [], "new_alerts": [], "color_changes": [],
               "health_changes": [], "deadline_resolved": [], "deadline_new": []}
    products = ["T20", "T40", "T60", "金滴", "威利坦"]

    for prov, curr in curr_map.items():
        prev = prev_map.get(prov, {})
        # 1. Switch completion changes
        for pk in products:
            c_prod = curr.get("products", {}).get(pk, {})
            p_prod = prev.get("products", {}).get(pk, {})
            if c_prod.get("done") and not p_prod.get("done"):
                changes["new_completions"].append(f"{prov} {pk} 切换完成")
        # 2. Color label changes
        c_color = curr.get("金针", {}).get("color_label")
        p_color = prev.get("金针", {}).get("color_label")
        if c_color != p_color:
            if c_color == "red" and p_color == "yellow":
                changes["color_changes"].append(f"🔴 {prov} 金针 黄标→红标 (升级)")
            elif c_color and not p_color:
                emoji = "🔴" if c_color == "red" else "🟡"
                changes["color_changes"].append(f"{emoji} {prov} 金针 新增{c_color}标")
            elif not c_color and p_color:
                changes["color_changes"].append(f"🟢 {prov} 金针 {p_color}标已解除")
        # 3. New alerts
        c_alerts = {a.get("desc") for a in curr.get("alerts", [])}
        p_alerts = {a.get("desc") for a in prev.get("alerts", [])}
        for new_a in c_alerts - p_alerts:
            changes["new_alerts"].append(f"{prov}: {new_a}")
        # 4. Health index changes (>5 pts)
        c_hi = curr.get("health_index", 0)
        p_hi = prev.get("health_index", 0)
        if abs(c_hi - p_hi) >= 5:
            arrow = "📈" if c_hi > p_hi else "📉"
            changes["health_changes"].append(f"{arrow} {prov} {p_hi}→{c_hi}")

    return changes

def get_urgent_actions(curr_map, today_str="2026-03-20"):
    today = datetime.strptime(today_str, "%Y-%m-%d")
    actions = []
    for prov, p in curr_map.items():
        for d in p.get("deadlines", []):
            try:
                dt = datetime.strptime(d["date"], "%Y-%m-%d")
                days = (dt - today).days
            except:
                continue
            actions.append({"province": prov, "desc": d["desc"], "date": d["date"],
                           "days_left": days, "urgency": d.get("urgency", "")})
        for a in p.get("alerts", []):
            if a.get("type") in ["price_risk", "color_upgrade", "new_color_label"]:
                actions.append({"province": prov, "desc": a["desc"], "date": a.get("date", ""),
                               "days_left": 0, "urgency": "critical"})
    actions.sort(key=lambda x: x["days_left"])
    return actions[:10]

def generate_html_report(changes, actions, curr_map, today_str):
    total = len(curr_map)
    avg_hi = sum(p.get("health_index", 0) for p in curr_map.values()) / total if total else 0
    red_count = sum(1 for p in curr_map.values() if p.get("金针", {}).get("color_label") == "red")
    yellow_count = sum(1 for p in curr_map.values() if p.get("金针", {}).get("color_label") == "yellow")

    # Changes summary
    change_items = []
    for c in changes.get("new_completions", []):
        change_items.append(f'<li style="color:{MHM_GREEN}">✅ {c}</li>')
    for c in changes.get("color_changes", []):
        change_items.append(f'<li style="color:{WARN_YELLOW}">{c}</li>')
    for c in changes.get("new_alerts", []):
        change_items.append(f'<li style="color:{WARN_RED}">🚨 {c}</li>')
    for c in changes.get("health_changes", []):
        change_items.append(f'<li>{c}</li>')
    changes_html = "\n".join(change_items) if change_items else '<li style="color:#93a1a1">本周无重大变化</li>'

    # Urgent actions
    action_rows = []
    for a in actions:
        if a["days_left"] <= 0:
            color = WARN_RED
            label = "🔴 极紧急"
        elif a["days_left"] <= 7:
            color = WARN_YELLOW
            label = "🟠 本周"
        else:
            color = MHM_GREEN
            label = "🟢 稍后"
        action_rows.append(f'''
        <tr>
            <td style="padding:8px;color:{color};font-weight:bold">{label}</td>
            <td style="padding:8px">{a["province"]}</td>
            <td style="padding:8px">{a["desc"]}</td>
            <td style="padding:8px">{a["date"]}</td>
            <td style="padding:8px;text-align:center">{a["days_left"]}天</td>
        </tr>''')
    actions_html = "\n".join(action_rows)

    html = f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:{BG_DARK};color:{TEXT_WHITE};padding:20px;margin:0">
<div style="max-width:800px;margin:0 auto">
    <h1 style="text-align:center;color:{MHM_GREEN}">🗺️ 政务准入周报</h1>
    <p style="text-align:center;color:{TEXT_LIGHT}">{today_str} | 覆盖 {total} 省</p>

    <!-- KPI Cards -->
    <div style="display:flex;gap:12px;margin:20px 0">
        <div style="flex:1;background:{BG_CARD};border-radius:10px;padding:15px;border-left:4px solid {MHM_GREEN}">
            <div style="color:{TEXT_LIGHT};font-size:12px">平均健康指数</div>
            <div style="font-size:24px;font-weight:bold">{avg_hi:.1f}</div>
        </div>
        <div style="flex:1;background:{BG_CARD};border-radius:10px;padding:15px;border-left:4px solid {WARN_YELLOW}">
            <div style="color:{TEXT_LIGHT};font-size:12px">黄标省份</div>
            <div style="font-size:24px;font-weight:bold">{yellow_count} 省</div>
        </div>
        <div style="flex:1;background:{BG_CARD};border-radius:10px;padding:15px;border-left:4px solid {WARN_RED}">
            <div style="color:{TEXT_LIGHT};font-size:12px">红标省份</div>
            <div style="font-size:24px;font-weight:bold">{red_count} 省</div>
        </div>
    </div>

    <!-- Changes this week -->
    <div style="background:{BG_CARD};border-radius:10px;padding:20px;margin:20px 0">
        <h2 style="color:{MHM_GREEN};margin-top:0">📋 本周变化</h2>
        <ul style="list-style:none;padding:0;margin:0">
            {changes_html}
        </ul>
    </div>

    <!-- Urgent Actions -->
    <div style="background:{BG_CARD};border-radius:10px;padding:20px;margin:20px 0">
        <h2 style="color:{WARN_RED};margin-top:0">⚡ 紧急行动 TOP {len(actions)}</h2>
        <table style="width:100%;border-collapse:collapse;color:{TEXT_WHITE}">
            <thead>
                <tr style="border-bottom:2px solid {TEXT_LIGHT}">
                    <th style="padding:8px;text-align:left">紧急度</th>
                    <th style="padding:8px;text-align:left">省份</th>
                    <th style="padding:8px;text-align:left">事项</th>
                    <th style="padding:8px;text-align:left">截止</th>
                    <th style="padding:8px;text-align:center">剩余</th>
                </tr>
            </thead>
            <tbody>
                {actions_html}
            </tbody>
        </table>
    </div>

    <p style="text-align:center;color:{TEXT_LIGHT};font-size:12px;margin-top:30px">
        森世海亚策略中心 | 政务准入作战指挥台 | 自动生成
    </p>
</div>
</body>
</html>'''
    return html

def main():
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Find latest two snapshots
    snaps = sorted(glob.glob(str(SNAP_DIR / "snapshot_*.json")))
    if not snaps:
        print("❌ 没有找到快照文件")
        return

    curr_path = snaps[-1]
    curr_map = load_snapshot(curr_path)
    print(f"📊 当前快照: {os.path.basename(curr_path)} ({len(curr_map)} 省)")

    if len(snaps) >= 2:
        prev_path = snaps[-2]
        prev_map = load_snapshot(prev_path)
        print(f"📊 上周快照: {os.path.basename(prev_path)} ({len(prev_map)} 省)")
        changes = compare_snapshots(curr_map, prev_map)
    else:
        print("ℹ️ 仅有一份快照，跳过对比")
        changes = {"new_completions": [], "new_alerts": [], "color_changes": [],
                   "health_changes": [], "deadline_resolved": [], "deadline_new": []}

    # Get urgent actions
    actions = get_urgent_actions(curr_map, today_str)
    print(f"\n⚡ 紧急事项: {len(actions)} 项")
    for a in actions[:5]:
        print(f"  {'🔴' if a['days_left']<=0 else '🟠' if a['days_left']<=7 else '🟢'} {a['province']}: {a['desc']} ({a['days_left']}天)")

    # Generate report
    html = generate_html_report(changes, actions, curr_map, today_str)
    report_path = REPORT_DIR / f"weekly_report_{today_str.replace('-','')}.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ 周报已生成: {report_path}")

    # Print changes summary
    total_changes = sum(len(v) for v in changes.values())
    if total_changes > 0:
        print(f"\n📋 本周变化 ({total_changes} 项):")
        for cat, items in changes.items():
            for item in items:
                print(f"  {item}")
    else:
        print("\nℹ️ 本周无重大变化")

    return str(report_path)

if __name__ == "__main__":
    main()

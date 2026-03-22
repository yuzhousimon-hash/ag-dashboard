"""
截止日期智能引擎
从province_master.json中提取所有截止日期
→ 计算T-7/T-3/T-1/T-0/过期 多级倒计时
→ 生成每日简报
→ 过期自动升级为红色预警
用法: python deadline_engine.py  (输出今日简报)
      python deadline_engine.py --html  (输出HTML邮件体)
"""
import json
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
MASTER_FILE = DATA / "province_master.json"

# ── Theme colors ──
MHM_GREEN = "#00a651"
WARN_YELLOW = "#f0ad4e"
WARN_RED = "#d9534f"
ACCENT_CYAN = "#2aa198"
BG_DARK = "#002b36"
BG_CARD = "#073642"
TEXT_WHITE = "#fdf6e3"
TEXT_LIGHT = "#93a1a1"

# ── Urgency tiers ──
TIER_OVERDUE = {"label": "🚨 已过期", "color": WARN_RED, "priority": 0}
TIER_TODAY   = {"label": "🔴 今天到期", "color": WARN_RED, "priority": 1}
TIER_T1      = {"label": "🔴 明天到期", "color": WARN_RED, "priority": 2}
TIER_T3      = {"label": "🟠 3天内", "color": WARN_YELLOW, "priority": 3}
TIER_T7      = {"label": "🟡 本周内", "color": WARN_YELLOW, "priority": 4}
TIER_LATER   = {"label": "🟢 稍后", "color": MHM_GREEN, "priority": 5}


def classify_deadline(days_left):
    if days_left < 0:
        return TIER_OVERDUE
    elif days_left == 0:
        return TIER_TODAY
    elif days_left == 1:
        return TIER_T1
    elif days_left <= 3:
        return TIER_T3
    elif days_left <= 7:
        return TIER_T7
    else:
        return TIER_LATER


def extract_deadlines(today_str=None):
    """提取所有截止日期并分级"""
    if today_str is None:
        today_str = datetime.now().strftime("%Y-%m-%d")
    today = datetime.strptime(today_str, "%Y-%m-%d")

    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        master = json.load(f)

    items = []
    for p in master:
        prov = p["province"]
        # From deadlines
        for d in p.get("deadlines", []):
            try:
                dt = datetime.strptime(d["date"], "%Y-%m-%d")
                days_left = (dt - today).days
            except:
                continue
            tier = classify_deadline(days_left)
            items.append({
                "province": prov,
                "desc": d["desc"],
                "date": d["date"],
                "days_left": days_left,
                "tier": tier,
                "source": "deadline",
            })
        # From alerts (critical ones have implicit urgency)
        for a in p.get("alerts", []):
            if a.get("type") in ["price_risk", "color_upgrade", "new_color_label"]:
                try:
                    dt = datetime.strptime(a["date"], "%Y-%m-%d")
                    days_left = (dt - today).days
                except:
                    days_left = 0
                tier = classify_deadline(min(days_left, 0))  # Alerts are always urgent
                items.append({
                    "province": prov,
                    "desc": a["desc"],
                    "date": a.get("date", ""),
                    "days_left": days_left,
                    "tier": tier,
                    "source": "alert",
                })

    # Sort by priority (overdue first), then days_left
    items.sort(key=lambda x: (x["tier"]["priority"], x["days_left"]))
    return items


def generate_daily_brief(items, today_str):
    """生成控制台简报"""
    overdue = [i for i in items if i["tier"]["priority"] == 0]
    today_items = [i for i in items if i["tier"]["priority"] == 1]
    tomorrow = [i for i in items if i["tier"]["priority"] == 2]
    three_day = [i for i in items if i["tier"]["priority"] == 3]
    week = [i for i in items if i["tier"]["priority"] == 4]

    lines = [f"\n📅 政务准入每日简报 | {today_str}", "=" * 50]

    if overdue:
        lines.append(f"\n🚨 已过期 ({len(overdue)}项) — 需立即处理！")
        for i in overdue:
            lines.append(f"  ⚠️ {i['province']}: {i['desc']} (过期{abs(i['days_left'])}天)")

    if today_items:
        lines.append(f"\n🔴 今天到期 ({len(today_items)}项)")
        for i in today_items:
            lines.append(f"  ❗ {i['province']}: {i['desc']}")

    if tomorrow:
        lines.append(f"\n🔴 明天到期 ({len(tomorrow)}项)")
        for i in tomorrow:
            lines.append(f"  → {i['province']}: {i['desc']}")

    if three_day:
        lines.append(f"\n🟠 3天内 ({len(three_day)}项)")
        for i in three_day:
            lines.append(f"  → {i['province']}: {i['desc']} ({i['days_left']}天)")

    if week:
        lines.append(f"\n🟡 本周内 ({len(week)}项)")
        for i in week:
            lines.append(f"  → {i['province']}: {i['desc']} ({i['days_left']}天)")

    total_urgent = len(overdue) + len(today_items) + len(tomorrow)
    lines.append(f"\n{'='*50}")
    lines.append(f"紧急事项合计: {total_urgent} | 本周: {len(three_day)+len(week)} | 总计: {len(items)}")

    return "\n".join(lines)


def generate_html_brief(items, today_str):
    """生成HTML邮件简报"""
    overdue = [i for i in items if i["tier"]["priority"] <= 1]
    this_week = [i for i in items if 2 <= i["tier"]["priority"] <= 4]

    rows = []
    for i in items:
        if i["tier"]["priority"] >= 5:
            continue  # Skip "later" items in email
        t = i["tier"]
        days_text = f"过期{abs(i['days_left'])}天" if i["days_left"] < 0 else (
            "今天" if i["days_left"] == 0 else f"{i['days_left']}天")
        rows.append(f'''<tr>
            <td style="padding:6px 10px;color:{t['color']};font-weight:bold;font-size:13px">{t['label']}</td>
            <td style="padding:6px 10px;font-size:13px">{i['province']}</td>
            <td style="padding:6px 10px;font-size:13px">{i['desc']}</td>
            <td style="padding:6px 10px;text-align:center;font-size:13px">{days_text}</td>
        </tr>''')

    table_html = "\n".join(rows)

    html = f'''<div style="font-family:'Segoe UI',Arial,sans-serif;max-width:600px;margin:0 auto">
    <h2 style="color:{MHM_GREEN};margin:0 0 5px 0">📅 今日截止事项</h2>
    <p style="color:{TEXT_LIGHT};margin:0 0 15px 0;font-size:12px">{today_str} | 🚨 {len(overdue)}项紧急 | 📋 {len(this_week)}项本周</p>
    <table style="width:100%;border-collapse:collapse;background:{BG_CARD};border-radius:8px;color:{TEXT_WHITE}">
        <thead>
            <tr style="border-bottom:2px solid {TEXT_LIGHT}">
                <th style="padding:8px 10px;text-align:left;font-size:12px">级别</th>
                <th style="padding:8px 10px;text-align:left;font-size:12px">省份</th>
                <th style="padding:8px 10px;text-align:left;font-size:12px">事项</th>
                <th style="padding:8px 10px;text-align:center;font-size:12px">倒计时</th>
            </tr>
        </thead>
        <tbody>{table_html}</tbody>
    </table>
</div>'''
    return html


def main():
    import sys
    today_str = datetime.now().strftime("%Y-%m-%d")
    items = extract_deadlines(today_str)

    if "--html" in sys.argv:
        html = generate_html_brief(items, today_str)
        out = DATA / "reports" / f"daily_brief_{today_str.replace('-','')}.html"
        out.parent.mkdir(exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(f'''<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="background:{BG_DARK};padding:20px">{html}</body></html>''')
        print(f"✅ HTML简报: {out}")
    else:
        print(generate_daily_brief(items, today_str))


if __name__ == "__main__":
    main()

"""
电商价格监控引擎 — 追踪MHM产品及竞品在电商平台的价格/销量
覆盖：阿里健康 / 京东健康 / 拼多多 / 美团买药

用法:
  python ecommerce_monitor.py           # 控制台输出
  python ecommerce_monitor.py --json    # 输出JSON
  python ecommerce_monitor.py --target ginaton  # 单产品追踪
"""
import json, sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
CONFIG_FILE = DATA / "scan_config.json"
OUTPUT_FILE = DATA / "ecommerce_monitor.json"

# ── Theme ──
MHM_GREEN = "#00a651"
WARN_YELLOW = "#f0ad4e"
WARN_RED = "#d9534f"
ACCENT_CYAN = "#2aa198"
BG_DARK = "#002b36"
BG_CARD = "#073642"
TEXT_WHITE = "#fdf6e3"
TEXT_LIGHT = "#93a1a1"


# ═══════════════════════════════════════════════════════
# 电商监控 SKU 定义
# ═══════════════════════════════════════════════════════
ECOMMERCE_SKUS = {
    "mhm_products": [
        {
            "name": "金纳多 银杏叶提取物片 T20",
            "sku_key": "ginaton_t20",
            "search_terms": ["金纳多 银杏叶提取物片 20片", "金纳多 EGb761"],
            "platforms": ["阿里健康", "京东健康", "拼多多"],
            "reference_price": 36.5,
            "category": "处方药/OTC",
        },
        {
            "name": "金纳多 银杏叶提取物片 T40",
            "sku_key": "ginaton_t40",
            "search_terms": ["金纳多 银杏叶提取物片 40片"],
            "platforms": ["阿里健康", "京东健康"],
            "reference_price": 73.24,
            "category": "处方药",
        },
        {
            "name": "威利坦 七叶皂苷钠片",
            "sku_key": "venoforton",
            "search_terms": ["威利坦 七叶皂苷钠", "Venoforton"],
            "platforms": ["阿里健康", "京东健康"],
            "reference_price": None,
            "category": "处方药",
        },
        {
            "name": "路优泰 贯叶连翘提取物片",
            "sku_key": "laif",
            "search_terms": ["路优泰 贯叶连翘", "Laif 900"],
            "platforms": ["阿里健康", "京东健康", "拼多多"],
            "reference_price": None,
            "category": "处方药",
        },
    ],
    "competitor_products": [
        {
            "name": "天保宁 银杏叶片",
            "sku_key": "tianbaoning",
            "search_terms": ["天保宁 银杏叶片", "康恩贝 银杏叶"],
            "platforms": ["阿里健康", "京东健康", "拼多多"],
            "competitor_of": "ginaton",
            "category": "OTC",
        },
        {
            "name": "舒血宁注射液",
            "sku_key": "shuxuening",
            "search_terms": ["舒血宁注射液"],
            "platforms": ["阿里健康", "京东健康"],
            "competitor_of": "ginaton",
            "category": "处方药",
        },
        {
            "name": "迈之灵 马栗种子提取物片",
            "sku_key": "mazhiling",
            "search_terms": ["迈之灵 马栗种子", "马栗种子提取物片"],
            "platforms": ["阿里健康", "京东健康"],
            "competitor_of": "venoforton",
            "category": "处方药",
        },
        {
            "name": "地奥司明片",
            "sku_key": "diosmin",
            "search_terms": ["地奥司明片", "Daflon"],
            "platforms": ["阿里健康", "京东健康", "拼多多"],
            "competitor_of": "venoforton",
            "category": "处方药",
        },
    ],
}

# ═══════════════════════════════════════════════════════
# 搜索查询生成器
# ═══════════════════════════════════════════════════════

def get_ecommerce_search_plan(target_filter=None):
    """
    生成电商搜索查询列表
    供Agent使用 search_web / browser_subagent 执行
    """
    queries = []
    all_skus = (
        ECOMMERCE_SKUS["mhm_products"]
        + ECOMMERCE_SKUS["competitor_products"]
    )

    for sku in all_skus:
        if target_filter:
            if target_filter not in sku["sku_key"] and target_filter not in sku.get("competitor_of",""):
                continue

        for platform in sku["platforms"]:
            for term in sku["search_terms"][:1]:  # Primary search term only
                queries.append({
                    "sku_key": sku["sku_key"],
                    "product_name": sku["name"],
                    "platform": platform,
                    "search_term": f"{term} {platform}",
                    "full_query": f"site:{_platform_domain(platform)} {term} 价格",
                    "category": sku["category"],
                    "is_mhm": "competitor_of" not in sku,
                    "competitor_of": sku.get("competitor_of"),
                    "reference_price": sku.get("reference_price"),
                })

    return {
        "queries": queries,
        "total_queries": len(queries),
        "platforms": list(set(q["platform"] for q in queries)),
        "mhm_count": sum(1 for q in queries if q["is_mhm"]),
        "competitor_count": sum(1 for q in queries if not q["is_mhm"]),
    }


def _platform_domain(platform):
    """平台名→域名映射"""
    mapping = {
        "阿里健康": "alihealth.cn OR taobao.com",
        "京东健康": "jd.com",
        "拼多多": "pinduoduo.com",
        "美团买药": "meituan.com",
    }
    return mapping.get(platform, "")


def process_ecommerce_data(raw_data, today_str=None):
    """
    处理Agent收集的电商数据
    raw_data: list of dicts, each with:
      - sku_key, platform, price, sales_volume, url, title
      - is_mhm, competitor_of (from search plan)
    """
    today = datetime.strptime(today_str, "%Y-%m-%d") if today_str else datetime.now()

    # Group by product
    by_product = {}
    for item in raw_data:
        key = item.get("sku_key", "unknown")
        if key not in by_product:
            by_product[key] = {
                "product_name": item.get("product_name", key),
                "is_mhm": item.get("is_mhm", False),
                "competitor_of": item.get("competitor_of"),
                "platforms": {},
            }
        platform = item.get("platform", "unknown")
        by_product[key]["platforms"][platform] = {
            "price": item.get("price"),
            "sales_volume": item.get("sales_volume"),
            "url": item.get("url"),
            "title": item.get("title"),
            "scraped_at": today.strftime("%Y-%m-%d"),
        }

    # Detect price anomalies
    anomalies = []
    for sku in ECOMMERCE_SKUS["mhm_products"]:
        ref = sku.get("reference_price")
        if ref and sku["sku_key"] in by_product:
            for plat, plat_data in by_product[sku["sku_key"]]["platforms"].items():
                price = plat_data.get("price")
                if price and price < ref * 0.8:
                    anomalies.append({
                        "type": "low_price",
                        "product": sku["name"],
                        "platform": plat,
                        "price": price,
                        "reference": ref,
                        "deviation": f"{((price/ref)-1)*100:.1f}%",
                        "severity": "high",
                    })

    return {
        "generated_at": today.strftime("%Y-%m-%d %H:%M"),
        "products": by_product,
        "anomalies": anomalies,
        "summary": {
            "total_skus": len(by_product),
            "mhm_skus": sum(1 for v in by_product.values() if v["is_mhm"]),
            "competitor_skus": sum(1 for v in by_product.values() if not v["is_mhm"]),
            "anomalies": len(anomalies),
        },
    }


def print_console_plan(plan):
    """打印搜索计划"""
    lines = ["\n" + "═" * 60]
    lines.append("🛒 电商价格监控引擎 | E-Commerce Monitor v1.0")
    lines.append(f"查询总数: {plan['total_queries']} | "
                 f"MHM产品: {plan['mhm_count']} | "
                 f"竞品: {plan['competitor_count']}")
    lines.append(f"覆盖平台: {', '.join(plan['platforms'])}")
    lines.append("═" * 60)

    current_sku = ""
    for q in plan["queries"]:
        if q["sku_key"] != current_sku:
            current_sku = q["sku_key"]
            icon = "💊" if q["is_mhm"] else "🎯"
            lines.append(f"\n{icon} {q['product_name']}")

        ref = f" (参考价: ¥{q['reference_price']})" if q.get("reference_price") else ""
        lines.append(f"  📦 {q['platform']}: {q['search_term']}{ref}")

    lines.append(f"\n💡 提示: Agent将使用 search_web 执行查询并收集价格信息。")
    lines.append("═" * 60)
    return "\n".join(lines)


def save_report(report, fmt="json"):
    out = OUTPUT_FILE
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"✅ JSON输出: {out}")


def main():
    args = sys.argv[1:]

    target_filter = None
    if "--target" in args:
        idx = args.index("--target")
        if idx + 1 < len(args):
            target_filter = args[idx + 1]

    plan = get_ecommerce_search_plan(target_filter)

    if "--json" in args:
        # Output plan as JSON for Agent consumption
        out = DATA / "ecommerce_plan.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2, default=str)
        print(f"✅ 搜索计划输出: {out}")
    else:
        print(print_console_plan(plan))


if __name__ == "__main__":
    main()

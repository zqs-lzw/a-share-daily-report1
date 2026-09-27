# analyze.py
# 将原始行情数据加工为报告所需的统计结果。

import pandas as pd
from config import MAINLINE_KEYWORDS, LIMIT_UP_THRESHOLD, LIMIT_UP_THRESHOLD_20
import logging

logger = logging.getLogger(__name__)


def classify_mainline(stock_name, sector_name=""):
    """根据股票名称和所属板块，归入投资主线"""
    text = f"{stock_name} {sector_name}"
    for mainline, keywords in MAINLINE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return mainline
    return "其他"


def analyze_market(raw):
    """主分析函数"""
    spot = raw["spot"].copy()
    zt_pool = raw["zt_pool"].copy()

    # ---- 1. 涨跌家数统计 ----
    # 兼容不同版本的列名
    change_col = "涨跌幅"
    if change_col not in spot.columns:
        for c in ["涨跌幅", "changepercent", "涨跌幅(%)"]:
            if c in spot.columns:
                change_col = c
                break

    up_count = int((spot[change_col] > 0).sum())
    down_count = int((spot[change_col] < 0).sum())
    flat_count = int((spot[change_col] == 0).sum())

    # ---- 2. 成交额统计 ----
    amount_col = "成交额"
    if amount_col not in spot.columns:
        for c in ["成交额", "amount", "成交额(元)"]:
            if c in spot.columns:
                amount_col = c
                break

    total_amount = spot[amount_col].sum() if amount_col in spot.columns else 0
    total_amount_yi = total_amount / 1e8  # 转换为亿

    # ---- 3. 涨停/跌停统计 ----
    zt_count = len(zt_pool)
    dt_count = len(raw["dt_pool"])
    zb_count = len(raw["zb_pool"])

    # 封板率
    total_attempts = zt_count + zb_count
    seal_rate = (zt_count / total_attempts * 100) if total_attempts > 0 else 0

    # ---- 4. 连板梯队 ----
    lianban_tiers = []
    if not zt_pool.empty and "连板数" in zt_pool.columns:
        zt_pool["连板数"] = pd.to_numeric(zt_pool["连板数"], errors="coerce").fillna(1)
        # 按连板数分组
        for tier in sorted(zt_pool["连板数"].unique(), reverse=True):
            if tier < 2:
                continue
            tier_stocks = zt_pool[zt_pool["连板数"] == tier]
            for _, s in tier_stocks.iterrows():
                lianban_tiers.append({
                    "tier": int(tier),
                    "name": s.get("名称", ""),
                    "code": s.get("代码", ""),
                    "change": float(s.get("涨跌幅", 0)),
                    "reason": s.get("涨停原因", s.get("所属行业", "")),
                })

    max_tier = max([t["tier"] for t in lianban_tiers], default=1)

    # ---- 5. 涨停主题分布 ----
    zt_themes = {}
    if not zt_pool.empty:
        for _, s in zt_pool.iterrows():
            name = s.get("名称", "")
            industry = s.get("所属行业", "")
            mainline = classify_mainline(name, industry)
            zt_themes[mainline] = zt_themes.get(mainline, 0) + 1

    # 按数量排序
    zt_themes_sorted = sorted(zt_themes.items(), key=lambda x: x[1], reverse=True)
    # 计算强度百分比
    max_theme_count = zt_themes_sorted[0][1] if zt_themes_sorted else 1
    zt_themes_with_strength = [
        {"name": k, "count": v, "strength": int(v / max_theme_count * 100)}
        for k, v in zt_themes_sorted
    ]

    # ---- 6. 板块涨跌排名 ----
    top_sectors = []
    bottom_sectors = []
    if not raw["sector_board"].empty:
        sb = raw["sector_board"].copy()
        # 尝试找涨跌幅列
        for col in ["涨跌幅", "涨跌幅(%)", "change_pct"]:
            if col in sb.columns:
                sb[col] = pd.to_numeric(sb[col], errors="coerce")
                sb_sorted = sb.sort_values(col, ascending=False)
                for _, r in sb_sorted.head(5).iterrows():
                    top_sectors.append({
                        "name": r.get("板块名称", r.get("名称", "")),
                        "change": float(r[col]),
                    })
                for _, r in sb_sorted.tail(5).iterrows():
                    bottom_sectors.append({
                        "name": r.get("板块名称", r.get("名称", "")),
                        "change": float(r[col]),
                    })
                break

    # ---- 7. 20cm涨停数量 ----
    zt_20cm = 0
    if not zt_pool.empty and "涨跌幅" in zt_pool.columns:
        zt_20cm = int((pd.to_numeric(zt_pool["涨跌幅"], errors="coerce") >= LIMIT_UP_THRESHOLD_20).sum())

    # ---- 8. 涨停股按主线分组（用于最强主线分析） ----
    mainline_stocks = {}
    if not zt_pool.empty:
        for _, s in zt_pool.iterrows():
            name = s.get("名称", "")
            industry = s.get("所属行业", "")
            mainline = classify_mainline(name, industry)
            if mainline not in mainline_stocks:
                mainline_stocks[mainline] = []
            mainline_stocks[mainline].append({
                "name": name,
                "code": s.get("代码", ""),
                "change": float(s.get("涨跌幅", 0)),
                "industry": industry,
                "lianban": int(s.get("连板数", 1)) if pd.notna(s.get("连板数")) else 1,
                "reason": s.get("涨停原因", ""),
            })

    # 按主线内涨停数排序
    mainline_ranked = sorted(mainline_stocks.items(), key=lambda x: len(x[1]), reverse=True)

    return {
        **raw,
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
        "total_amount_yi": total_amount_yi,
        "zt_count": zt_count,
        "dt_count": dt_count,
        "zb_count": zb_count,
        "seal_rate": seal_rate,
        "lianban_tiers": lianban_tiers,
        "max_tier": max_tier,
        "zt_themes": zt_themes_with_strength,
        "top_sectors": top_sectors,
        "bottom_sectors": bottom_sectors,
        "zt_20cm": zt_20cm,
        "mainline_ranked": mainline_ranked,
    }
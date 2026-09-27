# generate.py
# 主入口：抓取数据 → 分析 → 渲染模板 → 输出HTML

import os
import sys
import logging
from datetime import datetime

from fetch_data import fetch_all, get_last_trading_day
from analyze import analyze_market
from config import OUTPUT_DIR

from jinja2 import Environment, FileSystemLoader

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ---- 主线催化剂文案（可根据实际调整） ----
MAINLINE_CATALYSTS = {
    "AI硬件/CPO/光通信": "AI算力扩张+光模块需求爆发",
    "PCB/高端电路板": "AI算力载板需求+铜价上涨",
    "有色金属": "地缘风险+金属价格上涨",
    "MLCC/被动元件": "AI服务器被动元件倍增",
    "人形机器人/具身智能": "具身智能量产预期",
    "半导体": "国产替代+需求回暖",
}


def build_subtitle(analyzed):
    """自动生成副标题"""
    parts = []
    # 指数表现
    idx = analyzed.get("index", {})
    if idx:
        best = max(idx.values(), key=lambda x: abs(x["change"]))
        parts.append(f"{best.get('name', '')}涨{bests_change(best['change'])}")
    # 涨停数
    parts.append(f"{analyzed['zt_count']}股涨停")
    # 主线
    if analyzed["mainline_ranked"]:
        parts.append(f"{analyzed['mainline_ranked'][0][0]}领涨")
    return "，".join(parts)


def bests_change(v):
    return f"{v:+.1f}%" if v >= 0 else f"{v:.1f}%"


def build_core_judgment(analyzed):
    """自动生成核心判断文案"""
    zt = analyzed["zt_count"]
    up = analyzed["up_count"]
    total_amt = analyzed["total_amount_yi"]

    lines = []
    lines.append(f"今日两市涨停<strong class='hl-red'>{zt}只</strong>，上涨家数<strong class='hl-red'>{up}</strong>只，"
                 f"两市成交<strong class='hl-blue'>{total_amt:.0f}亿</strong>。")

    if analyzed["mainline_ranked"]:
        top = analyzed["mainline_ranked"][0]
        lines.append(f"最强主线为<strong class='hl-gold'>{top[0]}</strong>，该方向涨停<strong>{len(top[1])}</strong>只，"
                     f"为今日资金主攻方向。")

    if zt > 100:
        lines.append("涨停家数超过100只，市场情绪处于亢奋状态。")
    elif zt > 50:
        lines.append("涨停家数中等偏上，市场情绪偏暖。")
    else:
        lines.append("涨停家数偏少，市场情绪偏谨慎。")

    return " ".join(lines)


def build_key_observation(analyzed):
    """自动生成关键观察文案"""
    lines = []
    themes = analyzed["zt_themes"]
    if themes:
        lines.append(f"<strong class='hl-gold'>涨停主题高度集中于{themes[0]['name']}</strong>，"
                     f"该方向贡献了{themes[0]['count']}只涨停。")

    if analyzed["max_tier"] >= 3:
        lines.append(f"<strong class='hl-red'>高位连板风险：</strong>最高{analyzed['max_tier']}板，"
                     "高位股分歧概率加大。")
    else:
        lines.append(f"<strong class='hl-blue'>连板高度有限：</strong>最高仅{analyzed['max_tier']}板，"
                     "短线接力需谨慎。")

    lines.append(f"<strong class='hl-orange'>炸板率：</strong>炸板{analyzed['zb_count']}只，"
                 f"封板率{analyzed['seal_rate']:.0f}%。")

    return "<br><br>".join(lines)


def build_index_interpretation(analyzed):
    """自动生成指数解读"""
    idx = analyzed.get("index", {})
    if not idx:
        return "指数数据暂缺"
    changes = {k: v["change"] for k, v in idx.items()}
    if changes.get("创业板指", 0) > changes.get("上证指数", 0):
        return "成长风格跑赢价值，创业板表现强于主板"
    else:
        return "价值风格占优，大盘蓝筹表现强于成长"


def generate_report():
    """主流程"""
    logger.info("========== 开始生成 A 股复盘报告 ==========")

    # 1. 抓取数据
    try:
        raw = fetch_all()
    except Exception as e:
        logger.error(f"数据抓取失败: {e}")
        sys.exit(1)

    # 2. 分析
    analyzed = analyze_market(raw)

    # 3. 构造模板变量
    report_date = f"{raw['date_cn']}"
    data_date = f"{raw['date'][:4]}-{raw['date'][4:6]}-{raw['date'][6:8]}"

    # 指数列表
    index_list = []
    for name, data in analyzed.get("index", {}).items():
        index_list.append({
            "name": name,
            "value": data["value"],
            "change": data["change"],
        })
    # 按上证-深证-创业板排序
    order = {"上证指数": 0, "深证成指": 1, "创业板指": 2}
    index_list.sort(key=lambda x: order.get(x["name"], 99))

    # 主线催化剂映射
    mainline_catalysts = {
        name: MAINLINE_CATALYSTS.get(name, "多因素催化")
        for name, _ in analyzed["mainline_ranked"]
    }

    # 4. 渲染模板
    env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=False,
    )
    # 注册 min 过滤器
    env.filters["min"] = min

    template = env.get_template("report.html")

    html = template.render(
        report_date=report_date,
        data_date=data_date,
        subtitle_text=build_subtitle(analyzed),
        index_list=index_list,
        up_count=analyzed["up_count"],
        down_count=analyzed["down_count"],
        zt_count=analyzed["zt_count"],
        dt_count=analyzed["dt_count"],
        zb_count=analyzed["zb_count"],
        seal_rate=analyzed["seal_rate"],
        zt_20cm=analyzed["zt_20cm"],
        total_amount_yi=analyzed["total_amount_yi"],
        top_sectors=analyzed["top_sectors"],
        bottom_sectors=analyzed["bottom_sectors"],
        zt_themes=analyzed["zt_themes"],
        lianban_tiers=analyzed["lianban_tiers"],
        max_tier=analyzed["max_tier"],
        mainline_ranked=analyzed["mainline_ranked"],
        mainline_catalysts=mainline_catalysts,
        dt_pool=analyzed.get("dt_pool"),
        core_judgment=build_core_judgment(analyzed),
        key_observation=build_key_observation(analyzed),
        index_interpretation=build_index_interpretation(analyzed),
    )

    # 5. 输出
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_filename = f"report_{raw['date']}.html"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    # 同时输出一个 index.html（方便 GitHub Pages 访问）
    index_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"报告已生成: {output_path}")
    logger.info("========== 报告生成完成 ==========")
    return output_path


if __name__ == "__main__":
    generate_report()
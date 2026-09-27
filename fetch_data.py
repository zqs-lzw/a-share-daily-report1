# fetch_data.py
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_last_trading_day():
    """获取最近一个交易日(考虑周末和节假日)"""
    try:
        trade_cal = ak.tool_trade_date_hist_sina()
        trade_dates = pd.to_datetime(trade_cal["trade_date"]).dt.date
        today = datetime.now().date()
        past_dates = trade_dates[trade_dates <= today]
        if len(past_dates) > 0:
            return past_dates.max().strftime("%Y%m%d")
    except Exception as e:
        logger.warning(f"获取交易日历失败，回退到简单判断: {e}")

    today = datetime.now()
    if today.weekday() == 5:
        return (today - timedelta(days=1)).strftime("%Y%m%d")
    elif today.weekday() == 6:
        return (today - timedelta(days=2)).strftime("%Y%m%d")
    return today.strftime("%Y%m%d")


def fetch_all_spot():
    """获取全A股实时行情(带备用数据源)"""
    logger.info("正在获取全A股实时行情...")
    
    # 方案一：尝试东方财富接口
    for attempt in range(2):
        try:
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                logger.info(f"成功通过东方财富获取 {len(df)} 只股票数据")
                return df
        except Exception as e:
            logger.warning(f"东方财富接口第{attempt+1}次失败: {e}")
            time.sleep(3)

    # 方案二：切换到新浪财经接口
    logger.info("东方财富接口不可用，尝试通过新浪财经获取行情数据...")
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_spot()
            if df is not None and not df.empty:
                logger.info(f"成功通过新浪财经获取 {len(df)} 只股票数据")
                df = df.rename(columns={
                    "code": "代码",
                    "name": "名称",
                    "trade": "最新价",
                    "pricechange": "涨跌额",
                    "changepercent": "涨跌幅",
                    "amount": "成交额"
                })
                if "代码" in df.columns:
                    df["代码"] = df["代码"].astype(str).str.replace(r'^[a-zA-Z]+', '', regex=True)
                return df
        except Exception as e:
            logger.warning(f"新浪接口第{attempt+1}次失败: {e}")
            time.sleep(5)

    raise RuntimeError("获取全A股行情失败，东方财富和新浪接口均不可用")


def fetch_index_data():
    """获取三大指数行情(优先新浪接口，对海外IP友好)"""
    logger.info("正在获取指数数据...")
    index_data = {}
    index_names = {"sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指"}

    try:
        df = ak.stock_zh_index_spot_sina()
        if df is not None and not df.empty:
            for code, name in index_names.items():
                row = df[df["代码"] == code]
                if not row.empty:
                    r = row.iloc[0]
                    index_data[name] = {
                        "code": code,
                        "value": float(r.get("最新价", 0)),
                        "change": float(r.get("涨跌幅", 0)),
                    }
            if index_data:
                logger.info(f"成功通过新浪获取 {len(index_data)} 个指数数据")
                return index_data
    except Exception as e:
        logger.warning(f"新浪接口获取指数失败: {e}")

    for code, name in index_names.items():
        try:
            df = ak.stock_zh_index_spot_em(symbol="上证系列指数" if code.startswith("sh") else "深证系列指数")
            row = df[df["代码"] == code]
            if len(row) > 0:
                r = row.iloc[0]
                index_data[name] = {
                    "code": code,
                    "value": float(r.get("最新价", 0)),
                    "change": float(r.get("涨跌幅", 0)),
                }
        except Exception as e:
            logger.warning(f"东财获取{name}失败: {e}")

    return index_data


def fetch_limit_up_pool(date_str):
    """获取涨停池数据"""
    logger.info(f"正在获取 {date_str} 涨停池...")
    for attempt in range(3):
        try:
            df = ak.stock_zt_pool_em(date=date_str)
            logger.info(f"成功获取 {len(df)} 只涨停股")
            return df
        except Exception as e:
            logger.warning(f"第{attempt+1}次获取涨停池失败: {e}")
            time.sleep(5)
    logger.warning("涨停池获取失败，返回空DataFrame")
    return pd.DataFrame()


def fetch_limit_down_pool(date_str):
    """获取跌停池数据"""
    logger.info(f"正在获取 {date_str} 跌停池...")
    try:
        df = ak.stock_zt_pool_dtgc_em(date=date_str)
        logger.info(f"成功获取 {len(df)} 只跌停股")
        return df
    except Exception as e:
        logger.warning(f"获取跌停池失败: {e}")
        return pd.DataFrame()


def fetch_broken_board_pool(date_str):
    """获取炸板池数据"""
    logger.info(f"正在获取 {date_str} 炸板池...")
    try:
        df = ak.stock_zt_pool_zbgc_em(date=date_str)
        logger.info(f"成功获取 {len(df)} 只炸板股")
        return df
    except Exception as e:
        logger.warning(f"获取炸板池失败: {e}")
        return pd.DataFrame()


def fetch_sector_flow():
    """获取行业板块资金流向"""
    logger.info("正在获取板块资金流向...")
    try:
        df = ak.stock_fund_flow_industry(symbol="即时")
        return df
    except Exception as e:
        logger.warning(f"获取板块资金流向失败: {e}")
        return pd.DataFrame()


def fetch_sector_board():
    """获取行业板块行情"""
    logger.info("正在获取行业板块行情...")
    try:
        df = ak.stock_board_industry_name_em()
        return df
    except Exception as e:
        logger.warning(f"获取行业板块行情失败: {e}")
        return pd.DataFrame()


def fetch_all(date_str=None):
    """主入口：抓取全部所需数据"""
    if date_str is None:
        date_str = get_last_trading_day()

    logger.info(f"===== 开始抓取 {date_str} 数据 =====")

    raw = {
        "date": date_str,
        "date_cn": f"{date_str[:4]}年{int(date_str[4:6])}月{int(date_str[6:8])}日",
        "spot": fetch_all_spot(),
        "index": fetch_index_data(),
        "zt_pool": fetch_limit_up_pool(date_str),
        "dt_pool": fetch_limit_down_pool(date_str),
        "zb_pool": fetch_broken_board_pool(date_str),
        "sector_flow": fetch_sector_flow(),
        "sector_board": fetch_sector_board(),
    }

    logger.info("===== 数据抓取完成 =====")
    return raw


if __name__ == "__main__":
    data = fetch_all()
    print(f"日期: {data['date_cn']}")
    print(f"全A股数量: {len(data['spot'])}")
    print(f"涨停数: {len(data['zt_pool'])}")
    print(f"跌停数: {len(data['dt_pool'])}")
    print(f"炸板数: {len(data['zb_pool'])}")

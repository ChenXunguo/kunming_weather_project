import pandas as pd
from sqlalchemy import text
from config.config import DB_CONFIG
from sqlalchemy import create_engine
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MetricsCollector:
    """系统指标收集（用于监控趋势）"""

    def __init__(self):
        self.engine = create_engine(
            f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
            f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}",
            pool_pre_ping=True
        )

    def get_daily_stats(self, days: int = 7) -> pd.DataFrame:
        """获取最近N天的统计"""
        query = text("""
            SELECT DATE(record_time) as date,
                   COUNT(*) as records,
                   AVG(temp_current) as avg_temp,
                   AVG(humidity) as avg_humidity,
                   SUM(precipitation) as total_precip
            FROM weather_data
            WHERE record_time >= DATE_SUB(NOW(), INTERVAL :days DAY)
            GROUP BY DATE(record_time)
            ORDER BY date DESC
        """)
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={'days': days})
        return df

    def get_quality_trend(self, days: int = 30) -> pd.DataFrame:
        """获取数据质量趋势"""
        query = text("""
            SELECT record_date, validity_rate, outlier_count
            FROM data_quality_log
            WHERE record_date >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
            ORDER BY record_date DESC
        """)
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={'days': days})
        return df

    def get_system_summary(self) -> dict:
        """获取系统概览"""
        with self.engine.connect() as conn:
            # 总记录数
            total = conn.execute(text("SELECT COUNT(*) FROM weather_data")).fetchone()[0]
            # 最早和最晚
            range_res = conn.execute(text("SELECT MIN(record_time), MAX(record_time) FROM weather_data")).fetchone()
            # 今日采集量
            today = conn.execute(
                text("SELECT COUNT(*) FROM weather_data WHERE DATE(record_time) = CURDATE()")
            ).fetchone()[0]
        return {
            "total_records": total,
            "first_record": range_res[0] if range_res[0] else None,
            "last_record": range_res[1] if range_res[1] else None,
            "today_records": today,
            "last_update": datetime.now()
        }
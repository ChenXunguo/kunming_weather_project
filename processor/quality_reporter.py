import pandas as pd
from sqlalchemy import text
from processor.data_cleaner import WeatherDataCleaner


class QualityReporter:
    """数据质量报告生成器"""

    def __init__(self):
        self.cleaner = WeatherDataCleaner()

    def get_daily_quality(self, days: int = 7) -> pd.DataFrame:
        """获取最近N天的质量统计"""
        query = text("""
            SELECT record_date, total_records, valid_records, 
                   outlier_count, null_filled_count, validity_rate
            FROM data_quality_log
            WHERE record_date >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
            ORDER BY record_date DESC
        """)
        with self.cleaner.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={'days': days})
        return df

    def check_95_percent_goal(self, date: str = None) -> bool:
        """检查某天是否达到95%有效率目标"""
        if date is None:
            date = pd.Timestamp.now().strftime('%Y-%m-%d')

        query = text("""
            SELECT validity_rate FROM data_quality_log
            WHERE record_date = :date
            ORDER BY created_at DESC LIMIT 1
        """)
        with self.cleaner.engine.connect() as conn:
            result = conn.execute(query, {'date': date})
            row = result.fetchone()
            if row:
                return row[0] >= 95.0
        return False
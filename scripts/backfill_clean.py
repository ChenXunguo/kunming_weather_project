import sys
from pathlib import Path
from sqlalchemy import text  # ✅补上缺失导入

sys.path.insert(0, str(Path(__file__).parent.parent))

from processor.data_cleaner import WeatherDataCleaner
from logs.logger import setup_logger
import pandas as pd
from datetime import datetime, timedelta

logger = setup_logger("backfill")


def backfill_history(days: int = 30):
    """
    回填清洗最近N天的历史数据
    建议按天分批执行，避免长事务锁表
    """
    cleaner = WeatherDataCleaner()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    logger.info(f"开始回填清洗 {start_date.date()} 至 {end_date.date()} 的历史数据")

    # 按天循环
    current = start_date
    while current <= end_date:
        date_str = current.strftime('%Y-%m-%d')
        logger.info(f"正在清洗 {date_str} 的数据...")

        try:
            # 只处理当天的数据（使用 record_time 过滤）
            query = f"""
                SELECT id, station_id, record_time,
                        temp_current, temp_max, temp_min, feels_like,
                       humidity, pressure, wind_speed, cloud_cover
                FROM weather_data
                WHERE DATE(record_time) = '{date_str}'
                ORDER BY record_time
            """

            with cleaner.engine.connect() as conn:
                df = pd.read_sql(query, conn)

            if df.empty:
                logger.info(f"{date_str} 无数据")
                current += timedelta(days=1)
                continue

            # 清洗
            cleaned_df, stats = cleaner.clean_dataframe(df)

            # 更新数据库
            update_count = 0
            with cleaner.engine.connect() as conn:
                for idx, row in cleaned_df.iterrows():
                    # 对比原值，有变化则更新
                    orig_row = df.loc[idx]
                    need_update = False
                    for col in cleaner.NUMERIC_COLS:
                        if col in row and col in orig_row:
                            if pd.isna(row[col]) and pd.isna(orig_row[col]):
                                continue
                            if pd.isna(row[col]) or pd.isna(orig_row[col]) or row[col] != orig_row[col]:
                                need_update = True
                                break

                    if need_update:
                        params = {
                            "id": int(row["id"]),
                            "temp_current": row["temp_current"] if pd.notna(row["temp_current"]) else None,
                            "temp_max": row["temp_max"] if pd.notna(row["temp_max"]) else None,
                            "temp_min": row["temp_min"] if pd.notna(row["temp_min"]) else None,
                            "feels_like": row["feels_like"] if pd.notna(row["feels_like"]) else None,
                            "humidity": row["humidity"] if pd.notna(row["humidity"]) else None,
                            "pressure": row["pressure"] if pd.notna(row["pressure"]) else None,
                            "wind_speed": row["wind_speed"] if pd.notna(row["wind_speed"]) else None,
                            "cloud_cover": row["cloud_cover"] if pd.notna(row["cloud_cover"]) else None,
                        }
                        update_sql = text("""
                            UPDATE weather_data
                            SET temp_current = :temp_current,
                                temp_max = :temp_max,
                                temp_min = :temp_min,
                                feels_like = :feels_like,
                                humidity = :humidity,
                                pressure = :pressure,
                                wind_speed = :wind_speed,
                                cloud_cover = :cloud_cover
                            WHERE id = :id
                        """)
                        conn.execute(update_sql, params)
                        update_count += 1
                conn.commit()

            # ========== 重写质量日志插入，增加 ON DUPLICATE KEY UPDATE，解决1062重复主键 ==========
            stats['outliers_fixed'] = 0
            stats['nulls_filled'] = 0
            log_date = current.date()
            log_params = {
                "date": log_date,
                "total": stats["total"],
                "valid": stats["valid"],
                "outliers": stats["outliers_fixed"],
                "nulls": stats["nulls_filled"],
                "rate": stats["validity_rate"],
                "details": str({
                    "total": stats["total"],
                    "valid": stats["valid"],
                    "nulls_filled": stats["nulls_filled"],
                    "outliers_fixed": stats["outliers_fixed"],
                    "validity_rate": stats["validity_rate"]
                })
            }
            log_sql = text("""
                INSERT INTO data_quality_log
                (record_date, total_records, valid_records, outlier_count,
                 null_filled_count, validity_rate, cleaning_details)
                VALUES (:date, :total, :valid, :outliers, :nulls, :rate, :details)
                ON DUPLICATE KEY UPDATE
                    total_records=VALUES(total_records),
                    valid_records=VALUES(valid_records),
                    outlier_count=VALUES(outlier_count),
                    null_filled_count=VALUES(null_filled_count),
                    validity_rate=VALUES(validity_rate),
                    cleaning_details=VALUES(cleaning_details)
            """)
            with cleaner.engine.connect() as conn_log:
                conn_log.execute(log_sql, log_params)
                conn_log.commit()

            logger.info(f"{date_str} 清洗完成，更新 {update_count} 行，有效率 {stats['validity_rate']}%")

        except Exception as e:
            logger.error(f"清洗 {date_str} 失败: {e}")

        current += timedelta(days=1)

    logger.info("历史数据回填清洗完成")


if __name__ == "__main__":
    # 回填最近30天数据
    backfill_history(30)

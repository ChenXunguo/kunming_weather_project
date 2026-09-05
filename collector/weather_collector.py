import logging
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from sqlalchemy import create_engine, text
from config.config import DB_URL
from collector.api_client import OpenWeatherClient
from processor.data_cleaner import WeatherDataCleaner

logger = logging.getLogger(__name__)


class WeatherCollector:
    """气象数据采集器（带数据清洗+质量日志，区分实况/预报data_type）"""

    def __init__(self):
        self.api_client = OpenWeatherClient()
        self.engine = self._get_engine()
        self.station_id = self._get_or_create_station()
        self.cleaner = WeatherDataCleaner(self.engine)  # 初始化数据清洗器

    @staticmethod
    def _get_engine():
        return create_engine(
            DB_URL,
            pool_pre_ping=True,
            connect_args={"init_command": "SET time_zone = '+08:00';"}
        )

    def _get_or_create_station(self) -> int:
        """获取或创建昆明站点记录"""
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT station_id FROM station_info WHERE city = :city LIMIT 1"),
                {"city": "昆明"}
            )
            row = result.fetchone()
            if row:
                return row[0]

            result = conn.execute(
                text("""
                    INSERT INTO station_info (station_name, city, latitude, longitude, elevation)
                    VALUES (:name, :city, :lat, :lon, :ele)
                """),
                {
                    "name": "昆明观测站",
                    "city": "昆明",
                    "lat": 25.0409,
                    "lon": 102.7123,
                    "ele": 1891.0
                }
            )
            conn.commit()
            return result.lastrowid

    def _parse_current_weather(self, data: Dict) -> Optional[Dict]:
        """解析实时天气API响应，映射到数据库字段"""
        if not data:
            return None

        try:
            dt_timestamp = data.get('dt', 0)
            record_time = datetime.utcfromtimestamp(dt_timestamp) + timedelta(hours=8)

            main = data.get('main', {})
            wind = data.get('wind', {})
            clouds = data.get('clouds', {})
            weather = data.get('weather', [{}])[0]

            return {
                'station_id': self.station_id,
                'record_time': record_time,
                'temp_current': main.get('temp'),
                'temp_max': main.get('temp_max'),
                'temp_min': main.get('temp_min'),
                'feels_like': main.get('feels_like'),
                'humidity': main.get('humidity'),
                'pressure': main.get('pressure'),
                'wind_speed': wind.get('speed'),
                'wind_direction': wind.get('deg'),
                'wind_gusts': wind.get('gust'),
                'cloud_cover': clouds.get('all'),
                'weather_desc': weather.get('description'),
                'data_source': 'OpenWeatherMap',
                'raw_data': json.dumps(data, ensure_ascii=False),
                'data_type': 1   # ✅实况
            }
        except Exception as e:
            logger.error(f"解析天气数据失败: {e}")
            return None

    def _parse_forecast(self, data: Dict) -> List[Dict]:
        """解析天气预报数据（5天/3小时间隔）"""
        if not data or 'list' not in data:
            return []

        records = []
        for item in data['list']:
            try:
                dt_timestamp = item.get('dt', 0)
                record_time = datetime.utcfromtimestamp(dt_timestamp) + timedelta(hours=8)

                main = item.get('main', {})
                wind = item.get('wind', {})
                clouds = item.get('clouds', {})
                weather = item.get('weather', [{}])[0]

                records.append({
                    'station_id': self.station_id,
                    'record_time': record_time,
                    'temp_current': main.get('temp'),
                    'temp_max': main.get('temp_max'),
                    'temp_min': main.get('temp_min'),
                    'feels_like': main.get('feels_like'),
                    'humidity': main.get('humidity'),
                    'pressure': main.get('pressure'),
                    'wind_speed': wind.get('speed'),
                    'wind_direction': wind.get('deg'),
                    'wind_gusts': wind.get('gust'),
                    'cloud_cover': clouds.get('all'),
                    'weather_desc': weather.get('description'),
                    'data_source': 'OpenWeatherMap_Forecast',
                    'raw_data': json.dumps(item, ensure_ascii=False),
                    'data_type': 2  # ✅预报
                })
            except Exception as e:
                logger.error(f"解析预报条目失败: {e}")
                continue

        return records

    def _save_to_db_with_clean(self, records: List[Dict]) -> int:
        """
        数据清洗后批量保存到数据库
        流程：列表转DataFrame → 清洗校验 → 防重插入
        """
        if not records:
            return 0

        # 1. 转为DataFrame
        df = pd.DataFrame(records)

        # 2. 执行数据清洗
        cleaned_df, stats = self.cleaner.clean_dataframe(df)
        if cleaned_df.empty:
            logger.warning("清洗后无有效数据")
            return 0

        # 3. 写入数据库（保留防重复逻辑）
        with self.engine.connect() as conn:
            inserted = 0
            for _, row in cleaned_df.iterrows():
                check = conn.execute(
                    text("""
                        SELECT id FROM weather_data
                         WHERE station_id = :station_id AND record_time = :record_time
                        LIMIT 1
                    """),
                    {"station_id": row['station_id'], "record_time": row['record_time']}
                )
                if check.fetchone():
                    logger.debug(f"数据已存在: {row['record_time']}")
                    continue

                conn.execute(
                    text("""
                        INSERT INTO weather_data (
                            station_id, record_time, temp_current, temp_max, temp_min,
                            feels_like, humidity, pressure, wind_speed, wind_direction,
                            wind_gusts, cloud_cover, weather_desc, data_source, raw_data, data_type
                        ) VALUES (
                            :station_id, :record_time, :temp_current, :temp_max, :temp_min,
                            :feels_like, :humidity, :pressure, :wind_speed, :wind_direction,
                            :wind_gusts, :cloud_cover, :weather_desc, :data_source, :raw_data, :data_type
                        )
                    """),
                    row.to_dict()
                )
                inserted += 1

            conn.commit()

        # 4. 记录当日质量统计
        self._log_quality_for_today(stats)
        return inserted

    def _log_quality_for_today(self, stats: Dict):
        """记录当天的数据质量统计，每日仅一条"""
        with self.engine.connect() as conn:
            # 按北京时间统计当日
            today = (datetime.utcnow() + timedelta(hours=8)).date()

            # 当日已有记录则跳过
            check = conn.execute(
                text("SELECT id FROM data_quality_log WHERE record_date = :date"),
                {'date': today}
            )
            if check.fetchone():
                return

            conn.execute(
                text("""
                    INSERT INTO data_quality_log
                     (record_date, total_records, valid_records, outlier_count,
                      null_filled_count, validity_rate, cleaning_details)
                    VALUES (:date, :total, :valid, :outliers, :nulls, :rate, :details)
                """),
                {
                    'date': today,
                    'total': stats.get('total', 0),
                    'valid': stats.get('valid', 0),
                    'outliers': stats.get('outliers_fixed', 0),
                    'nulls': stats.get('nulls_filled', 0),
                    'rate': stats.get('validity_rate', 0),
                    'details': json.dumps(stats, ensure_ascii=False,
                                          default=lambda x: int(x) if hasattr(x, 'item') else x)
                }
            )
            conn.commit()
            logger.info(f"当日数据质量日志已写入，合格率: {stats.get('validity_rate', 0)}%")

    def collect(self) -> Dict[str, int]:
        """
        执行一次完整采集（实时 + 预报），全程带清洗
        返回: {'current': 插入数, 'forecast': 插入数}
        """
        res = {'current': 0, 'forecast': 0}

        # 1. 采集实时数据
        logger.info("开始采集实时天气数据...")
        current_data = self.api_client.get_current_weather()
        if current_data:
            parsed = self._parse_current_weather(current_data)
            if parsed:
                res['current'] = self._save_to_db_with_clean([parsed])
                logger.info(f"实时数据采集并清洗完成，插入 {res['current']} 条")
        else:
            logger.warning("实时数据采集失败")

        # 2. 采集预报数据
        logger.info("开始采集天气预报数据...")
        forecast_data = self.api_client.get_forecast()
        if forecast_data:
            parsed_list = self._parse_forecast(forecast_data)
            if parsed_list:
                res['forecast'] = self._save_to_db_with_clean(parsed_list)
                logger.info(f"预报数据采集并清洗完成，插入 {res['forecast']} 条")
        else:
            logger.warning("预报数据采集失败")

        return res


# 独立运行入口（用于测试）
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    collector = WeatherCollector()
    result = collector.collect()
    print(f"采集完成: {result}")

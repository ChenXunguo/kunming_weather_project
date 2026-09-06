import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import logging
from typing import Dict, Tuple, Optional, List

from config.config import DB_CONFIG

logger = logging.getLogger(__name__)


class WeatherDataCleaner:
    """
    气象数据清洗器
    功能：3σ异常值检测/修正、缺失值填补、业务合理性校验
    """

    # 数值列配置：字段名 -> (合理性下限, 合理性上限)
    BOUNDS = {
        'temp_current': (-10, 35),
        'temp_max': (-10, 35),
        'temp_min': (-10, 35),
        'feels_like': (-15, 40),
        'humidity': (0, 100),
        'pressure': (800, 900),
        'wind_speed': (0, 30),
        'cloud_cover': (0, 100),
    }

    # 需要清洗的数值列
    NUMERIC_COLS = list(BOUNDS.keys())

    def __init__(self, engine=None):
        self.engine = engine or self._get_engine()

    def _get_engine(self):
        url = (f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
               f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
               f"?charset={DB_CONFIG['charset']}")
        return create_engine(url, pool_pre_ping=True)

    def _apply_3sigma(self, series: pd.Series) -> pd.Series:
        """
        对单列应用3σ原则，将超出边界的值截断至边界
        返回清洗后的Series
        """
        # 剔除NaN后计算均值和标准差
        clean_series = series.dropna()
        if len(clean_series) < 2:
            return series  # 数据太少，无法计算σ

        mean = clean_series.mean()
        std = clean_series.std()

        # 如果标准差为0，表示所有值相同，无需清洗
        if std == 0:
            return series

        lower_bound = mean - 3 * std
        upper_bound = mean + 3 * std

        # 额外应用业务合理性边界（取更严格的限制）
        col_name = series.name
        if col_name in self.BOUNDS:
            biz_lower, biz_upper = self.BOUNDS[col_name]
            lower_bound = max(lower_bound, biz_lower)
            upper_bound = min(upper_bound, biz_upper)

        # 截断（clip）至边界
        clipped = series.clip(lower=lower_bound, upper=upper_bound)

        # 记录被修改的数量（用于日志）
        modified_mask = (series != clipped) & (~series.isna())
        if modified_mask.any():
            logger.debug(f"列 {col_name}: 修正了 {modified_mask.sum()} 个异常值 "
                         f"(边界: [{lower_bound:.2f}, {upper_bound:.2f}])")

        return clipped

    def _fill_missing(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        对缺失值进行智能填补
        策略：时间序列线性插值 + 尾部/头部前向/后向填充
        """
        df_filled = df.copy()

        for col in self.NUMERIC_COLS:
            if col not in df_filled.columns:
                continue

            # 1. 先尝试线性插值（适合时间序列）
            df_filled[col] = df_filled[col].interpolate(
                method='linear',
                limit_direction='both',  # 同时填充首尾
                limit_area='inside'  # 仅填充内部缺失
            )

            # 2. 如果首尾仍有缺失，用最近的有效值填充（前向/后向）
            df_filled[col] = df_filled[col].ffill().bfill()

            # 3. 如果整列全为空（极端情况），用该列均值填充（基于历史数据）
            if df_filled[col].isna().all():
                # 从数据库查询该列的历史均值
                avg_val = self._get_historical_mean(col)
                if avg_val is not None:
                    df_filled[col] = df_filled[col].fillna(avg_val)
                else:
                    # 保底：用中位数或0
                    df_filled[col] = df_filled[col].fillna(0)

        return df_filled

    def _get_historical_mean(self, column: str) -> Optional[float]:
        """从数据库中查询某列的全局历史均值（用于极端情况保底）"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text(f"SELECT AVG({column}) FROM weather_data WHERE {column} IS NOT NULL")
                )
                row = result.fetchone()
                return float(row[0]) if row and row[0] is not None else None
        except Exception as e:
            logger.warning(f"获取历史均值失败 ({column}): {e}")
            return None

    def _check_temp_logic(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        业务逻辑校验：
        1. temp_max >= temp_current >= temp_min
        2. feels_like 与 temp_current 偏差不超过 15℃
        """
        df_checked = df.copy()

        # 规则1：确保 max >= current >= min
        if all(col in df_checked.columns for col in ['temp_max', 'temp_current', 'temp_min']):
            # 如果 current > max，将 current 设为 max
            mask = df_checked['temp_current'] > df_checked['temp_max']
            df_checked.loc[mask, 'temp_current'] = df_checked.loc[mask, 'temp_max']

            # 如果 current < min，将 current 设为 min
            mask = df_checked['temp_current'] < df_checked['temp_min']
            df_checked.loc[mask, 'temp_current'] = df_checked.loc[mask, 'temp_min']

        # 规则2：体感温度合理性
        if all(col in df_checked.columns for col in ['feels_like', 'temp_current']):
            diff = (df_checked['feels_like'] - df_checked['temp_current']).abs()
            mask = diff > 15
            # 将偏差过大的体感温度修正为当前温度
            df_checked.loc[mask, 'feels_like'] = df_checked.loc[mask, 'temp_current']

        return df_checked

    def clean_dataframe(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """
        对DataFrame执行完整清洗流程
        返回: (清洗后的DataFrame, 质量统计字典)
        """
        if df.empty:
            return df, {'total': 0, 'valid': 0, 'outliers': 0, 'nulls': 0, 'rate': 0}

        original_count = len(df)
        original_nulls = df[self.NUMERIC_COLS].isna().sum().sum() if self.NUMERIC_COLS else 0

        # 1. 确保数值列类型正确
        for col in self.NUMERIC_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # 2. 应用3σ异常值修正（就地修改）
        for col in self.NUMERIC_COLS:
            if col in df.columns:
                df[col] = self._apply_3sigma(df[col])

        # 3. 填补缺失值
        df = self._fill_missing(df)

        # 4. 业务逻辑校验
        df = self._check_temp_logic(df)

        # 5. 确保数值范围强制合规（二次保障）
        for col, (low, high) in self.BOUNDS.items():
            if col in df.columns:
                df[col] = df[col].clip(lower=low, upper=high)

        # 6. 计算质量统计
        final_nulls = df[self.NUMERIC_COLS].isna().sum().sum() if self.NUMERIC_COLS else 0
        total_cells = original_count * len(self.NUMERIC_COLS)
        valid_cells = total_cells - final_nulls

        stats = {
            'total': original_count,
            'valid': 0,  # 下方基于有效行数重新计算
            'nulls_filled': original_nulls - final_nulls,
            'outliers_fixed': 0,  # 由调用层（clean_recent_records）对比前后值统计
            'validity_rate': 0
        }

        # 计算有效行数（所有核心字段均非空）
        valid_rows = df[self.NUMERIC_COLS].dropna().shape[0]
        stats['valid'] = valid_rows
        stats['validity_rate'] = round((valid_rows / original_count) * 100, 2) if original_count > 0 else 0

        logger.info(f"清洗完成: 总记录 {original_count}, 有效行 {valid_rows}, "
                    f"有效率 {stats['validity_rate']}%, 填充空值 {stats['nulls_filled']} 个")

        return df, stats

    def clean_recent_records(self, hours: int = 24) -> Dict:
        """
        清洗最近N小时的记录（用于实时流水线）
        从数据库加载 -> 清洗 -> 更新回数据库
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # 1. 加载数据
        query = text("""
            SELECT id, station_id, record_time, 
                   temp_current, temp_max, temp_min, feels_like,
                   humidity, pressure, wind_speed, cloud_cover
            FROM weather_data
            WHERE record_time >= :cutoff_time
            ORDER BY record_time
        """)

        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={'cutoff_time': cutoff_time})

        if df.empty:
            logger.info(f"最近 {hours} 小时无新数据需要清洗")
            return {'total': 0, 'valid': 0, 'validity_rate': 100.0}

        original_df = df.copy()

        # 2. 执行清洗
        cleaned_df, stats = self.clean_dataframe(df)

        # 3. 统计异常值修正数量（对比原始数据）
        outlier_count = 0
        for col in self.NUMERIC_COLS:
            if col in original_df.columns and col in cleaned_df.columns:
                # 忽略NaN比较
                mask = (original_df[col].notna()) & (cleaned_df[col].notna())
                diff_mask = (original_df[col] != cleaned_df[col]) & mask
                outlier_count += diff_mask.sum()
        stats['outliers_fixed'] = int(outlier_count)
        stats['nulls_filled'] = int(original_df[self.NUMERIC_COLS].isna().sum().sum() -
                                    cleaned_df[self.NUMERIC_COLS].isna().sum().sum())

        # 4. 更新数据库（逐行UPDATE）
        update_count = 0
        with self.engine.connect() as conn:
            for idx, row in cleaned_df.iterrows():
                # 仅当数据有变化时才更新（对比原始值）
                orig_row = original_df.loc[idx]
                need_update = False
                for col in self.NUMERIC_COLS:
                    if col in row and col in orig_row:
                        # 处理NaN比较
                        if pd.isna(row[col]) and pd.isna(orig_row[col]):
                            continue
                        if pd.isna(row[col]) or pd.isna(orig_row[col]) or row[col] != orig_row[col]:
                            need_update = True
                            break

                if need_update:
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
                    params = {col: row[col] for col in self.NUMERIC_COLS if col in row}
                    params['id'] = row['id']
                    conn.execute(update_sql, params)
                    update_count += 1

            conn.commit()

        stats['updated_rows'] = update_count
        logger.info(f"数据库更新完成: {update_count} 行被修正")

        # 5. 写入质量日志
        self._log_quality(stats, cutoff_time)

        return stats

    def _log_quality(self, stats: Dict, record_date: datetime):
        """将质量统计写入 data_quality_log 表【修复主键冲突】"""
        with self.engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO data_quality_log 
                        (record_date, total_records, valid_records, outlier_count, 
                         null_filled_count, validity_rate, cleaning_details)
                    VALUES 
                        (:date, :total, :valid, :outliers, :nulls, :rate, :details)
                    ON DUPLICATE KEY UPDATE
                        total_records = VALUES(total_records),
                        valid_records = VALUES(valid_records),
                        outlier_count = VALUES(outlier_count),
                        null_filled_count = VALUES(null_filled_count),
                        validity_rate = VALUES(validity_rate),
                        cleaning_details = VALUES(cleaning_details)
                """),
                {
                    'date': record_date.date(),
                    'total': stats.get('total', 0),
                    'valid': stats.get('valid', 0),
                    'outliers': stats.get('outliers_fixed', 0),
                    'nulls': stats.get('nulls_filled', 0),
                    'rate': stats.get('validity_rate', 0),
                    'details': str(stats)
                }
            )
            conn.commit()

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Tuple


class FeatureEngineer:
    """气象预测特征工程"""

    # 核心数值特征列
    FEATURE_COLS = ['temp_current', 'humidity', 'pressure', 'wind_speed', 'cloud_cover']

    @staticmethod
    def add_time_features(df: pd.DataFrame, time_col: str = 'record_time') -> pd.DataFrame:
        """添加时间周期特征（用于捕捉日周期和季节周期）"""
        df_copy = df.copy()

        # 确保时间是datetime类型
        if not pd.api.types.is_datetime64_any_dtype(df_copy[time_col]):
            df_copy[time_col] = pd.to_datetime(df_copy[time_col])

        # 循环时间特征（用sin/cos编码，保留周期性）
        hour = df_copy[time_col].dt.hour
        df_copy['hour_sin'] = np.sin(2 * np.pi * hour / 24)
        df_copy['hour_cos'] = np.cos(2 * np.pi * hour / 24)

        day_of_year = df_copy[time_col].dt.dayofyear
        df_copy['doy_sin'] = np.sin(2 * np.pi * day_of_year / 365)
        df_copy['doy_cos'] = np.cos(2 * np.pi * day_of_year / 365)

        # 简单辅助特征
        df_copy['month'] = df_copy[time_col].dt.month
        df_copy['day_of_week'] = df_copy[time_col].dt.dayofweek

        return df_copy

    @staticmethod
    def add_lag_features(df: pd.DataFrame, target_col: str = 'temp_current',
                         lag_hours: list = None) -> pd.DataFrame:
        """
        添加滞后特征（将历史值作为预测特征）
        lag_hours: 例如 [6, 12, 24] 表示过去6/12/24小时的气温
        注意：数据需按时间升序排列
        """
        if lag_hours is None:
            lag_hours = [6, 12, 24]

        df_copy = df.copy()
        df_copy = df_copy.sort_values('record_time').reset_index(drop=True)

        # 计算相邻记录的时间间隔（小时）
        time_diffs = df_copy['record_time'].diff().dt.total_seconds() / 3600
        median_interval = time_diffs.median()

        if pd.isna(median_interval) or median_interval == 0:
            median_interval = 3  # 默认3小时间隔

        for lag_hour in lag_hours:
            steps = int(round(lag_hour / median_interval))
            lag_col = f'{target_col}_lag_{lag_hour}h'
            df_copy[lag_col] = df_copy[target_col].shift(steps)

        return df_copy

    @staticmethod
    def add_rolling_features(df: pd.DataFrame, target_col: str = 'temp_current',
                             windows: list = None) -> pd.DataFrame:
        """添加滚动统计特征（滑动窗口均值/标准差）"""
        if windows is None:
            windows = [3, 6]

        df_copy = df.copy()
        df_copy = df_copy.sort_values('record_time').reset_index(drop=True)
        time_diffs = df_copy['record_time'].diff().dt.total_seconds() / 3600
        median_interval = time_diffs.median()
        if pd.isna(median_interval) or median_interval == 0:
            median_interval = 3

        for window_steps in windows:
            df_copy[f'{target_col}_rollmean_{window_steps}'] = (
                df_copy[target_col].rolling(window=window_steps, min_periods=1).mean()
            )
            df_copy[f'{target_col}_rollstd_{window_steps}'] = (
                df_copy[target_col].rolling(window=window_steps, min_periods=1).std()
            )
        return df_copy

    @staticmethod
    def add_pressure_diff_feature(df: pd.DataFrame, lag_hour=3) -> pd.DataFrame:
        """气压3小时差分特征 pressure_diff_3h，统一在这里生成"""
        df_copy = df.copy()
        df_copy = df_copy.sort_values("record_time").reset_index(drop=True)
        time_diffs = df_copy['record_time'].diff().dt.total_seconds() / 3600
        median_interval = time_diffs.median()
        if pd.isna(median_interval) or median_interval == 0:
            median_interval = 3
        steps = int(round(lag_hour / median_interval))
        df_copy['pressure_lag_3h'] = df_copy['pressure'].shift(steps)
        df_copy['pressure_diff_3h'] = df_copy['pressure'] - df_copy['pressure_lag_3h']
        df_copy.drop(columns=["pressure_lag_3h"], inplace=True)
        return df_copy

    @staticmethod
    def prepare_prediction_data(df: pd.DataFrame, target_hours: int = 6) -> Tuple[pd.DataFrame, pd.Series, list]:
        """
        构造监督学习数据集：把未来N小时气温作为标签y
        :param df: 已经做完全部特征工程后的df
        :param target_hours: 预测未来多少小时
        :return: X特征，y标签，特征列名列表
        """
        df_copy = df.copy().sort_values("record_time").reset_index(drop=True)
        time_diffs = df_copy['record_time'].diff().dt.total_seconds() / 3600
        median_interval = time_diffs.median()
        if pd.isna(median_interval) or median_interval == 0:
            median_interval = 3
        shift_steps = int(round(target_hours / median_interval))

        # y:未来target_hours的气温
        df_copy['y_target'] = df_copy['temp_current'].shift(-shift_steps)

        # 剔除NA：lag、rolling、shift标签带来空值
        df_copy = df_copy.dropna()

        # ==========修复点：新增"id"到排除列表==========
        exclude_cols = ["record_time", "y_target", "id"]
        feature_cols = [c for c in df_copy.columns if c not in exclude_cols]

        X = df_copy[feature_cols].copy()
        y = df_copy['y_target'].copy()
        return X, y, feature_cols


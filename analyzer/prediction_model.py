import sys
from pathlib import Path
# 项目根目录加入搜索路径，兼容直接运行本文件
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from sqlalchemy import text
import logging
from datetime import datetime, timedelta
import json
import pickle
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

from analyzer.feature_engineering import FeatureEngineer
from config.config import DB_URL
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)


class TemperaturePredictor:
    """短期气温预测模型"""

    def __init__(self):
        self.engine = create_engine(
            DB_URL,
            pool_pre_ping=True,
            connect_args={"init_command": "SET time_zone = '+08:00';"}
        )
        # 实例化特征工程对象
        self.feature_engineer = FeatureEngineer()

        self.model = None
        self.scaler = None
        self.target_hours = None
        # 统一变量名 model_dir，和save_model保持一致
        self.model_dir = Path(__file__).resolve().parent.parent / "model_cache"
        self.model_dir.mkdir(exist_ok=True)

    def load_training_data(self, days: int = 60) -> pd.DataFrame:
        """加载训练数据（最近N天，仅实况data_type=1）"""
        query = text("""
            SELECT id, record_time, temp_current, humidity, pressure,
                    wind_speed, cloud_cover
            FROM weather_data
            WHERE record_time >= DATE_SUB(NOW(), INTERVAL :days DAY)
            AND temp_current IS NOT NULL
            AND data_type = 1
            ORDER BY record_time
        """)
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={'days': days})
        logger.info(f"加载了 {len(df)} 条训练数据")
        return df

    def prepare_features(self, df: pd.DataFrame, target_hours: int = 6) -> tuple:
        """
        特征工程 + 构造监督学习标签：预测未来target_hours的气温
        当前数据量较小，移除24h滞后/滚动窗口；后续数据充足再恢复
        return X,y
        """
        df_fe = self.feature_engineer.add_time_features(df, "record_time")
        df_fe = self.feature_engineer.add_lag_features(df_fe, "temp_current", lag_hours=[3, 6, 12,24])
        df_fe = self.feature_engineer.add_rolling_features(df_fe, "temp_current", windows=[3, 6, 12,24])
        df_fe = self.feature_engineer.add_pressure_diff_feature(df_fe)

        df_fe["target_temp"] = df_fe["temp_current"].shift(-target_hours)
        df_fe = df_fe.dropna()

        feature_cols = self.feature_engineer.FEATURE_COLS + [
            "hour_sin", "hour_cos", "month_sin", "month_cos",
            "lag_3_temp_current", "lag_6_temp_current", "lag_12_temp_current", "lag_24_temp_current",
            "roll_3_mean_temp_current", "roll_6_mean_temp_current", "roll_12_mean_temp_current",
            "roll_24_mean_temp_current",
            "roll_3_std_temp_current", "roll_6_std_temp_current", "roll_12_std_temp_current",
            "roll_24_std_temp_current",  "pressure_diff"
        ]
        self.feature_cols = [c for c in feature_cols if c in df_fe.columns]
        X = df_fe[self.feature_cols].copy()
        y = df_fe["target_temp"].copy()
        logger.info(f"特征工程完成，有效样本 X:{len(X)}")
        return X, y

    def train(self, X: pd.DataFrame, y: pd.Series, model_type: str = 'rf') -> dict:
        """模型训练，返回评估指标"""
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        if model_type == "rf":
            self.model = RandomForestRegressor(
                n_estimators=100,
                max_depth=None,
                min_samples_split=2,
                min_samples_leaf=1,
                random_state=42,
                n_jobs=-1
            )
        else:
            self.model = LinearRegression()

        self.model.fit(X_train_scaled, y_train)
        y_pred_train = self.model.predict(X_train_scaled)
        y_pred_test = self.model.predict(X_test_scaled)

        metrics = {
            "train_rmse": float(np.sqrt(mean_squared_error(y_train, y_pred_train))),
            "test_rmse": float(np.sqrt(mean_squared_error(y_test, y_pred_test))),
            "train_mae": float(mean_absolute_error(y_train, y_pred_train)),
            "test_mae": float(mean_absolute_error(y_test, y_pred_test)),
            "r2": float(r2_score(y_test, y_pred_test))
        }
        logger.info(f"模型训练完成，test_rmse={metrics['test_rmse']:.3f}℃")
        self.save_model(model_type)
        return metrics

    def predict_future(self, hours_ahead: int = 6) -> pd.DataFrame:
        """滚动预测未来1~hours_ahead小时气温"""
        if self.model is None:
            raise ValueError("请先训练或加载模型")

        query = text("""
            SELECT record_time, temp_current, humidity, pressure, wind_speed, cloud_cover
            FROM weather_data
            WHERE record_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
              AND data_type = 1
            ORDER BY record_time DESC
            LIMIT 200
        """)
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)

        if df.empty:
            logger.warning("无数据可用于预测")
            return pd.DataFrame()

        df["record_time"] = pd.to_datetime(df["record_time"])
        df = df.sort_values("record_time").reset_index(drop=True)
        base_time = df.iloc[-1]["record_time"]
        logger.info(f"【DEBUG】base_time type:{type(base_time)}, value:{base_time}")

        pred_records = []
        current_df = df.copy()

        for step in range(1, hours_ahead + 1):
            df_fe = self.feature_engineer.add_time_features(current_df, "record_time")
            df_fe = self.feature_engineer.add_lag_features(df_fe, "temp_current", lag_hours=[3, 6, 12,24])
            df_fe = self.feature_engineer.add_rolling_features(df_fe, "temp_current", windows=[3, 6, 12,24])
            df_fe = self.feature_engineer.add_pressure_diff_feature(df_fe)

            latest_idx = len(df_fe) - 1
            X_latest = df_fe.iloc[[latest_idx]].copy()

            missing_cols = set(self.feature_cols) - set(X_latest.columns)
            for col in missing_cols:
                X_latest[col] = 0
            X_latest = X_latest[self.feature_cols].fillna(0)

            X_scaled = self.scaler.transform(X_latest)
            pred_temp = self.model.predict(X_scaled)[0]

            pred_time = base_time + timedelta(hours=step)
            pred_records.append({
                "prediction_time": pred_time,
                "predicted_temp": round(pred_temp, 2),
                "base_time": base_time,
                "hours_ahead": step
            })
            logger.info(f"预测 {step}h后: {pred_time} 气温 {pred_temp:.2f}℃")

            new_row = {
                "record_time": pred_time,
                "temp_current": pred_temp,
                "humidity": current_df.iloc[-1]["humidity"],
                "pressure": current_df.iloc[-1]["pressure"],
                "wind_speed": current_df.iloc[-1]["wind_speed"],
                "cloud_cover": current_df.iloc[-1]["cloud_cover"]
            }
            current_df = pd.concat([current_df, pd.DataFrame([new_row])], ignore_index=True)

        return pd.DataFrame(pred_records)

    def save_model(self, model_type: str = 'rf'):
        """保存模型和Scaler"""
        if self.model is None:
            logger.warning("无模型可保存")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_path = self.model_dir / f'temp_predictor_{self.target_hours}h_{model_type}_{timestamp}.pkl'
        scaler_path = self.model_dir / f'scaler_{self.target_hours}h_{timestamp}.pkl'

        with open(model_path, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'feature_cols': self.feature_cols,
                'target_hours': self.target_hours,
                'model_type': model_type
            }, f)

        with open(scaler_path, 'wb') as f:
            pickle.dump(self.scaler, f)
        logger.info(f"模型已保存: {model_path}")
        logger.info(f"Scaler已保存: {scaler_path}")

    def load_model(self, model_path: str, scaler_path: str):
        with open(model_path, "rb") as f:
            model_data = pickle.load(f)
        self.model = model_data["model"]
        self.feature_cols = model_data["feature_cols"]
        self.target_hours = model_data["target_hours"]
        with open(scaler_path, "rb") as f:
            self.scaler = pickle.load(f)
        logger.info("模型加载完成")

    def save_prediction_to_db(self, prediction_df: pd.DataFrame):
        """预测结果写入analysis_results"""
        if prediction_df.empty:
            return

        with self.engine.connect() as conn:
            for _, row in prediction_df.iterrows():
                conn.execute(
                    text("""
                        INSERT INTO analysis_results
                            (analysis_type, analysis_date, variable_x, variable_y,
                             prediction_value, model_params)
                        VALUES
                            ('prediction', :analysis_date, 'temp_current', :variable_y,
                             :prediction_value, :model_params)
                    """),
                    {
                        "analysis_date": datetime.now().date(),
                        "variable_y": f"future_{int(row['hours_ahead'])}h",
                        "prediction_value": float(row["predicted_temp"]),
                        "model_params": json.dumps({
                            "base_time": row["base_time"].isoformat(),
                            "prediction_time": row["prediction_time"].isoformat(),
                            "hours_ahead": int(row["hours_ahead"]),
                            "model": "RandomForestRegressor"
                        }, ensure_ascii=False)
                    }
                )
            conn.commit()
        logger.info(f"{len(prediction_df)}条预测结果已存入数据库")

    def _save_model_metadata(self, metrics: dict):
        """保存模型评估指标元数据入库"""
        today = datetime.now().date()
        with self.engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO analysis_results
                    (analysis_type, analysis_date, model_params)
                    VALUES (:atype, :adate, :params)
                """),
                {
                    "atype": "model_metric",
                    "adate": today,
                    "params": json.dumps(metrics, ensure_ascii=False)
                }
            )
            conn.commit()
        logger.info("模型评估元数据已入库")

    def train_and_evaluate_pipeline(self, days: int = 60, target_hours: int = 6):
        """完整的训练和评估流水线"""
        logger.info(f"===== 开始训练预测模型 (目标: 未来{target_hours}小时气温) =====")
        self.target_hours = target_hours

        df = self.load_training_data(days)
        if len(df) < 30:
            logger.error(f"数据量不足 (仅{len(df)}条)，至少需要30条原始实况数据")
            return None

        X, y = self.prepare_features(df, target_hours)
        if len(X) < 10:
            logger.error("特征生成后样本量不足")
            return None

        metrics_rf = self.train(X, y, 'rf')
        self._save_model_metadata(metrics_rf)
        return metrics_rf


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    predictor = TemperaturePredictor()
    metrics = predictor.train_and_evaluate_pipeline(days=60, target_hours=6)
    if metrics:
        pred_df = predictor.predict_future(6)
        predictor.save_prediction_to_db(pred_df)

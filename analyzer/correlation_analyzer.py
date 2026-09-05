import matplotlib.pyplot as plt
plt.switch_backend('Agg')       # 新增：禁用GUI后端，解决APScheduler子线程绘图警告
plt.rcParams['font.sans-serif'] = ['SimHei']   # Windows黑体
plt.rcParams['axes.unicode_minus'] = False     # 解决负号显示异常

import pandas as pd
import numpy as np
import seaborn as sns
from sqlalchemy import text
import logging
from datetime import datetime, timedelta
from pathlib import Path
import json

from config.config import DB_CONFIG
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)



class CorrelationAnalyzer:
    """多维相关性分析器"""

    # 核心分析变量
    CORE_VARS = ['temp_current', 'temp_max', 'temp_min', 'feels_like',
                 'humidity', 'pressure', 'wind_speed', 'cloud_cover']

    def __init__(self):
        self.engine = create_engine(
            f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
            f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
            f"?charset={DB_CONFIG['charset']}",
            pool_pre_ping=True
        )
        self.output_dir = Path(__file__).parent.parent / 'reports' / 'figures'
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_recent_data(self, days: int = 30) -> pd.DataFrame:
        """加载最近N天的气象数据用于分析"""
        query = text("""
            SELECT record_time, temp_current, temp_max, temp_min, feels_like,
                   humidity, pressure, wind_speed, cloud_cover, precipitation
            FROM weather_data
            WHERE record_time >= DATE_SUB(NOW(), INTERVAL :days DAY)
            ORDER BY record_time
        """)
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={'days': days})
        logger.info(f"加载了 {len(df)} 条记录，时间范围：{days} 天")
        return df

    def compute_correlation_matrix(self, df: pd.DataFrame, method: str = 'pearson') -> pd.DataFrame:
        """计算变量间的相关系数矩阵"""
        # 选取数值列
        available_vars = [v for v in self.CORE_VARS if v in df.columns]
        corr_df = df[available_vars].corr(method=method)
        return corr_df

    def plot_heatmap(self, corr_df: pd.DataFrame, title: str = "气象变量相关性热力图",
                     save: bool = True) -> plt.Figure:
        """绘制相关性热力图"""
        fig, ax = plt.subplots(figsize=(10, 8))

        # 生成mask只显示下三角
        mask = np.triu(np.ones_like(corr_df, dtype=bool))

        sns.heatmap(corr_df, mask=mask, annot=True, fmt='.2f',
                    cmap='RdBu_r', center=0, square=True,
                    linewidths=0.5, cbar_kws={"shrink": 0.8},
                    ax=ax)

        ax.set_title(title, fontsize=16, fontweight='bold')
        ax.tick_params(rotation=45)

        plt.tight_layout()
        if save:
            save_path = self.output_dir / f'correlation_heatmap_{datetime.now().strftime("%Y%m%d")}.png'
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            logger.info(f"热力图已保存: {save_path}")

        # 关键：子线程绘图完成立刻释放画布，避免退出时报tkinter错误
        plt.close(fig)
        return fig

    def analyze_correlation_with_temp(self, df: pd.DataFrame) -> pd.Series:
        """
        分析各变量与气温（temp_current）的相关性
        返回按相关系数绝对值排序的Series
        """
        if 'temp_current' not in df.columns:
            raise ValueError("数据中缺少 temp_current 列")

        numeric_cols = df.select_dtypes(include=[np.number]).columns
        corr_with_temp = df[numeric_cols].corrwith(df['temp_current']).drop('temp_current')
        # 按绝对值排序
        sorted_corr = corr_with_temp.reindex(corr_with_temp.abs().sort_values(ascending=False).index)

        logger.info("与气温相关性最强的变量（绝对值）：")
        for var, corr in sorted_corr.head(5).items():
            logger.info(f"  {var}: {corr:.3f}")

        return sorted_corr

    def save_correlation_to_db(self, corr_matrix: pd.DataFrame):
        """相关性矩阵逐条入库，过滤NaN"""
        with self.engine.connect() as conn:
            insert_count = 0
            for col_x in corr_matrix.columns:
                for col_y in corr_matrix.index:
                    if col_x == col_y:
                        continue
                    val = corr_matrix.loc[col_y, col_x]
                    # ✅过滤NaN，MySQL不允许存储nan
                    if pd.isna(val):
                        continue
                    conn.execute(
                        text("""
                            INSERT INTO analysis_results
                                (analysis_type, analysis_date, variable_x, variable_y,
                                 correlation_coefficient)
                            VALUES
                                ('correlation', :analysis_date, :variable_x, :variable_y,
                                 :correlation_coefficient)
                        """),
                        {
                            "analysis_date": datetime.now().date(),
                            "variable_x": col_x,
                            "variable_y": col_y,
                            "correlation_coefficient": float(val)
                        }
                    )
                    insert_count += 1
            conn.commit()
        logger.info(f"相关性分析结果已保存入库，共插入{insert_count}条")

    def run_full_analysis(self, days: int = 30):
        """执行完整相关性分析流程"""
        logger.info(f"开始相关性分析（最近 {days} 天）...")

        # 1. 加载数据
        df = self.load_recent_data(days)
        if df.empty:
            logger.warning("无数据可分析")
            return

        # 2. 计算相关系数矩阵
        corr_matrix = self.compute_correlation_matrix(df)

        # 3. 绘制热力图
        self.plot_heatmap(corr_matrix)

        # 4. 分析各变量与气温的相关性
        corr_with_temp = self.analyze_correlation_with_temp(df)
        logger.info(f"与气温最强正相关: {corr_with_temp.idxmax()} = {corr_with_temp.max():.3f}")
        logger.info(f"与气温最强负相关: {corr_with_temp.idxmin()} = {corr_with_temp.min():.3f}")

        # 5. 保存结果到数据库 ✅修复：移除多余days参数
        self.save_correlation_to_db(corr_matrix)

        return corr_matrix, corr_with_temp


if __name__ == "__main__":
    # 测试运行
    logging.basicConfig(level=logging.INFO)
    analyzer = CorrelationAnalyzer()
    analyzer.run_full_analysis(30)
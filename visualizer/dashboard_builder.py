from pyecharts.charts import Page, Tab
from pyecharts.globals import CurrentConfig
import pandas as pd
from pathlib import Path
from datetime import datetime
import logging

from visualizer.chart_generator import ChartGenerator
from sqlalchemy import text, create_engine
from config.config import DB_CONFIG

logger = logging.getLogger(__name__)


class DashboardBuilder:
    """数据看板构建器"""

    def __init__(self):
        self.chart_gen = ChartGenerator()
        self.engine = create_engine(
            f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
            f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
            f"?charset={DB_CONFIG['charset']}",
            pool_pre_ping=True
        )
        self.output_dir = Path(__file__).parent.parent / 'reports' / 'dashboards'
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _load_weather_data(self, days: int = 30) -> pd.DataFrame:
        """加载近期气象数据"""
        query = text("""
            SELECT record_time, temp_current, temp_max, temp_min, feels_like,
                   humidity, pressure, wind_speed, cloud_cover, weather_desc,
                   precipitation
            FROM weather_data
            WHERE record_time >= DATE_SUB(NOW(), INTERVAL :days DAY)
            ORDER BY record_time
        """)
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={'days': days})
        return df

    def _load_correlation_data(self) -> pd.DataFrame:
        """加载最新相关性矩阵"""
        query = text("""
            SELECT variable_x, variable_y, correlation_coefficient
            FROM analysis_results
            WHERE analysis_type = 'correlation'
            ORDER BY analysis_date DESC, ABS(correlation_coefficient) DESC
            LIMIT 100
        """)
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)

        if df.empty:
            return pd.DataFrame()

        # 构建矩阵
        vars_list = list(set(df['variable_x'].tolist() + df['variable_y'].tolist()))
        corr_matrix = pd.DataFrame(index=vars_list, columns=vars_list)
        for _, row in df.iterrows():
            corr_matrix.loc[row['variable_x'], row['variable_y']] = row['correlation_coefficient']
            corr_matrix.loc[row['variable_y'], row['variable_x']] = row['correlation_coefficient']
        # 对角线设为1
        for v in vars_list:
            corr_matrix.loc[v, v] = 1.0
        return corr_matrix.fillna(0)

    def _load_prediction_data(self) -> pd.DataFrame:
        """加载最新预测结果"""
        query = text("""
            SELECT prediction_value, model_params, analysis_date
            FROM analysis_results
            WHERE analysis_type = 'prediction'
            ORDER BY analysis_date DESC
            LIMIT 5
        """)
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)
        return df

    def _create_kpi_cards(self, df: pd.DataFrame) -> str:
        """生成KPI指标卡HTML（内嵌于看板）"""
        if df.empty:
            return "<div>暂无数据</div>"

        latest = df.iloc[-1]
        avg_temp = df['temp_current'].mean() if 'temp_current' in df.columns else 0
        max_temp = df['temp_current'].max() if 'temp_current' in df.columns else 0
        min_temp = df['temp_current'].min() if 'temp_current' in df.columns else 0
        avg_humidity = df['humidity'].mean() if 'humidity' in df.columns else 0

        # 查询数据有效率
        quality_query = text("""
            SELECT validity_rate FROM data_quality_log 
            WHERE record_date = CURDATE()
            ORDER BY created_at DESC LIMIT 1
        """)
        with self.engine.connect() as conn:
            q_result = conn.execute(quality_query)
            q_row = q_result.fetchone()
            validity_rate = q_row[0] if q_row else 0

        html = f"""
        <div style="display:flex; justify-content:space-around; flex-wrap:wrap; padding:20px 0; background:#f8f9fa; border-radius:8px;">
            <div style="text-align:center; padding:10px 20px; background:white; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.1); min-width:120px;">
                <div style="font-size:14px; color:#888;">当前温度</div>
                <div style="font-size:28px; font-weight:bold; color:#5470C6;">{latest.get('temp_current', 0):.1f}℃</div>
            </div>
            <div style="text-align:center; padding:10px 20px; background:white; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.1); min-width:120px;">
                <div style="font-size:14px; color:#888;">平均温度</div>
                <div style="font-size:28px; font-weight:bold; color:#91CC75;">{avg_temp:.1f}℃</div>
            </div>
            <div style="text-align:center; padding:10px 20px; background:white; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.1); min-width:120px;">
                <div style="font-size:14px; color:#888;">最高/最低</div>
                <div style="font-size:28px; font-weight:bold; color:#EE6666;">{max_temp:.1f} / {min_temp:.1f}℃</div>
            </div>
            <div style="text-align:center; padding:10px 20px; background:white; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.1); min-width:120px;">
                <div style="font-size:14px; color:#888;">平均湿度</div>
                <div style="font-size:28px; font-weight:bold; color:#73C0DE;">{avg_humidity:.1f}%</div>
            </div>
            <div style="text-align:center; padding:10px 20px; background:white; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.1); min-width:120px;">
                <div style="font-size:14px; color:#888;">数据有效率</div>
                <div style="font-size:28px; font-weight:bold; color:{'#3BA272' if validity_rate >= 95 else '#EE6666'};">{validity_rate:.1f}%</div>
            </div>
        </div>
        """
        return html

    def build_dashboard(self, days: int = 30, output_filename: str = None) -> str:
        """
        构建完整看板HTML
        返回: HTML文件路径
        """
        logger.info(f"开始构建看板（最近 {days} 天）...")

        # 1. 加载数据
        df_weather = self._load_weather_data(days)
        if df_weather.empty:
            logger.warning("无数据，生成空看板")
            return ""

        corr_matrix = self._load_correlation_data()
        df_pred = self._load_prediction_data()

        # 2. 生成图表
        chart_trend = self.chart_gen.create_temperature_trend_chart(df_weather)
        chart_humidity = self.chart_gen.create_humidity_pressure_chart(df_weather)
        chart_pie = self.chart_gen.create_weather_distribution_pie(df_weather)
        chart_heatmap = self.chart_gen.create_correlation_heatmap(corr_matrix)
        chart_precip = self.chart_gen.create_precipitation_bar(df_weather)

        # 3. 创建KPI卡片HTML
        kpi_html = self._create_kpi_cards(df_weather)

        # 4. 组装Page
        page = Page(layout=Page.DraggablePageLayout, page_title="昆明气象数据看板")

        # 不再使用废弃Html组件！先加全部图表，KPI卡片后续通过字符串替换注入HTML
        page.add(chart_trend)
        page.add(chart_humidity, chart_pie)
        page.add(chart_heatmap, chart_precip)

        # 5. 渲染临时HTML
        if output_filename is None:
            output_filename = f"dashboard_{datetime.now().strftime('%Y%m%d')}.html"

        output_path = self.output_dir / output_filename
        temp_html = str(self.output_dir / "_tmp_page.html")
        page.render(temp_html)

        # 读取渲染出来的html，把KPI卡片插入到第一个图表div前面
        with open(temp_html, "r", encoding="utf-8") as f:
            page_content = f.read()

        # 将KPI卡片插入到第一个echarts容器之前
        insert_mark = '<div class="chart-container"'
        final_html = page_content.replace(insert_mark, f"{kpi_html}\n{insert_mark}", 1)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_html)

        # 删除临时文件
        import os
        if os.path.exists(temp_html):
            os.remove(temp_html)

        logger.info(f"看板已生成: {output_path}")
        return str(output_path)



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    builder = DashboardBuilder()
    builder.build_dashboard(days=30)
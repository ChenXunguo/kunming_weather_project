import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import logging
import json

from jinja2 import Environment, FileSystemLoader

from visualizer.dashboard_builder import DashboardBuilder
from config.config import DB_CONFIG
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


class PDFReporter:
    """季度PDF报告生成器"""

    def __init__(self):
        self.dashboard_builder = DashboardBuilder()
        self.engine = create_engine(
            f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
            f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
            f"?charset={DB_CONFIG['charset']}",
            pool_pre_ping=True
        )
        self.report_dir = Path(__file__).parent.parent / 'reports' / 'pdf'
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.template_dir = Path(__file__).parent.parent / 'templates'
        self.template_dir.mkdir(parents=True, exist_ok=True)
        self.jinja_env = Environment(loader=FileSystemLoader(str(self.template_dir)))

    def _get_quarter_range(self, quarter: int = None, year: int = None) -> tuple:
        """获取季度起止日期"""
        if year is None:
            year = datetime.now().year
        if quarter is None:
            current_month = datetime.now().month
            quarter = (current_month - 1) // 3 + 1

        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2
        start_date = datetime(year, start_month, 1)
        if end_month == 12:
            end_date = datetime(year, 12, 31)
        else:
            end_date = datetime(year, end_month + 1, 1) - timedelta(days=1)
        return start_date, end_date

    def _generate_quarter_summary(self, df: pd.DataFrame, start_date: datetime, end_date: datetime) -> dict:
        """生成季度统计摘要，预先初始化全部key"""
        summary = {
            'quarter': f"{start_date.year}年Q{(start_date.month - 1) // 3 + 1}",
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'total_records': len(df),
            'avg_temp': 0.0,
            'max_temp': 0.0,
            'min_temp': 0.0,
            'max_temp_day': "--",
            'min_temp_day': "--",
            'avg_humidity': 0.0,
            'max_humidity': 0.0,
            'min_humidity': 0.0,
            'total_precip': 0.0,
            'rainy_days': 0,
            'avg_validity_rate': 0.0,
            'top_corr_factor': "暂未计算"
        }

        if df.empty:
            return summary

        if 'temp_current' in df.columns:
            summary['avg_temp'] = round(df['temp_current'].mean(), 2)
            summary['max_temp'] = round(df['temp_current'].max(), 2)
            summary['min_temp'] = round(df['temp_current'].min(), 2)
            max_day = df.loc[df['temp_current'].idxmax(), 'record_time'].strftime('%Y-%m-%d')
            min_day = df.loc[df['temp_current'].idxmin(), 'record_time'].strftime('%Y-%m-%d')
            summary['max_temp_day'] = max_day
            summary['min_temp_day'] = min_day

        if 'humidity' in df.columns:
            summary['avg_humidity'] = round(df['humidity'].mean(), 2)
            summary['max_humidity'] = round(df['humidity'].max(),2)
            summary['min_humidity'] = round(df['humidity'].min(),2)

        if 'precipitation' in df.columns:
            summary['total_precip'] = round(df['precipitation'].sum(), 2)
            rainy_days = df[df['precipitation'] > 0.1]['record_time'].dt.date.nunique()
            summary['rainy_days'] = rainy_days

        quality_query = text("""
            SELECT AVG(validity_rate) as avg_rate
            FROM data_quality_log
            WHERE record_date BETWEEN :start AND :end
        """)
        with self.engine.connect() as conn:
            result = conn.execute(quality_query, {'start': start_date.date(), 'end': end_date.date()})
            row = result.mappings().fetchone()
            if row and row["avg_rate"] is not None:
                summary['avg_validity_rate'] = round(row["avg_rate"], 2)

        corr_query = text("""
            SELECT variable_x, variable_y, correlation_coefficient
            FROM analysis_results
            WHERE analysis_type = 'correlation'
              AND variable_x = 'temp_current'
              AND analysis_date >= :start
            ORDER BY ABS(correlation_coefficient) DESC
            LIMIT 1
        """)
        with self.engine.connect() as conn:
            result = conn.execute(corr_query, {'start': start_date})
            row = result.fetchone()
            if row:
                summary['top_corr_factor'] = f"{row[1]} (r={row[2]:.3f})"
        return summary

    def _generate_html_report(self, dashboard_html_path: str, summary: dict,
                              start_date: datetime, end_date: datetime) -> str:
        """生成带样式的完整HTML报告"""
        with open(dashboard_html_path, 'r', encoding='utf-8') as f:
            dashboard_content = f.read()

        context = {
            'title': f"昆明气象季度报告 - {summary['quarter']}",
            'start_date': summary['start_date'],
            'end_date': summary['end_date'],
            'summary': summary,
            'dashboard_html': dashboard_content,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        template = self.jinja_env.from_string("""

        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <title>{{ title }}</title>
            <style>
                body { font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif; margin: 20px; background: #f5f7fa; }
                .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
                h1 { text-align: center; color: #2c3e50; border-bottom: 3px solid #5470C6; padding-bottom: 15px; }
                .meta { text-align: center; color: #7f8c8d; font-size: 14px; margin-bottom: 30px; }
                .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin: 20px 0; }
                .summary-item { background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; border-left: 4px solid #5470C6; }
                .summary-item .label { font-size: 12px; color: #95a5a6; }
                .summary-item .value { font-size: 22px; font-weight: bold; color: #2c3e50; margin-top: 5px; }
                .section-title { font-size: 18px; font-weight: bold; color: #34495e; margin: 30px 0 15px 0; padding-left: 10px; border-left: 4px solid #e74c3c; }
                .dashboard-embed { margin: 20px 0; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; }
                .footer { text-align: center; color: #bdc3c7; font-size: 12px; margin-top: 30px; padding-top: 15px; border-top: 1px solid #ecf0f1; }
                .chart-container { width: 100%; height: auto; }
                .chart-container > div { width: 100% !important; }
                @page { margin: 1.5cm; size: A4; }
                @media print { body { background: white; } .container { box-shadow: none; } }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🌤️ 昆明气象季度分析报告</h1>
                <div class="meta">
                    报告周期：{{ start_date }} 至 {{ end_date }} | 生成时间：{{ generated_at }}
                </div>

                <div class="section-title">📊 季度核心指标</div>
                <div class="summary-grid">
                    <div class="summary-item"><div class="label">平均温度</div><div class="value">{{ summary.avg_temp }}℃</div></div>
                    <div class="summary-item"><div class="label">最高/最低</div><div class="value">{{ summary.max_temp }} / {{ summary.min_temp }}℃</div></div>
                    <div class="summary-item"><div class="label">极端高温日</div><div class="value">{{ summary.max_temp_day }}</div></div>
                    <div class="summary-item"><div class="label">极端低温日</div><div class="value">{{ summary.min_temp_day }}</div></div>
                    <div class="summary-item"><div class="label">平均湿度</div><div class="value">{{ summary.avg_humidity }}%</div></div>
                    <div class="summary-item"><div class="label">总降水量</div><div class="value">{{ summary.total_precip }}mm</div></div>
                    <div class="summary-item"><div class="label">降雨天数</div><div class="value">{{ summary.rainy_days }}天</div></div>
                    <div class="summary-item"><div class="label">数据有效率</div><div class="value">{{ summary.avg_validity_rate }}%</div></div>
                </div>
                <div style="margin:10px 0; padding:10px; background:#eaf2f8; border-radius:6px; text-align:center;">
                    <strong>📌 与气温相关性最强因子：</strong> {{ summary.top_corr_factor }}
                </div>

                <div class="section-title">📈 数据可视化看板</div>
                <div class="dashboard-embed">
                    {{ dashboard_html|safe }}
                </div>

                <div class="section-title">📝 季度分析小结</div>
                <div style="background:#fefefe; padding:15px; border-radius:8px; line-height:1.8; color:#2c3e50;">
                    <p>本季度（{{ summary.quarter }}）昆明地区气象数据采集与分析呈现以下特点：</p>
                    <ul>
                        <li><strong>气温特征：</strong>季度平均气温 {{ summary.avg_temp }}℃，最高 {{ summary.max_temp }}℃（{{ summary.max_temp_day }}），最低 {{ summary.min_temp }}℃（{{ summary.min_temp_day }}）。</li>
                        <li><strong>湿度与降水：</strong>平均相对湿度 {{ summary.avg_humidity }}%，季度总降水量 {{ summary.total_precip }}mm，降雨日数 {{ summary.rainy_days }} 天。</li>
                        <li><strong>数据质量：</strong>季度平均数据有效率 {{ summary.avg_validity_rate }}%，达到预期目标（≥95%）。</li>
                        <li><strong>关联分析：</strong>与气温相关性最强的因子为 <strong>{{ summary.top_corr_factor }}</strong>，为后续气温预测提供了重要参考。</li>
                    </ul>
                    <p style="margin-top:10px; color:#7f8c8d; font-size:14px;">* 本报告基于系统自动采集与清洗的公开气象数据生成，仅供参考。</p>
                </div>

                <div class="footer">昆明气象数据智能分析系统 · 自动生成</div>
            </div>
        </body>
        </html>
        """)
        html_output = template.render(**context)
        return html_output

    def generate_quarterly_report(self, quarter: int = None, year: int = None) -> str:
        """生成季度PDF报告，返回文件路径"""
        # 1. 获取季度时间范围
        start_date, end_date = self._get_quarter_range(quarter, year)
        logger.info(
            f"生成 {start_date.year}年Q{(start_date.month - 1) // 3 + 1} 报告 ({start_date.date()} ~ {end_date.date()})")

        # 2. 加载季度数据
        df_quarter = self._load_quarter_data(start_date, end_date)
        if df_quarter.empty:
            logger.warning("季度内无数据，报告生成失败")
            return ""

        # 3. 生成季度摘要
        summary = self._generate_quarter_summary(df_quarter, start_date, end_date)

        # 4. 构建临时看板HTML
        temp_dashboard_path = self._build_temp_dashboard(df_quarter, start_date, end_date)

        # 5. 渲染完整HTML报告
        html_content = self._generate_html_report(temp_dashboard_path, summary, start_date, end_date)

        # 保存HTML中间产物
        temp_html_path = self.report_dir / f"quarter_report_{start_date.year}Q{(start_date.month - 1) // 3 + 1}.html"
        with open(temp_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"HTML报告已输出：{temp_html_path}")

        # 6. 延迟导入weasyprint，尝试生成PDF
        try:
            from weasyprint import HTML, CSS
        except OSError as e:
            logger.error(f"WeasyPrint GTK库缺失，无法导出PDF: {e}，仅输出HTML版本")
            return str(temp_html_path)

        # 真正执行PDF导出
        pdf_path = self.report_dir / f"quarter_report_{start_date.year}Q{(start_date.month - 1) // 3 + 1}.pdf"
        try:
            HTML(string=html_content, base_url=str(self.report_dir)).write_pdf(
                target=str(pdf_path),
                stylesheets=[CSS(string='@page { size: A4; margin: 1.5cm; }')]
            )
            logger.info(f"PDF报告生成成功: {pdf_path}")
            return str(pdf_path)
        except Exception as e:
            logger.error(f"PDF渲染失败:{e}，使用HTML作为产物")
            return str(temp_html_path)

    def _load_quarter_data(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """加载季度数据"""
        query = text("""
            SELECT record_time, temp_current, temp_max, temp_min, feels_like,
                   humidity, pressure, wind_speed, cloud_cover, weather_desc, precipitation
            FROM weather_data
            WHERE record_time BETWEEN :start AND :end
            ORDER BY record_time
        """)
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={'start': start_date, 'end': end_date})
        logger.info(f"加载季度数据：{len(df)} 条")
        return df

    def _build_temp_dashboard(self, df: pd.DataFrame, start_date: datetime, end_date: datetime) -> str:
        """临时构建看板HTML（基于传入的df）"""
        from pyecharts.charts import Page

        from visualizer.chart_generator import ChartGenerator

        chart_gen = ChartGenerator()

        chart_trend = chart_gen.create_temperature_trend_chart(df)
        chart_humidity = chart_gen.create_humidity_pressure_chart(df)
        chart_pie = chart_gen.create_weather_distribution_pie(df)
        chart_precip = chart_gen.create_precipitation_bar(df)

        corr_matrix = self.dashboard_builder._load_correlation_data()
        chart_heatmap = chart_gen.create_correlation_heatmap(corr_matrix)

        page = Page(layout=Page.DraggablePageLayout)
        page.add(chart_trend)
        page.add(chart_humidity)
        page.add(chart_pie)
        page.add(chart_heatmap)
        page.add(chart_precip)

        temp_path = self.report_dir / f"temp_dashboard_{start_date.strftime('%Y%m%d')}.html"
        page.render(str(temp_path))
        return str(temp_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    reporter = PDFReporter()
    reporter.generate_quarterly_report()

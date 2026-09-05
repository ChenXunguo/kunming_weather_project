import pandas as pd
import numpy as np
from pyecharts.charts import Line, Bar, Pie, HeatMap, Scatter, Grid, Tab, Page
from pyecharts import options as opts
from pyecharts.globals import ThemeType, CurrentConfig
from pyecharts.components import Table
from pyecharts.commons.utils import JsCode
from datetime import datetime, timedelta
import logging
from pathlib import Path

# 设置 Pyecharts 默认主题和语言
CurrentConfig.ONLINE_HOST = "https://cdn.jsdelivr.net/npm/echarts@5/dist/"

logger = logging.getLogger(__name__)


class ChartGenerator:
    """Pyecharts 图表生成器"""

    # 昆明常用颜色主题
    COLORS = ['#5470C6', '#91CC75', '#FAC858', '#EE6666', '#73C0DE', '#3BA272', '#FC8452']

    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / 'reports' / 'figures'
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_temperature_trend_chart(self, df: pd.DataFrame,
                                       title: str = "昆明气温变化趋势") -> Line:
        """
        创建气温趋势折线图（含最高/最低/体感温度）
        """
        if df.empty:
            return Line().set_global_opts(title_opts=opts.TitleOpts(title="暂无数据"))

        # 确保按时间排序
        df = df.sort_values('record_time')
        # 取最近30天数据（如数据量过大可采样）
        if len(df) > 500:
            df = df.iloc[-500:]

        x_data = df['record_time'].dt.strftime('%m-%d %H:%M').tolist()

        line = Line(init_opts=opts.InitOpts(theme=ThemeType.LIGHT, width="100%", height="400px"))

        # 当前温度
        if 'temp_current' in df.columns:
            line.add_xaxis(x_data)
            line.add_yaxis("当前温度", df['temp_current'].round(1).tolist(),
                           linestyle_opts=opts.LineStyleOpts(width=2),
                           label_opts=opts.LabelOpts(is_show=False),
                           symbol="circle", symbol_size=4)

        # 最高温度
        if 'temp_max' in df.columns:
            line.add_yaxis("最高温度", df['temp_max'].round(1).tolist(),
                           linestyle_opts=opts.LineStyleOpts(width=1.5, type_='dashed'),
                           label_opts=opts.LabelOpts(is_show=False),
                           symbol="diamond", symbol_size=4)

        # 最低温度
        if 'temp_min' in df.columns:
            line.add_yaxis("最低温度", df['temp_min'].round(1).tolist(),
                           linestyle_opts=opts.LineStyleOpts(width=1.5, type_='dotted'),
                           label_opts=opts.LabelOpts(is_show=False),
                           symbol="triangle", symbol_size=4)

        # 体感温度
        if 'feels_like' in df.columns:
            line.add_yaxis("体感温度", df['feels_like'].round(1).tolist(),
                           linestyle_opts=opts.LineStyleOpts(width=2, type_='dashed'),
                           label_opts=opts.LabelOpts(is_show=False),
                           symbol="rect", symbol_size=4)

        line.set_global_opts(
            title_opts=opts.TitleOpts(title=title, pos_left="center"),
            tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),
            legend_opts=opts.LegendOpts(pos_top="10%", pos_left="center"),
            xaxis_opts=opts.AxisOpts(
                name="时间",
                axislabel_opts=opts.LabelOpts(rotate=30, interval=10),
                splitline_opts=opts.SplitLineOpts(is_show=False)
            ),
            yaxis_opts=opts.AxisOpts(
                name="温度 (℃)",
                splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(type_='dashed'))
            ),
            datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100),
            visualmap_opts=opts.VisualMapOpts(
                is_show=False,
                dimension=0,
                min_=df['temp_current'].min() if 'temp_current' in df.columns else -5,
                max_=df['temp_current'].max() if 'temp_current' in df.columns else 35,
                range_color=['#313695', '#4575b4', '#74add1', '#abd9e9', '#e0f3f8',
                             '#ffffbf', '#fee090', '#fdae61', '#f46d43', '#d73027']
            )
        )
        return line

    def create_humidity_pressure_chart(self, df):
        from pyecharts import options as opts
        from pyecharts.charts import Line

        if df.empty:
            return Line()

        x_data = df["record_time"].dt.strftime("%m‑%d").tolist()
        humi_data = df["humidity"].tolist()
        press_data = df["pressure"].tolist()

        line = Line()
        line.add_xaxis(x_data)

        # 主Y轴 index=0 湿度（左侧）
        line.add_yaxis(
            series_name="湿度",
            y_axis=humi_data,
            yaxis_index=0,
        )
        # 副Y轴 index=1 气压（右侧）
        line.add_yaxis(
            series_name="气压",
            y_axis=press_data,
            yaxis_index=1,
        )

        # 扩展第二个Y轴，不要写进set_global_opts
        line.extend_axis(
            yaxis=opts.AxisOpts(
                name="气压",
                position="right",
            )
        )

        line.set_global_opts(
            title_opts=opts.TitleOpts(title="湿度与气压变化趋势", pos_left="center"),
            yaxis_opts=opts.AxisOpts(name="湿度"),
            datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100),
        )
        return line

    def create_weather_distribution_pie(self, df: pd.DataFrame) -> Pie:
        """
        创建天气状况分布饼图（按天气描述分类）
        """
        if df.empty or 'weather_desc' not in df.columns:
            return Pie().set_global_opts(title_opts=opts.TitleOpts(title="暂无天气分类数据"))

        # 统计各天气描述出现次数
        weather_counts = df['weather_desc'].value_counts().head(8)
        if weather_counts.empty:
            return Pie()

        # 如果类别太多，将其他合并
        if len(weather_counts) > 8:
            others_sum = weather_counts.iloc[8:].sum()
            weather_counts = weather_counts.iloc[:8]
            weather_counts['其他'] = others_sum

        # 生成颜色
        colors = ['#5470C6', '#91CC75', '#FAC858', '#EE6666', '#73C0DE', '#3BA272', '#FC8452', '#9A60B4', '#EA7CCC']

        pie = Pie(init_opts=opts.InitOpts(theme=ThemeType.LIGHT, width="100%", height="350px"))
        pie.add(
            series_name="天气分布",
            data_pair=[(k, int(v)) for k, v in weather_counts.items()],
            radius=["40%", "70%"],
            center=["50%", "50%"],
            label_opts=opts.LabelOpts(
                formatter="{b}: {d}%",
                font_size=12
            ),
            itemstyle_opts=opts.ItemStyleOpts(
                border_width=2,
                border_color='#ffffff'
            )
        )
        pie.set_colors(colors)
        pie.set_global_opts(
            title_opts=opts.TitleOpts(title="天气状况分布", pos_left="center"),
            legend_opts=opts.LegendOpts(pos_top="10%", pos_left="center", orient="horizontal"),
            tooltip_opts=opts.TooltipOpts(
                trigger="item",
                formatter="{a} <br/>{b}: {c}次 ({d}%)"
            )
        )
        return pie

    def create_correlation_heatmap(self, corr_df: pd.DataFrame) -> HeatMap:
        """
        创建相关性热力图（基于阶段四的相关系数矩阵）
        """
        if corr_df.empty:
            return HeatMap().set_global_opts(title_opts=opts.TitleOpts(title="暂无相关性数据"))

        # 获取变量名列表
        variables = corr_df.index.tolist()
        # 转换为 HeatMap 所需格式: [[x_index, y_index, value], ...]
        data = []
        for i, var_x in enumerate(variables):
            for j, var_y in enumerate(variables):
                if i != j:
                    val = corr_df.loc[var_x, var_y]
                    if not pd.isna(val):
                        data.append([j, i, round(val, 3)])  # 注意pyecharts heatmap坐标顺序

        # 添加对角线（灰色）
        for i, var in enumerate(variables):
            data.append([i, i, 1.0])

        heatmap = HeatMap(init_opts=opts.InitOpts(theme=ThemeType.LIGHT, width="100%", height="450px"))
        heatmap.add_xaxis(variables)
        heatmap.add_yaxis(
            series_name="相关系数",
            yaxis_data=variables,
            value=data,
            label_opts=opts.LabelOpts(
                is_show=True,
                formatter=JsCode("function(params){return params.value[2] ? params.value[2].toFixed(2) : '';}"),
                font_size=10
            )
        )

        heatmap.set_global_opts(
            title_opts=opts.TitleOpts(title="气象变量相关性热力图", pos_left="center"),
            tooltip_opts=opts.TooltipOpts(
                formatter=JsCode("""
                    function(params) {
                        return params.value[1] + ' 与 ' + params.value[0] + '<br/>相关系数: ' + params.value[2];
                    }
                """)
            ),
            xaxis_opts=opts.AxisOpts(
                axislabel_opts=opts.LabelOpts(rotate=30, font_size=11),
                splitarea_opts=opts.SplitAreaOpts(is_show=True)
            ),
            yaxis_opts=opts.AxisOpts(
                axislabel_opts=opts.LabelOpts(font_size=11),
                splitarea_opts=opts.SplitAreaOpts(is_show=True)
            ),
            visualmap_opts=opts.VisualMapOpts(
                min_=-1,
                max_=1,
                range_color=['#313695', '#4575b4', '#74add1', '#abd9e9',
                             '#ffffbf', '#fee090', '#fdae61', '#f46d43', '#d73027'],
                is_calculable=True,
                orient='horizontal',
                pos_left='center',
                pos_bottom='5%'
            )
        )
        return heatmap

    def create_precipitation_bar(self, df: pd.DataFrame) -> Bar:
        """
        创建日降水量柱状图（按天聚合）
        """
        if df.empty or 'precipitation' not in df.columns:
            return Bar().set_global_opts(title_opts=opts.TitleOpts(title="暂无降水数据"))

        # 按天聚合
        df['date'] = df['record_time'].dt.date
        daily_precip = df.groupby('date')['precipitation'].sum().reset_index()
        daily_precip = daily_precip.sort_values('date').tail(30)  # 最近30天

        if daily_precip.empty:
            return Bar()

        bar = Bar(init_opts=opts.InitOpts(theme=ThemeType.LIGHT, width="100%", height="300px"))
        bar.add_xaxis(daily_precip['date'].astype(str).tolist())
        bar.add_yaxis(
            "日降水量 (mm)",
            daily_precip['precipitation'].round(2).tolist(),
            bar_width="50%",
            itemstyle_opts=opts.ItemStyleOpts(color='#5470C6', border_radius=[4, 4, 0, 0]),
            label_opts=opts.LabelOpts(is_show=True, position='top', formatter='{c}mm')
        )
        bar.set_global_opts(
            title_opts=opts.TitleOpts(title="最近30天日降水量", pos_left="center"),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
            xaxis_opts=opts.AxisOpts(
                axislabel_opts=opts.LabelOpts(rotate=30, interval=2)
            ),
            yaxis_opts=opts.AxisOpts(name="降水量 (mm)"),
            datazoom_opts=opts.DataZoomOpts(range_start=0, range_end=100)
        )
        return bar

    def create_prediction_vs_actual_chart(self, df_actual: pd.DataFrame,
                                          df_pred: pd.DataFrame) -> Line:
        """
        创建预测值与实际值对比图（用于模型效果展示）
        """
        if df_actual.empty:
            return Line().set_global_opts(title_opts=opts.TitleOpts(title="暂无预测数据"))

        # 取最近7天实际值和对应的预测值（需从 analysis_results 关联）
        # 简化版：使用实际温度曲线 + 标注预测点
        df_actual = df_actual.sort_values('record_time').tail(50)

        line = Line(init_opts=opts.InitOpts(theme=ThemeType.LIGHT, width="100%", height="300px"))
        x_data = df_actual['record_time'].dt.strftime('%m-%d %H:%M').tolist()
        line.add_xaxis(x_data)

        if 'temp_current' in df_actual.columns:
            line.add_yaxis("实际温度", df_actual['temp_current'].round(1).tolist(),
                           linestyle_opts=opts.LineStyleOpts(width=2, color='#5470C6'),
                           label_opts=opts.LabelOpts(is_show=False),
                           symbol="circle", symbol_size=4)

        # 如果有预测值且与时间匹配，添加散点
        if not df_pred.empty and 'prediction_time' in df_pred.columns:
            pred_times = df_pred['prediction_time'].dt.strftime('%m-%d %H:%M').tolist()
            pred_vals = df_pred['predicted_temp'].round(1).tolist()
            line.add_yaxis("预测值",
                           [None] * len(x_data),  # 占位，用 markpoint 或单独处理
                           label_opts=opts.LabelOpts(is_show=False))
            # 使用 markpoint 标记预测点（实际项目中可通过 markpoint 实现）

        line.set_global_opts(
            title_opts=opts.TitleOpts(title="温度预测 vs 实际（近期）", pos_left="center"),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
            legend_opts=opts.LegendOpts(pos_top="10%", pos_left="center"),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=30, interval=5)),
            yaxis_opts=opts.AxisOpts(name="温度 (℃)")
        )
        return line
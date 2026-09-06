# 昆明气象数据智能分析系统

一个端到端的气象数据采集、清洗、分析、可视化与告警系统。自动从 OpenWeatherMap 采集昆明实况与 5 天预报数据，经质量清洗后入库，并周期性完成相关性分析、6 小时气温预测模型训练、数据看板与季度报告生成；内置健康检查、业务监控与多通道告警。

## 功能总览



| 模块                | 能力                                                           |
| ----------------- | ------------------------------------------------------------ |
| 采集 `collector/`   | OpenWeatherMap 实况 + 5 天预报，自动重试（超时 / 429/5xx），批量查重入库          |
| 清洗 `processor/`   | 3σ 异常值修正、缺失值线性插值填补、业务合理性校验、每日质量日志                            |
| 分析 `analyzer/`    | 气象变量相关性矩阵、随机森林 / 线性回归 6h 气温预测、结果入库                           |
| 可视化 `visualizer/` | Pyecharts 数据看板（趋势 / 湿度气压 / 天气分布 / 相关性热力 / 降水）、季度 HTML/PDF 报告 |
| 调度 `scheduler/`   | croniter 驱动 cron 表达式调度，依赖检查 + 失败重试 + 线程池                     |
| 监控 `monitor/`     | 健康检查（DB / 数据新鲜度 / 磁盘）、HTTP 监控中心（:8899）、业务指标                  |
| 告警 `alert/`       | 邮件 / 企业微信 / 钉钉多通道通知                                          |

## 目录结构



```
├── main.py                 # 系统入口（日志、健康检查、监控服务、调度器、首次采集）

├── config/config.py        # 配置加载（.env）与校验

├── collector/              # 数据采集（OpenWeatherClient + WeatherCollector）

├── processor/              # 数据清洗与质量报告

├── analyzer/               # 相关性分析 + 特征工程 + 预测模型

├── visualizer/             # 图表、看板、PDF 报告生成

├── scheduler/              # cron 任务调度与线程池

├── monitor/                # 健康检查与 HTTP 监控

├── alert/                  # 告警管理器与通知器

├── database/schema.sql     # 建表脚本（v2.1，与代码字段完全对齐）

├── scripts/                # 运维脚本（迁移、回填清洗、报告生成、模型检查）

├── deploy/                 # Docker / systemd 部署文件

├── reports/                # 生成的看板、图表、报告

├── models/ model\\\_cache/    # 训练好的模型与 Scaler（pkl）

└── logs/                   # 运行日志（按天轮转，保留30天）
```

## 快速开始

### 1. 环境准备（Python 3.10+）



```
python -m venv .venv

\\# Windows

.venv\Scripts\activate

\\# Linux/macOS

source .venv/bin/activate

pip install -r requirements.txt
```

### 2. 配置 .env

复制项目根目录 `.env` 并按需修改：



```
\\# 必填

OPENWEATHER\\\_API\\\_KEY=你的OpenWeatherMap密钥

DB\\\_PASSWORD=数据库密码

\\# 可选

DB\\\_HOST=localhost

DB\\\_PORT=3306

DB\\\_USER=root

DB\\\_NAME=kunming\\\_weather

COLLECT\\\_INTERVAL=6          # 采集间隔（小时），模型训练建议 3\\\~6

MONITOR\\\_API\\\_TOKEN=          # 设置后 /trigger 接口需携带 X-API-Token 头

COLLECT\\\_ON\\\_STARTUP=true     # 启动时立即采集一次
```

> 告警通道（邮件 / 企微 / 钉钉）默认关闭，按需在 .env 中启用。

### 3. 初始化数据库



```
\\# 方式一：直接导入建表脚本

mysql -uroot -p < database/schema.sql

\\# 方式二：从旧版本库升级（幂等，可重复执行）

python scripts/migrate\\\_db.py
```

### 4. 启动系统



```
python main.py
```

启动后：



* 立即执行一次采集，之后按 cron 调度：采集每 6 小时整点、清洗延后 10 分钟、每日 02:00 分析、季末 28 日 03:00 生成季度报告；

* HTTP 监控中心：[http://localhost:8899](http://localhost:8899) （`/health`、`/metrics/summary`、`/ready` 及对应可视化页面）；

* 通过 `/trigger/<任务名>` 可手动触发任务（需 `X-API-Token` 请求头）。

## 常用脚本



```
python scripts/run\\\_analysis.py        # 手动执行一次完整分析（相关性+训练+预测）

python scripts/generate\\\_report.py     # 生成看板/季度报告（--type dashboard|quarterly|both）

python scripts/check\\\_quality.py       # 检查模型性能与最新相关性

python scripts/backfill\\\_clean.py      # 回填清洗最近N天历史数据

python scripts/migrate\\\_db.py          # 数据库结构迁移（旧库→v2.1）
```

## 调度任务



| 任务              | cron                | 说明                    |
| --------------- | ------------------- | --------------------- |
| collect         | `0 */6 * * *`       | 采集实况 + 预报，失败重试 2 次    |
| clean           | `10 */6 * * *`      | 清洗最近 24h 数据，有效率低于阈值告警 |
| analysis        | `0 2 * * *`         | 相关性分析 + 模型训练 + 6h 预测  |
| quarter\_report | `0 3 28 3,6,9,12 *` | 季度报告生成                |

模型训练需要 ≥30 条实况数据（`data_type=1`）；以 6 小时间隔采集约 7.5 天可自动开始训练。

## 技术栈

Python・Requests・Pandas/NumPy・SQLAlchemy + PyMySQL・scikit-learn・Pyecharts・Matplotlib/Seaborn・Flask + Waitress・croniter・Loguru・WeasyPrint（可选，缺 GTK 时自动降级输出 HTML）

## 部署



* Docker：`docker compose -f deploy/docker/docker-compose.yml up -d`（首次启动自动执行 schema.sql 初始化）

* systemd：参考 `deploy/systemd/weather.service`（Linux 环境）

## 已知说明



* OpenWeatherMap 免费接口不保证返回降水字段，`precipitation` 可能为空（看板中显示 0 属正常）；

* WeasyPrint 在 Windows 需 GTK 运行库，缺失时季度报告自动输出 HTML 版本；

* 密钥仅存于 `.env`（已 gitignore）

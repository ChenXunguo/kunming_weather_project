from flask import Flask, jsonify, request
import threading
import logging
from waitress import serve
from monitor.health_check import HealthChecker
from monitor.metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)


class HttpMonitorServer:
    def __init__(self, monitor_config: dict):
        self.monitor_config = monitor_config
        self.host = monitor_config["health_check_host"]
        self.port = monitor_config["health_check_port"]
        self.app = Flask(__name__)
        # 生产环境强制关闭调试
        self.app.config["DEBUG"] = False
        self.app.config["TESTING"] = False
        self.health_checker = HealthChecker()
        self.metrics_collector = MetricsCollector()
        self._register_routes()
        self.server_thread = None

    def _register_routes(self):
        @self.app.route("/")
        def index():
            return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>气象系统监控中心</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Microsoft YaHei", sans-serif;
            max-width: 640px;
            margin: 80px auto;
            padding: 0 24px;
            color: #2c3e50;
            background: #f8fafc;
        }
        h1 {
            font-size: 24px;
            margin-bottom: 32px;
            padding-bottom: 12px;
            border-bottom: 3px solid #3b82f6;
        }
        .card {
            background: #ffffff;
            border-radius: 8px;
            padding: 18px 20px;
            margin-bottom: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }
        .card a {
            color: #3b82f6;
            text-decoration: none;
            font-size: 16px;
            font-weight: 500;
        }
        .card a:hover {
            text-decoration: underline;
        }
        .desc {
            font-size: 13px;
            color: #64748b;
            margin-top: 6px;
        }
        .api-card {
            background: #f1f5f9;
        }
    </style>
</head>
<body>
    <h1>昆明气象数据智能分析系统 · 监控中心</h1>

    <div class="card">
        <a href="/health/view">/health 健康检查</a>
        <div class="desc">图形化展示数据库连通性、数据新鲜度、磁盘使用率三项健康状态</div>
    </div>

    <div class="card">
        <a href="/metrics/summary/view">/metrics/summary 业务指标</a>
        <div class="desc">图形化展示数据总记录数、首尾时间、最近更新时间等业务统计</div>
    </div>

    <div class="card">
        <a href="/ready/view">/ready 服务就绪</a>
        <div class="desc">图形化展示服务存活与就绪状态</div>
    </div>

    <div class="card api-card">
        <a href="/health">/health 原始JSON接口</a>
        <div class="desc">供监控脚本、API 调用使用的纯数据接口</div>
    </div>

    <div class="card api-card">
        <a href="/metrics/summary">/metrics/summary 原始JSON接口</a>
        <div class="desc">供监控脚本、API 调用使用的纯数据接口</div>
    </div>

    <div class="card api-card">
        <a href="/ready">/ready 原始JSON接口</a>
        <div class="desc">供监控脚本、API 调用使用的纯数据接口</div>
    </div>
</body>
</html>
            """

        @self.app.route("/health/view")
        def health_view():
            report = self.health_checker.full_health_check()
            status = report.get("status", "UNKNOWN")
            checks = report.get("checks", {})
            timestamp = report.get("timestamp", "")

            status_color = "#10b981" if status == "HEALTHY" else "#ef4444"
            status_text = "系统健康" if status == "HEALTHY" else "系统异常"

            check_items = ""
            label_map = {
                "database": "数据库连通性",
                "data_freshness": "数据新鲜度",
                "disk_usage": "磁盘使用率"
            }
            for key, value in checks.items():
                label = label_map.get(key, key)
                dot_color = "#10b981" if value else "#ef4444"
                status_text_item = "正常" if value else "异常"
                check_items += f"""
                <div class="check-item">
                    <span class="dot" style="background:{dot_color}"></span>
                    <span class="check-label">{label}</span>
                    <span class="check-status">{status_text_item}</span>
                </div>
                """

            return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>系统健康状态</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Microsoft YaHei", sans-serif;
            max-width: 600px;
            margin: 80px auto;
            padding: 0 24px;
            color: #2c3e50;
            background: #f8fafc;
        }}
        .status-card {{
            background: #fff;
            border-radius: 12px;
            padding: 32px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            text-align: center;
            margin-bottom: 24px;
        }}
        .status-badge {{
            display: inline-block;
            padding: 6px 18px;
            border-radius: 20px;
            color: #fff;
            font-size: 14px;
            font-weight: 500;
            background: {status_color};
            margin-bottom: 16px;
        }}
        .status-title {{
            font-size: 28px;
            font-weight: 600;
            margin-bottom: 8px;
        }}
        .timestamp {{
            font-size: 13px;
            color: #94a3b8;
        }}
        .check-list {{
            background: #fff;
            border-radius: 12px;
            padding: 8px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        .check-item {{
            display: flex;
            align-items: center;
            padding: 14px 24px;
            border-bottom: 1px solid #f1f5f9;
        }}
        .check-item:last-child {{ border-bottom: none; }}
        .dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 12px;
        }}
        .check-label {{
            flex: 1;
            font-size: 15px;
        }}
        .check-status {{
            font-size: 14px;
            color: #64748b;
        }}
        .back {{
            display: block;
            text-align: center;
            margin-top: 20px;
            color: #3b82f6;
            text-decoration: none;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="status-card">
        <div class="status-badge">{status_text}</div>
        <div class="status-title">{status}</div>
        <div class="timestamp">检测时间：{timestamp}</div>
    </div>

    <div class="check-list">
        {check_items}
    </div>

    <a href="/" class="back">← 返回监控首页</a>
</body>
</html>
            """

        @self.app.route("/metrics/summary/view")
        def metrics_summary_view():
            summary = self.metrics_collector.get_system_summary()
            first_record = str(summary.get("first_record", "-"))
            last_record = str(summary.get("last_record", "-"))
            last_update = str(summary.get("last_update", "-"))
            total_records = summary.get("total_records", 0)

            return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>业务指标概览</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Microsoft YaHei", sans-serif;
            max-width: 600px;
            margin: 80px auto;
            padding: 0 24px;
            color: #2c3e50;
            background: #f8fafc;
        }}
        .page-title {{
            font-size: 22px;
            margin-bottom: 24px;
            padding-bottom: 10px;
            border-bottom: 3px solid #3b82f6;
        }}
        .metric-card {{
            background: #fff;
            border-radius: 12px;
            padding: 20px 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            margin-bottom: 16px;
        }}
        .metric-label {{
            font-size: 13px;
            color: #64748b;
            margin-bottom: 6px;
        }}
        .metric-value {{
            font-size: 22px;
            font-weight: 600;
            color: #1e293b;
        }}
        .metric-value.big {{
            font-size: 32px;
            color: #3b82f6;
        }}
        .back {{
            display: block;
            text-align: center;
            margin-top: 20px;
            color: #3b82f6;
            text-decoration: none;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="page-title">业务指标概览</div>

    <div class="metric-card">
        <div class="metric-label">数据总记录数</div>
        <div class="metric-value big">{total_records} 条</div>
    </div>

    <div class="metric-card">
        <div class="metric-label">最早一条记录时间</div>
        <div class="metric-value">{first_record}</div>
    </div>

    <div class="metric-card">
        <div class="metric-label">最新一条记录时间</div>
        <div class="metric-value">{last_record}</div>
    </div>

    <div class="metric-card">
        <div class="metric-label">指标最近更新时间</div>
        <div class="metric-value">{last_update}</div>
    </div>

    <a href="/" class="back">← 返回监控首页</a>
</body>
</html>
            """

        @self.app.route("/ready/view")
        def ready_view():
            return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>服务就绪状态</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Microsoft YaHei", sans-serif;
            max-width: 600px;
            margin: 80px auto;
            padding: 0 24px;
            color: #2c3e50;
            background: #f8fafc;
            text-align: center;
        }
        .ready-card {
            background: #fff;
            border-radius: 12px;
            padding: 48px 32px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        .ready-icon {
            width: 64px;
            height: 64px;
            border-radius: 50%;
            background: #10b981;
            margin: 0 auto 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-size: 32px;
            font-weight: bold;
        }
        .ready-title {
            font-size: 28px;
            font-weight: 600;
            margin-bottom: 8px;
            color: #10b981;
        }
        .ready-desc {
            font-size: 14px;
            color: #64748b;
        }
        .back {
            display: block;
            text-align: center;
            margin-top: 24px;
            color: #3b82f6;
            text-decoration: none;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="ready-card">
        <div class="ready-icon">✓</div>
        <div class="ready-title">服务运行正常</div>
        <div class="ready-desc">监控服务已就绪，可正常接收请求</div>
    </div>

    <a href="/" class="back">← 返回监控首页</a>
</body>
</html>
            """

        # 在http_monitor.py路由函数内部追加
        @self.app.route("/trigger/<task_name>")
        def trigger_task(task_name):
            # 安全防护：未配置令牌或令牌不匹配时拒绝（避免远程无鉴权触发任务）
            token = self.monitor_config.get("api_token", "")
            if not token or request.headers.get("X-API-Token") != token:
                return jsonify({"ok": False, "error": "forbidden"}), 403
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from scheduler.task_scheduler import get_scheduler
            sched = get_scheduler()
            sched.run_task_now(task_name)
            return {"ok": True, "task": task_name}

        @self.app.route("/health")
        def health():
            report = self.health_checker.full_health_check()
            return jsonify(report)

        @self.app.route("/metrics/summary")
        def metrics_summary():
            summary = self.metrics_collector.get_system_summary()
            if summary.get("first_record"):
                summary["first_record"] = str(summary["first_record"])
            if summary.get("last_record"):
                summary["last_record"] = str(summary["last_record"])
            summary["last_update"] = str(summary["last_update"])
            return jsonify(summary)

        @self.app.route("/ready")
        def ready():
            return jsonify({"ready": True})

    def start(self):
        """使用waitress生产服务启动，不再使用app.run开发服务器"""
        def run_server():
            logger.info(f"生产HTTP监控服务启动 {self.host}:{self.port}")
            serve(self.app, host=self.host, port=self.port)

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

    def stop(self):
        logger.info("监控HTTP服务停止")

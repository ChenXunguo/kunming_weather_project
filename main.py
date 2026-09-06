#!/usr/bin/env python3
import sys
import signal
import time
import logging
import os
from pathlib import Path
from loguru import logger

# 项目根目录（以本文件位置为准，不依赖启动时的工作目录）
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
RUN_DIR = BASE_DIR / "run"

# 确保logs、run目录存在
LOG_DIR.mkdir(exist_ok=True)
RUN_DIR.mkdir(exist_ok=True)

# 配置loguru日志（控制台 + 文件按天轮转，保留30天）
logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")
logger.add(str(LOG_DIR / "weather_{time:YYYY-MM-DD}.log"),
           rotation="1 day", retention="30 days", level="DEBUG")

# 配置标准logging，让调度器模块的日志也能输出
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

from scheduler.task_scheduler import get_scheduler
from monitor.health_check import HealthChecker
from alert.alert_manager import AlertManager
from monitor.http_monitor import HttpMonitorServer
from config.config import MONITOR_CONFIG, PROD_CONFIG

# 全局调度器
scheduler = None
pid_file = Path(PROD_CONFIG["pid_path"])
if not pid_file.is_absolute():
    pid_file = BASE_DIR / pid_file


def signal_handler(sig, frame):
    logger.info("收到退出信号，正在关闭系统...")
    if scheduler:
        scheduler.stop()
    # 删除pid文件
    if pid_file.exists():
        pid_file.unlink(missing_ok=True)
    sys.exit(0)


def main():
    global scheduler
    logger.info("昆明气象数据智能分析系统启动")

    # 写入PID文件
    if PROD_CONFIG["enable_pid_file"]:
        with open(pid_file, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))

    # 启动时前置健康检查
    checker = HealthChecker()
    health = checker.full_health_check()
    logger.info(f"初始健康状态: {health['status']}")
    if health["status"] != "HEALTHY":
        AlertManager().send_alert(
            subject="系统启动健康检查警告",
            message=f"健康状态详情: {health['checks']}",
            level="WARNING"
        )

    # 启动HTTP监控服务（waitress生产服务）
    monitor_server = HttpMonitorServer(MONITOR_CONFIG)
    monitor_server.start()
    logger.info("HTTP监控服务已启动")

    # 获取调度器单例并启动
    scheduler = get_scheduler()
    scheduler.start()

    # 启动后立即执行一次采集，避免等待下一个整点（可选）
    if PROD_CONFIG.get("collect_on_startup", True):
        try:
            logger.info("启动后立即执行首次采集任务...")
            scheduler.run_task_now("collect")
        except Exception as e:
            logger.error(f"启动时首次采集失败: {e}")

    # 注册信号处理(Ctrl-C、kill终止)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 主线程阻塞等待
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()

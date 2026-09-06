# test_monitor.py
import sys
sys.path.insert(0, ".")

from monitor.health_check import HealthChecker
from monitor.metrics_collector import MetricsCollector
from monitor.http_monitor import HttpMonitorServer
from config.config import MONITOR_CONFIG

def main():
    print("===== 开始监控模块测试 =====")
    hc = HealthChecker()
    health_result = hc.full_health_check()
    print("健康检查结果：", health_result)

    mc = MetricsCollector()
    summary = mc.get_system_summary()
    print("系统指标概览：", summary)

    http_server = HttpMonitorServer(MONITOR_CONFIG)
    print("✅监控模块全部实例化完成")

if __name__ == "__main__":
    main()

import os
import sys
import time
from datetime import datetime, timedelta
from sqlalchemy import text
from config.config import DB_CONFIG
from sqlalchemy import create_engine
import logging

logger = logging.getLogger(__name__)


class HealthChecker:
    """系统健康检查"""

    def __init__(self):
        self.engine = create_engine(
            f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
            f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}",
            pool_pre_ping=True
        )

    def check_database(self) -> bool:
        """检查数据库连接"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"数据库健康检查失败: {e}")
            return False

    def check_data_freshness(self, max_hours: int = 24) -> bool:
        """检查最近数据是否新鲜（不超过max_hours）"""
        try:
            with self.engine.connect() as conn:
                # ==========修复点：把 record_time → collect_time==========
                result = conn.execute(
                    text("SELECT MAX(collect_time) FROM weather_data")
                )
                row = result.fetchone()
                if row and row[0]:
                    latest = row[0]
                    age = (datetime.now() - latest).total_seconds() / 3600
                    if age > max_hours:
                        logger.warning(f"数据陈旧: 最新记录距今 {age:.1f} 小时")
                        return False
                    return True
            # 表中暂无任何数据时返回True，避免刚启动无数据直接判定不健康
            return True
        except Exception as e:
            logger.error(f"数据新鲜度检查失败: {e}")
            return False

    def check_disk_usage(self, threshold_percent: int = 80) -> bool:
        """检查磁盘使用率（用于日志/报告目录）兼容Windows/Linux"""
        try:
            if sys.platform == "win32":
                import ctypes
                free_bytes = ctypes.c_ulonglong(0)
                total_bytes = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p("."), None, ctypes.pointer(total_bytes),
                                                           ctypes.pointer(free_bytes))
                used = total_bytes.value - free_bytes.value
                used_percent = (used / total_bytes.value) * 100
            else:
                stat = os.statvfs('.')
                total = stat.f_blocks * stat.f_frsize
                free = stat.f_bfree * stat.f_frsize
                used_percent = (1 - free / total) * 100

            if used_percent > threshold_percent:
                logger.warning(f"磁盘使用率 {used_percent:.1f}% 超过阈值")
                return False
            return True
        except Exception as e:
            logger.error(f"磁盘检查失败: {e}")
            return True

    def full_health_check(self) -> dict:
        """完整健康检查"""
        db_ok = self.check_database()
        fresh_ok = self.check_data_freshness()
        disk_ok = self.check_disk_usage()
        status = "HEALTHY" if (db_ok and fresh_ok and disk_ok) else "UNHEALTHY"
        return {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "database": db_ok,
                "data_freshness": fresh_ok,
                "disk_usage": disk_ok
            }
        }

import os
from dotenv import load_dotenv
from pathlib import Path

# __file__ = config/config.py # .parent → config文件夹 # .parent.parent → 项目根目录
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# 数据库配置
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME', 'kunming_weather'),
    'charset': 'utf8mb4'
}

# OpenWeatherMap API配置
OPENWEATHER_CONFIG = {
    'api_key': os.getenv('OPENWEATHER_API_KEY', ''),
    'city': os.getenv('CITY', 'Kunming'),
    'country': os.getenv('COUNTRY', 'CN'),
    'units': 'metric',  # metric=摄氏度, imperial=华氏度
    'lang': 'zh_cn',
    'base_url': 'https://api.openweathermap.org/data/2.5',
    'timeout': 30  # 请求超时时间（秒）
}

# 采集配置
COLLECT_CONFIG = {
    'interval_hours': int(os.getenv("COLLECT_INTERVAL", 1)),
    'retry_times': 3,
    'retry_delay': 5,
    'batch_size': 100
}


def check_config():
    """校验配置，缺失关键参数直接抛出异常，模块导入即执行"""
    if not OPENWEATHER_CONFIG["api_key"]:
        raise ValueError("❌ OPENWEATHER_API_KEY 为空，请检查项目根目录 .env 文件")

    if not DB_CONFIG["password"]:
        raise ValueError("❌ DB_PASSWORD 未配置，请检查 .env")

    if not DB_CONFIG["host"] or not DB_CONFIG["user"] or not DB_CONFIG["database"]:
        raise ValueError("❌数据库配置项缺失，请检查 .env")


# 模块被import时立刻执行校验（重要！）
check_config()

# ====================== 告警配置（完全复用你.env变量，key对齐notifiers代码） ======================
ALERT_CONFIG = {
    'enable_alert': True,
    'quality_threshold': float(os.getenv("QUALITY_THRESHOLD", 95.0)),
    'max_task_failed_count': 3,
    'email': {
        'enabled': os.getenv('ALERT_EMAIL_ENABLED', 'false').lower() == 'true',
        'smtp_host': os.getenv('SMTP_HOST', 'smtp.163.com'),
        'smtp_port': int(os.getenv('SMTP_PORT', 465)),
        'sender': os.getenv('EMAIL_SENDER', ''),
        'password': os.getenv('EMAIL_PASSWORD', ''),
        'receivers': os.getenv('EMAIL_RECEIVERS', '').split(','),
        'use_tls': True
    },
    'wechat': {
        'enabled': os.getenv('ALERT_WECHAT_ENABLED', 'false').lower() == 'true',
        'webhook_url': os.getenv('WECHAT_WEBHOOK', '')
    },
    'dingtalk': {
        'enabled': os.getenv('ALERT_DINGTALK_ENABLED', 'false').lower() == 'true',
        'webhook_url': os.getenv('DINGTALK_WEBHOOK', ''),
        'secret': os.getenv('DINGTALK_SECRET', '')
    }
}

# ====================== 阶段六新增：调度器配置 SCHEDULER_CONFIG ======================
SCHEDULER_CONFIG = {
    "collect_interval_min": COLLECT_CONFIG["interval_hours"] * 60,
    "clean_interval_min": 15,
    "analysis_interval_hour": 6,
    "report_gen_hour": 2,
    "quarter_report_day": 1,
    "worker_thread_num": 4,
    "max_task_timeout_sec": 300,
}

# ====================== 阶段六新增：监控配置 MONITOR_CONFIG ======================
MONITOR_CONFIG = {
    "health_check_host": "0.0.0.0",
    "health_check_port": 8899,
    "metrics_dump_interval_sec": 60,
}

# ====================== 生产部署配置 PROD_CONFIG 第三点优化 ======================
PROD_CONFIG = {
    "enable_pid_file": True,
    "pid_path": "./run/weather.pid",
    "max_http_workers": 4,
    "allow_debug_api": False,
    "health_check_timeout": 10
}

# 正确 pymysql 参数：server_timezone=Asia/Shanghai
DB_URL = (
    f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    f"?charset={DB_CONFIG['charset']}"
)


if __name__ == "__main__":
    print(f"正在读取 .env 文件路径：{env_path}")
    print(f".env 是否存在：{env_path.exists()}")
    print("✅配置加载完成")
    print(f"OpenWeather API Key: {OPENWEATHER_CONFIG['api_key'][:8]}******")
    print(f"DB target: {DB_CONFIG['host']}/{DB_CONFIG['database']}")
    print(f"SCHEDULER_CONFIG: {SCHEDULER_CONFIG}")
    print(f"ALERT_CONFIG quality_threshold: {ALERT_CONFIG['quality_threshold']}")

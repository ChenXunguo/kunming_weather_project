import os

# 定义所有路径
structure = [
    "config/config.py",
    "config/__init__.py",
    "database/schema.sql",
    "database/db_connection.py",
    "database/__init__.py",
    "collector/weather_collector.py",
    "collector/__init__.py",
    "processor/data_cleaner.py",
    "processor/__init__.py",
    "analyzer/correlation_analyzer.py",
    "analyzer/__init__.py",
    "visualizer/chart_generator.py",
    "visualizer/__init__.py",
    "scheduler/task_scheduler.py",
    "scheduler/__init__.py",
    "reports/report_generator.py",
    "reports/__init__.py",
    "logs/",
    "main.py",
    "requirements.txt",
]

for path in structure:
    if path.endswith("/"):
        os.makedirs(path, exist_ok=True)
    else:
        dir_name = os.path.dirname(path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)
        # 创建空文件
        with open(path, "a", encoding="utf-8") as f:
            pass

print("✅ 项目目录结构全部创建完成！")

import schedule
import time
import logging
import threading
from datetime import datetime
from croniter import croniter
from scheduler.task_registry import TaskRegistry
from scheduler.worker_pool import WorkerPool
from alert.alert_manager import AlertManager
from collector.weather_collector import WeatherCollector
from processor.data_cleaner import WeatherDataCleaner
from analyzer.analysis_runner import AnalysisRunner
from visualizer.pdf_reporter import PDFReporter

logger = logging.getLogger(__name__)


def register_all_tasks():
    """注册所有任务"""
    # 采集任务
    def collect_job():
        collector = WeatherCollector()
        result = collector.collect()
        return result

    TaskRegistry.register(
        name="collect",
        func=collect_job,
        schedule_expr="0 */6 * * *",  # ✅ 每6小时整点执行，不是6分钟
        retries=2,
        timeout=180
    )

    # 清洗任务（依赖采集）
    def clean_job():
        cleaner = WeatherDataCleaner()
        stats = cleaner.clean_recent_records(hours=24)
        # 检查有效率并告警
        if stats.get('validity_rate', 0) < 95:
            AlertManager().alert_quality_issue(
                date=datetime.now().strftime('%Y-%m-%d'),
                validity_rate=stats['validity_rate']
            )
        return stats

    TaskRegistry.register(
        name="clean",   # ✅修复：任务名改为 clean
        func=clean_job,
        schedule_expr="10 */6 * * *",  # 采集完成后10分钟执行清洗
        depends_on=["collect"],
        retries=2,
        timeout=180
    )

    # 分析任务（每日凌晨）
    def analysis_job():
        runner = AnalysisRunner()
        runner.run_daily_analysis()
        return "analysis done"

    TaskRegistry.register(
        name="analysis",
        func=analysis_job,
        schedule_expr="0 2 * * *",  # 每天2点
        depends_on=["clean"],
        retries=1
    )

    # 季度报告（季末28号）
    def quarter_report_job():
        reporter = PDFReporter()
        path = reporter.generate_quarterly_report()
        return path

    TaskRegistry.register(
        name="quarter_report",
        func=quarter_report_job,
        schedule_expr="0 3 28 3,6,9,12 *",  # 3,6,9,12月28日3点
        depends_on=["analysis"],
        retries=0
    )



class UnifiedScheduler:
    """统一调度器"""

    def __init__(self):
        self.worker_pool = WorkerPool(max_workers=2)
        self.alert_manager = AlertManager()
        self.running = False
        self.thread = None
        self.cron_tasks = []  # 存储复杂cron表达式调度的任务
        # 实例化即自动注册全部业务任务
        register_all_tasks()

    def _schedule_task(self, name: str, task_info: dict):
        """为单个任务设置schedule【修复完整版】"""
        expr = task_info['schedule_expr']
        if not expr:
            return

        parts = expr.split()
        if len(parts) != 5:
            logger.warning(f"cron表达式格式错误 {expr}，任务 {name} 仅支持手动触发")
            return

        minute, hour, day, month, wday = parts

        # case1: */6 * * * * 每N分钟 / 每N小时
        if minute.startswith("*/") and hour == "*" and day == "*" and month == "*" and wday == "*":
            n = int(minute.replace("*/",""))
            if n % 60 == 0:
                hours = n // 60
                schedule.every(hours).hours.do(self._run_task, name)
                logger.info(f"任务 {name} 设置为每 {hours} 小时执行")
            else:
                schedule.every(n).minutes.do(self._run_task, name)
                logger.info(f"任务 {name} 设置为每 {n} 分钟执行")
            return

        # case2: 0 */6 * * * → 每6小时，第0分执行
        if minute == "0" and hour.startswith("*/") and day == "*" and month == "*" and wday == "*":
            n_hour = int(hour.replace("*/",""))
            schedule.every(n_hour).hours.do(self._run_task, name)
            logger.info(f"任务 {name} 设置每 {n_hour} 小时(0分)执行")
            return

        # case3: 真正每日固定时刻 0 2 * * * minute与hour都不是*
        if day == "*" and month == "*" and wday == "*":
            if minute != "*" and hour != "*" and not minute.startswith("*/") and not hour.startswith("*/"):
                time_str = f"{hour.zfill(2)}:{minute.zfill(2)}"
                schedule.every().day.at(time_str).do(self._run_task, name)
                logger.info(f"任务 {name} 设置每日 {time_str} 执行")
                return

        # case4：复杂cron表达式，使用croniter原生支持
        try:
            now = datetime.now()
            iter_obj = croniter(expr, now)
            next_run = iter_obj.get_next(datetime)
            self.cron_tasks.append({
                'name': name,
                'expr': expr,
                'croniter': iter_obj,
                'next_run': next_run
            })
            logger.info(f"任务 {name} cron调度生效：{expr}，下次执行：{next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            return
        except Exception as e:
            logger.warning(f"cron表达式解析失败 {expr}，任务[{name}]仅支持手动触发，错误：{e}")
            return

    def _run_task(self, name: str):
        """执行任务（由schedule触发）"""
        logger.info(f"调度器触发任务: {name}")
        try:
            # 检查依赖
            deps = TaskRegistry.get_dependencies(name)
            for dep in deps:
                dep_task = TaskRegistry.get_task(dep)
                if dep_task and dep_task.get('last_status') != 'success':
                    logger.warning(f"依赖任务 {dep} 未成功，跳过 {name}")
                    return

            # 提交到线程池
            future = self.worker_pool.submit_task(name)
            task_info = TaskRegistry.get_task(name)

            try:
                # 等待任务执行完成
                future.result(timeout=task_info['timeout'])
                # 执行成功，更新状态
                TaskRegistry.mark_run(name, True)
                logger.info(f"任务 {name} 执行成功")
            except Exception as e:
                # 执行失败，更新状态
                TaskRegistry.mark_run(name, False)
                logger.error(f"任务 {name} 执行异常: {e}")
                self.alert_manager.send_alert(
                    subject=f"任务执行失败 - {name}",
                    message=f"任务: {name}\n错误: {e}",
                    level="ERROR"
                )
        except Exception as e:
            logger.error(f"调度任务 {name} 失败: {e}")

    def start(self):
        """启动调度器"""
        if self.running:
            logger.warning("调度器已在运行")
            return

        # 为每个任务设置调度
        for name, task in TaskRegistry.get_all_tasks().items():
            if task['schedule_expr']:
                self._schedule_task(name, task)
            else:
                logger.info(f"任务 {name} 无调度表达式，仅可手动触发")

        # 启动一个线程来运行schedule循环
        def _run_loop():
            logger.info("调度器主循环启动")
            self.running = True
            while self.running:
                schedule.run_pending()

                # 检查复杂cron任务是否到达执行时间
                now = datetime.now()
                for task in self.cron_tasks:
                    if now >= task['next_run']:
                        logger.info(f"cron调度触发任务: {task['name']}")
                        self._run_task(task['name'])
                        # 计算下一次执行时间
                        task['next_run'] = task['croniter'].get_next(datetime)
                        logger.info(f"任务 {task['name']} 下次执行：{task['next_run'].strftime('%Y-%m-%d %H:%M:%S')}")

                time.sleep(30)  # 每30秒检查一次

        self.thread = threading.Thread(target=_run_loop, daemon=True)
        self.thread.start()
        logger.info("调度器已启动")

    def stop(self):
        """停止调度器"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.worker_pool.shutdown(wait=True)
        logger.info("调度器已停止")

    def run_task_now(self, name: str):
        """手动立即执行某个任务"""
        task = TaskRegistry.get_task(name)
        if not task:
            logger.error(f"任务 {name} 不存在")
            return
        # 直接执行（不通过schedule）
        self._run_task(name)


# 为了兼容之前的调用方式，保留单例
_scheduler = None

def get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = UnifiedScheduler()
    return _scheduler

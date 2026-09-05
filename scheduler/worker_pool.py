import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor, Future
from functools import wraps
from scheduler.task_registry import TaskRegistry

logger = logging.getLogger(__name__)


def task_runner(name: str):
    """任务执行装饰器，包装异常处理和日志"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger.info(f"开始执行任务: {name}")
            try:
                result = func(*args, **kwargs)
                logger.info(f"任务 {name} 执行成功")
                TaskRegistry.mark_run(name, success=True)
                return result
            except Exception as e:
                logger.error(f"任务 {name} 执行失败: {e}", exc_info=True)
                TaskRegistry.mark_run(name, success=False)
                # 触发告警（由调用方处理）
                raise
        return wrapper
    return decorator


class WorkerPool:
    """任务执行线程池"""
    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.futures: Dict[str, Future] = {}

    def submit_task(self, name: str, *args, **kwargs) -> Future:
        """提交任务到线程池"""
        task = TaskRegistry.get_task(name)
        if not task:
            raise ValueError(f"任务 {name} 未注册")
        func = task['func']
        future = self.executor.submit(func, *args, **kwargs)
        self.futures[name] = future
        return future

    def wait_for_dependencies(self, name: str, timeout: int = 60):
        """等待依赖任务完成"""
        deps = TaskRegistry.get_dependencies(name)
        for dep in deps:
            future = self.futures.get(dep)
            if future:
                try:
                    future.result(timeout=timeout)
                except Exception as e:
                    logger.error(f"依赖任务 {dep} 执行失败，任务 {name} 将跳过")
                    raise RuntimeError(f"依赖任务 {dep} 失败: {e}")
            else:
                logger.warning(f"依赖任务 {dep} 未提交，可能尚未执行")

    def shutdown(self, wait=True):
        self.executor.shutdown(wait=wait)
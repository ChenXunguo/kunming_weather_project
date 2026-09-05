from typing import Dict, Callable, List, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskRegistry:
    """任务注册表，管理所有可调度任务及其依赖关系"""
    _tasks: Dict[str, dict] = {}

    @classmethod
    def register(cls, name: str, func: Callable,
                 schedule_expr: str = None,
                 depends_on: List[str] = None,
                 retries: int = 0,
                 timeout: int = 300):
        """注册任务"""
        cls._tasks[name] = {
            'func': func,
            'schedule_expr': schedule_expr,
            'depends_on': depends_on or [],
            'retries': retries,
            'timeout': timeout,
            'last_run': None,
            'last_status': None
        }
        logger.info(f"任务注册: {name}")

    @classmethod
    def get_task(cls, name: str) -> Optional[dict]:
        return cls._tasks.get(name)

    @classmethod
    def get_all_tasks(cls) -> Dict[str, dict]:
        return cls._tasks

    @classmethod
    def get_dependencies(cls, name: str) -> List[str]:
        task = cls._tasks.get(name)
        return task['depends_on'] if task else []

    @classmethod
    def mark_run(cls, name: str, success: bool):
        task = cls._tasks.get(name)
        if task:
            task['last_run'] = datetime.now()
            task['last_status'] = 'success' if success else 'failed'
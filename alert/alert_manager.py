import logging
from typing import List, Optional
from alert.notifiers import Notifier, EmailNotifier, WeChatNotifier, DingTalkNotifier
from config.config import ALERT_CONFIG

logger = logging.getLogger(__name__)


class AlertManager:
    """告警管理器，负责注册通知器并发送告警"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.notifiers: List[Notifier] = []
            self._init_notifiers()
            self.initialized = True

    def _init_notifiers(self):
        """从配置初始化通知器"""
        # 邮件
        if ALERT_CONFIG.get('email', {}).get('enabled'):
            email_cfg = ALERT_CONFIG['email']
            self.notifiers.append(
                EmailNotifier(
                    smtp_host=email_cfg['smtp_host'],
                    smtp_port=email_cfg['smtp_port'],
                    sender=email_cfg['sender'],
                    password=email_cfg['password'],
                    receivers=email_cfg['receivers'],
                    use_tls=email_cfg.get('use_tls', True)
                )
            )
        # 企业微信
        if ALERT_CONFIG.get('wechat', {}).get('enabled'):
            self.notifiers.append(
                WeChatNotifier(ALERT_CONFIG['wechat']['webhook_url'])
            )
        # 钉钉
        if ALERT_CONFIG.get('dingtalk', {}).get('enabled'):
            self.notifiers.append(
                DingTalkNotifier(
                    webhook_url=ALERT_CONFIG['dingtalk']['webhook_url'],
                    secret=ALERT_CONFIG['dingtalk'].get('secret')
                )
            )

    def send_alert(self, subject: str, message: str, level: str = "INFO"):
        """向所有注册的通知器发送告警"""
        for notifier in self.notifiers:
            try:
                notifier.send(subject, message, level)
            except Exception as e:
                logger.error(f"发送告警到 {notifier.__class__.__name__} 失败: {e}")

    def alert_collect_failure(self, api_name: str, error: str):
        """采集失败告警"""
        self.send_alert(
            subject=f"气象数据采集失败 - {api_name}",
            message=f"采集源: {api_name}\n错误信息: {error}\n时间: {self._now()}",
            level="ERROR"
        )

    def alert_quality_issue(self, date: str, validity_rate: float):
        """数据质量告警（有效率低于阈值）"""
        if validity_rate < ALERT_CONFIG.get('quality_threshold', 95):
            self.send_alert(
                subject=f"数据有效率低于阈值 - {date}",
                message=f"日期: {date}\n有效率: {validity_rate}%\n阈值: {ALERT_CONFIG.get('quality_threshold', 95)}%",
                level="WARNING"
            )

    def alert_model_issue(self, model_name: str, metric: str, value: float):
        """模型性能告警"""
        self.send_alert(
            subject=f"模型异常 - {model_name}",
            message=f"模型: {model_name}\n指标: {metric} = {value}",
            level="WARNING"
        )

    def alert_system_health(self, component: str, status: str):
        """系统健康告警"""
        self.send_alert(
            subject=f"系统健康告警 - {component}",
            message=f"组件: {component}\n状态: {status}",
            level="ERROR" if status == "DOWN" else "WARNING"
        )

    @staticmethod
    def _now():
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
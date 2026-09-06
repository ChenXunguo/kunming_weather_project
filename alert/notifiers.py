import smtplib
import requests
import json
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from abc import ABC, abstractmethod
from typing import List, Optional

logger = logging.getLogger(__name__)


class Notifier(ABC):
    """通知器基类"""
    @abstractmethod
    def send(self, subject: str, message: str, level: str = "INFO"):
        pass


class EmailNotifier(Notifier):
    """邮件通知器（使用SMTP）"""
    def __init__(self, smtp_host: str, smtp_port: int, sender: str,
                 password: str, receivers: list, use_tls: bool = True):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender = sender
        self.password = password
        self.receivers = receivers
        self.use_tls = use_tls

    def send(self, subject: str, message: str, level: str = "INFO"):
        if not self.receivers:
            return
        msg = MIMEMultipart()
        msg['From'] = self.sender
        msg['To'] = ', '.join(self.receivers)
        msg['Subject'] = Header(f"[{level}] {subject}", 'utf-8')
        msg.attach(MIMEText(message, 'plain', 'utf-8'))
        try:
            if self.use_tls:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.login(self.sender, self.password)
            server.sendmail(self.sender, self.receivers, msg.as_string())
            server.quit()
            logger.info(f"邮件通知已发送: {subject}")
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")


class WeChatNotifier(Notifier):
    """企业微信机器人通知器"""
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, subject: str, message: str, level: str = "INFO"):
        if not self.webhook_url:
            return
        # 根据级别添加颜色
        color_map = {"INFO": "info", "WARNING": "warning", "ERROR": "comment"}
        content = f"### [{level}] {subject}\n{message}"
        data = {
            "msgtype": "markdown",
            "markdown": {
                "content": content
            }
        }
        try:
            resp = requests.post(self.webhook_url, json=data, timeout=10)
            if resp.status_code == 200:
                logger.info("企业微信通知发送成功")
            else:
                logger.error(f"企业微信通知失败: {resp.text}")
        except Exception as e:
            logger.error(f"企业微信通知异常: {e}")


class DingTalkNotifier(Notifier):
    """钉钉机器人通知器"""
    def __init__(self, webhook_url: str, secret: str = None):
        self.webhook_url = webhook_url
        self.secret = secret  # 可选加签

    def send(self, subject: str, message: str, level: str = "INFO"):
        if not self.webhook_url:
            return
        data = {
            "msgtype": "text",
            "text": {
                "content": f"[{level}] {subject}\n{message}"
            },
            "at": {
                "isAtAll": False
            }
        }
        try:
            resp = requests.post(self.webhook_url, json=data, timeout=10)
            if resp.status_code == 200:
                logger.info("钉钉通知发送成功")
            else:
                logger.error(f"钉钉通知失败: {resp.text}")
        except Exception as e:
            logger.error(f"钉钉通知异常: {e}")

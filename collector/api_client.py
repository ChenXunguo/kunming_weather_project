import requests
import time
import logging

from config.config import OPENWEATHER_CONFIG, COLLECT_CONFIG

logger = logging.getLogger(__name__)


class OpenWeatherClient:
    def __init__(self):
        self.api_key = OPENWEATHER_CONFIG['api_key']
        self.base_url = OPENWEATHER_CONFIG['base_url']
        self.city = OPENWEATHER_CONFIG['city']
        self.country = OPENWEATHER_CONFIG['country']
        self.units = OPENWEATHER_CONFIG['units']
        self.lang = OPENWEATHER_CONFIG['lang']
        self.timeout = OPENWEATHER_CONFIG.get('timeout', 30)
        self.retry_times = COLLECT_CONFIG['retry_times']
        self.retry_delay = COLLECT_CONFIG['retry_delay']
        # 复用连接会话 + 携带 User-Agent（部分接口强制要求）
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "KunmingWeatherCollector/2.1 (data-analysis project)"
        })

    def _request_with_retry(self, endpoint: str, params: dict):
        """带重试的请求（超时重试，429/5xx退避，401/403直接放弃）"""
        params['appid'] = self.api_key
        params['units'] = self.units
        params['lang'] = self.lang

        resp = None
        for attempt in range(1, self.retry_times + 1):
            try:
                # forecast接口数据量大，单独放大超时时间
                req_timeout = 45 if endpoint == "forecast" else self.timeout
                resp = self.session.get(
                    f"{self.base_url}/{endpoint}",
                    params=params,
                    timeout=(10, req_timeout)  # (连接超时,读取超时)
                )
                if resp.status_code == 429:
                    logger.warning(f"请求 {endpoint} 触发限流(429)（第{attempt}次），{self.retry_delay}秒后重试...")
                    if attempt < self.retry_times:
                        time.sleep(self.retry_delay)
                        continue
                resp.raise_for_status()
                return resp.json()

            except requests.exceptions.Timeout:
                logger.warning(f"请求 {endpoint} 超时（第{attempt}次），{self.retry_delay}秒后重试...")
                if attempt < self.retry_times:
                    time.sleep(self.retry_delay)

            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP错误: {e}")
                if resp is not None and resp.status_code == 401:
                    logger.error("API Key无效或尚未生效（新key需等待5‑10分钟）")
                elif resp is not None and resp.status_code >= 500 and attempt < self.retry_times:
                    # 服务端5xx错误可短暂重试
                    time.sleep(self.retry_delay)
                    continue
                break  # 其余HTTP错误不重试

            except requests.exceptions.RequestException as e:
                logger.error(f"请求异常 {endpoint}: {e}")
                if attempt < self.retry_times:
                    time.sleep(self.retry_delay)

        logger.error(f"请求 {endpoint} 最终失败")
        return None

    def get_current_weather(self):
        """获取实时天气"""
        params = {
            'q': f"{self.city},{self.country}"
        }
        return self._request_with_retry('weather', params)

    def get_forecast(self):
        """获取5天预报"""
        params = {
            'q': f"{self.city},{self.country}"
        }
        return self._request_with_retry('forecast', params)

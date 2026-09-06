FROM python:3.9-slim

WORKDIR /app

# 设置时区
ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1

# 安装系统依赖（WeasyPrint 运行依赖 + 编译依赖）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    tzdata \
    && ln -sf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo "$TZ" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖清单，利用 Docker 层缓存加速构建
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 复制项目全部代码
COPY . .

# 创建运行时必需的所有目录（代码输出路径）
RUN mkdir -p \
    logs \
    reports/figures \
    reports/dashboards \
    reports/pdf \
    models \
    model_cache \
    run

# 暴露 HTTP 监控服务端口
EXPOSE 8899

CMD ["python", "main.py"]

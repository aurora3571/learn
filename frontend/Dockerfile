# 使用 Python 3.11
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制所有前端文件
COPY . .

# 列出文件以确认（调试用）
RUN ls -la

# 设置环境变量
ENV API_BASE_URL=https://learn-self-eight.vercel.app/api

EXPOSE 8080

# 使用绝对路径启动
CMD streamlit run /app/streamlit_app.py --server.port=8080 --server.address=0.0.0.0
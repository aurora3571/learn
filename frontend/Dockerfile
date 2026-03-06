# 明确指定使用 Python 3.11（重要！）
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（最小化安装）
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 包（只安装前端需要的）
RUN pip install --no-cache-dir \
    streamlit==1.32.2 \
    requests==2.31.0 \
    pandas==2.0.3

# 复制应用代码
COPY . .

# 设置环境变量
ENV API_BASE_URL=https://learn-self-eight.vercel.app/api

# 暴露端口
EXPOSE 8080

# 启动命令
CMD streamlit run streamlit_app.py --server.port=8080 --server.address=0.0.0.0
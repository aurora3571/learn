# 使用官方 Python 镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 先单独安装 pandas 的依赖（避免常见问题）
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 只安装必要的包
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 \
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
# 使用 Python 3.11
FROM python:3.11-slim
LABEL "language"="python"

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 设置环境变量
ENV API_BASE_URL=https://learn-self-eight.vercel.app/api

EXPOSE 8080

# 启动应用，指向 frontend 文件夹中的 streamlit_app.py
CMD ["streamlit", "run", "frontend/streamlit_app.py", "--server.port=8080", "--server.address=0.0.0.0"]

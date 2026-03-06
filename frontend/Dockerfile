# 使用 Python 3.11
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件（假设它们在构建上下文的根目录）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 【关键修改】明确复制前端目录
# 如果构建上下文是项目根目录，则复制 frontend 子文件夹
COPY frontend/ /app/

# 如果构建上下文已经是 frontend，则直接复制当前目录
# 为了兼容两种情况，我们使用更稳妥的方式
COPY . /app/

# 列出文件以确认
RUN echo "=== Current directory contents ===" && ls -la /app

# 设置环境变量
ENV API_BASE_URL=https://learn-self-eight.vercel.app/api

EXPOSE 8080

# 使用相对路径启动，因为文件已经在工作目录
CMD streamlit run streamlit_app.py --server.port=8080 --server.address=0.0.0.0
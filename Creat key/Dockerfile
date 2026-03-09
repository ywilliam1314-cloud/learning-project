# 使用官方 Python 3.12 精简镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 复制应用文件
COPY app.py .
COPY templates/ templates/

# 安装依赖
RUN pip install --no-cache-dir flask

# 暴露 Flask 默认端口
EXPOSE 5000

# 设置环境变量
ENV FLASK_APP=app.py

# 绑定 0.0.0.0 使容器外部可访问
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]

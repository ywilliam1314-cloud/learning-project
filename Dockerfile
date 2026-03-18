FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY xyz_to_json.py index.html README.md ./

EXPOSE 2100

ENTRYPOINT ["python", "xyz_to_json.py"]
CMD ["--serve", "--host", "0.0.0.0", "--port", "2100"]

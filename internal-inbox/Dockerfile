FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -u 10001 inbox
COPY . .
USER inbox
CMD ["uvicorn", "app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8024"]

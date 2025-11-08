FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/keys/firebase-sa.json
ENV PYTHONPATH=/app
EXPOSE 5000
CMD ["python", "app.py"]

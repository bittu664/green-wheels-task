FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --no-create-home app
COPY lease ./lease
USER 10001
EXPOSE 8000
CMD ["uvicorn", "lease.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

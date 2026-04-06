FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary

COPY . .

RUN mkdir -p data/uploads data/reports

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

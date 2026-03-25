FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1

# Устанавливаем зависимости отдельно, чтобы кешировать слой.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
  && pip install --no-cache-dir "uvicorn[standard]"

# Копируем код приложения.
COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "8000"]


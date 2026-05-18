FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY entrypoint.sh .
# Windows CRLF breaks Linux exec shebang ("no such file or directory"); normalize at build time.
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 8000

# Invoke via sh so a stray CR in shebang cannot break container start.
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

EXPOSE 8000

# entrypoint.sh migrates and collects static files, then runs the command.
# Production: gunicorn (long timeout for big CSV uploads). docker-compose.yml overrides this with runserver for local use.
ENTRYPOINT ["./entrypoint.sh"]
CMD ["gunicorn", "retail_management_system.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "3", "--timeout", "300", "--access-logfile", "-"]

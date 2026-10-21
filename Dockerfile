FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY community_app.py promote_admin.py reset_password.py updater.py version.json features_v8.py studio_v8.py scheduler_v8.py payments_v8.py ./
COPY integrations/ ./integrations/
COPY studio_v6/ ./studio_v6/
COPY assets/ ./assets/
COPY static/ ./static/
RUN mkdir -p /app/data && chown -R app:app /app
USER app
EXPOSE 8010
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8010'), timeout=3).read()" || exit 1
# One worker: the Auto-Post scheduler and realtime chat hub live in-process.
CMD ["sh", "-c", "exec uvicorn community_app:app --host 0.0.0.0 --port ${PORT:-8010} --workers 1 --proxy-headers --forwarded-allow-ips '*'"]

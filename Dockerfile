FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements_public.txt .
RUN pip install --no-cache-dir -r requirements_public.txt && groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY community_app.py promote_admin.py ./
COPY studio_v6/video_service.py ./studio_v6/video_service.py
COPY studio_v6/product_discovery.py ./studio_v6/product_discovery.py
COPY studio_v6/grok_service.py ./studio_v6/grok_service.py
COPY studio_v6/openrouter_service.py ./studio_v6/openrouter_service.py
COPY studio_v6/shopee_user_import.py ./studio_v6/shopee_user_import.py
COPY static/ ./static/
RUN mkdir -p /app/data && chown -R app:app /app
USER app
EXPOSE 8010
# Railway and similar hosts inject PORT; compose keeps the default 8010.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8010'), timeout=3).read()" || exit 1
# One worker only: SQLite on a single volume. Proxy headers keep per-IP login throttling working behind the host's proxy.
CMD ["sh", "-c", "exec uvicorn community_app:app --host 0.0.0.0 --port ${PORT:-8010} --workers 1 --proxy-headers --forwarded-allow-ips '*'"]

FROM python:3.14-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.lock . && useradd --uid 10001 --create-home hitl
USER hitl

FROM base AS mcp
EXPOSE 8100
CMD ["uvicorn", "codex_hitl.mcp_server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8100", "--workers", "1"]

FROM base AS bot
EXPOSE 8101
CMD ["uvicorn", "codex_hitl.telegram_bot:create_app", "--factory", "--host", "0.0.0.0", "--port", "8101", "--workers", "1"]

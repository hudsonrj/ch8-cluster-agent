FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic httpx

COPY connect/ ./connect/

EXPOSE 8000
CMD ["uvicorn", "connect.server.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

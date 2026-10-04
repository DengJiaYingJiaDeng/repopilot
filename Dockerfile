FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN python -m pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "repopilot.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

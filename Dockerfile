FROM python:3.10-alpine AS build
RUN apk update && apk add git gcc musl-dev python3-dev libffi-dev openssl-dev cargo
WORKDIR /app
COPY requirements.txt .
RUN python -m venv venv
ENV PATH="/app/venv/bin/:$PATH"
RUN pip install -U pip
RUN pip install -r requirements.txt
FROM python:3.10-alpine
WORKDIR /app
COPY --from=build /app/venv /app/venv
# Libmagic is required at runtime by python-magic
RUN apk update && apk add libmagic
ENV PATH="/app/venv/bin/:$PATH"
ENV PYTHONPATH /app
COPY . /app/
ARG APP_VERSION=dev
ARG NEW_INSTALLATION_ENDPOINT=dev
ARG NEW_HEARTBEAT_ENDPOINT=dev
CMD ["python", "-u", "./src/main.py"]

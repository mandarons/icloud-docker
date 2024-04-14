FROM ghcr.io/linuxserver/baseimage-alpine:3.16 AS build
RUN apk update && apk add git gcc musl-dev py3-pip python3 python3-dev libffi-dev openssl-dev
WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv venv
ENV PATH="/app/venv/bin/:$PATH"
RUN pip3 install -U pip
RUN pip3 install -r requirements.txt
FROM ghcr.io/linuxserver/baseimage-alpine:3.16
ARG APP_VERSION=dev
ARG NEW_INSTALLATION_ENDPOINT=dev
ARG NEW_HEARTBEAT_ENDPOINT=dev
WORKDIR /app
COPY --from=build /app/venv /app/venv
# Libmagic is required at runtime by python-magic
RUN apk update && apk add python3 libmagic
ENV PATH="/app/venv/bin/:$PATH"
ENV PYTHONPATH /app
ENV NEW_INSTALLATION_ENDPOINT=$NEW_INSTALLATION_ENDPOINT
ENV NEW_HEARTBEAT_ENDPOINT=$NEW_HEARTBEAT_ENDPOINT
ENV APP_VERSION=$APP_VERSION
COPY . /app/
CMD ["python3", "-u", "./main.py"]

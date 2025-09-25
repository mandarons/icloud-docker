# syntax=docker/dockerfile:1

FROM alpine:3.19

# set version label
ARG APP_VERSION=dev
ARG NEW_INSTALLATION_ENDPOINT=dev
ARG NEW_HEARTBEAT_ENDPOINT=dev
ENV NEW_INSTALLATION_ENDPOINT=$NEW_INSTALLATION_ENDPOINT
ENV NEW_HEARTBEAT_ENDPOINT=$NEW_HEARTBEAT_ENDPOINT
ENV APP_VERSION=$APP_VERSION
LABEL maintainer="mandarons"

# Set environment variables
ENV HOME="/app"
ENV PUID=911
ENV PGID=911

# Install system dependencies and create user first for better caching
RUN \
  echo "**** update package repository ****" && \
  apk update && \
  echo "**** install packages ****" && \
  apk add --no-cache \
    python3 \
    py3-pip \
    sudo \
    libmagic \
    shadow \
    dumb-init \
    su-exec && \
  echo "**** create user ****" && \
  addgroup -g 911 abc && \
  adduser -D -u 911 -G abc abc

# Install build dependencies and Python packages
COPY requirements.txt .
RUN \
  echo "**** install build packages ****" && \
  apk add --no-cache --virtual=build-dependencies \
    git \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    openssl-dev \
    cargo && \
  echo "**** install icloud app ****" && \
  python3 -m venv /venv && \
  /venv/bin/pip install -U --no-cache-dir \
    pip \
    wheel && \
  /venv/bin/pip install -U --no-cache-dir -r requirements.txt && \
  echo "**** cleanup ****" && \
  apk del --purge \
    build-dependencies && \
  rm -rf \
    /tmp/* \
    /root/.cache \
    /root/.cargo && \
  rm requirements.txt

# add local files
COPY . /app/
WORKDIR /app

# Create necessary directories
RUN mkdir -p /icloud /config/session_data && \
    chown -R abc:abc /app /config /icloud

# Create entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 80
USER abc
ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["/usr/local/bin/docker-entrypoint.sh"]

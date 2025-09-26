# syntax=docker/dockerfile:1

# Build stage
FROM python:3.10-alpine3.22 AS builder

# Install build dependencies
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
  pip install -U --no-cache-dir \
    pip \
    wheel && \
  pip install -U --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.10-alpine3.22

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

# Install runtime dependencies and create user
RUN \
  echo "**** update package repository ****" && \
  apk update && \
  echo "**** install runtime packages ****" && \
  apk add --no-cache \
    libmagic \
    shadow \
    su-exec && \
  echo "**** create user ****" && \
  addgroup -g 911 abc && \
  adduser -D -u 911 -G abc -h /home/abc -s /bin/sh abc

# Copy Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# add local files
COPY . /app/
WORKDIR /app

# Create entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 80
CMD ["/usr/local/bin/docker-entrypoint.sh"]

# syntax=docker/dockerfile:1

FROM ghcr.io/linuxserver/baseimage-alpine:3.19

# set version label
ARG APP_VERSION=dev
ARG NEW_INSTALLATION_ENDPOINT=dev
ARG NEW_HEARTBEAT_ENDPOINT=dev
ENV NEW_INSTALLATION_ENDPOINT=$NEW_INSTALLATION_ENDPOINT
ENV NEW_HEARTBEAT_ENDPOINT=$NEW_HEARTBEAT_ENDPOINT
ENV APP_VERSION=$APP_VERSION
LABEL maintainer="mandarons"

ENV HOME="/app"
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
    sudo libmagic shadow dumb-init \
    cargo && \
  echo "**** install packages ****" && \
  apk add --no-cache \
    python3 && \
  echo "**** install icloud app ****" && \
  python3 -m venv /lsiopy && \
  pip install -U --no-cache-dir \
    pip \
    wheel && \
  pip install -U --no-cache-dir -r requirements.txt && \
  echo "**** cleanup ****" && \
  apk del --purge \
    build-dependencies && \
  rm -rf \
    /tmp/* \
    ${HOME}/.cache \
    ${HOME}/.cargo

# add local files
RUN apk update && apk add sudo libmagic shadow dumb-init
COPY root/ /
COPY . /app/
WORKDIR /app

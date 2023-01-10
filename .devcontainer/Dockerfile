FROM mcr.microsoft.com/vscode/devcontainers/python:0-3.10

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN \
    apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    software-properties-common git default-jre && \
    apt-get clean &&\
    rm -rf /var/lib/apt/lists/*
RUN \
    wget https://repo.maven.apache.org/maven2/io/qameta/allure/allure-commandline/2.20.1/allure-commandline-2.20.1.zip && \
    unzip allure-commandline-2.20.1.zip -d /allure && \
    rm allure-commandline-2.20.1.zip

ENV PATH "/allure/allure-2.20.1/bin:${PATH}"

WORKDIR /workspaces

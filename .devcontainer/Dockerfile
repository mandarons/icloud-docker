FROM mcr.microsoft.com/vscode/devcontainers/python:0-3.10

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN \
    apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    software-properties-common git default-jre && \
    apt-get clean &&\
    rm -rf /var/lib/apt/lists/*
# Install allure report
RUN \
    wget https://repo.maven.apache.org/maven2/io/qameta/allure/allure-commandline/2.20.1/allure-commandline-2.20.1.zip && \
    unzip allure-commandline-2.20.1.zip -d /allure && \
    rm allure-commandline-2.20.1.zip
    
RUN mkdir /config /icloud && chown -R vscode:vscode /config /icloud
USER vscode
# Install uv (pip replacement)
RUN \
    curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/allure/allure-2.20.1/bin:/home/vscode/.cargo/bin:${PATH}"

WORKDIR /workspaces

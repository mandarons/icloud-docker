FROM mcr.microsoft.com/devcontainers/python:0-3.11

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Uninstall pre-installed formatting and linting tools
# They would conflict with our pinned versions
RUN pipx uninstall black
RUN pipx uninstall flake8
RUN pipx uninstall pydocstyle
RUN pipx uninstall pycodestyle
RUN pipx uninstall mypy
RUN pipx uninstall pylint

RUN \
    apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    git \
    cmake \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
# Set the default shell to bash instead of sh
ENV SHELL /bin/bash
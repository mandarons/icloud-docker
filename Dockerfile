FROM python:3.10-alpine3.19 AS build
RUN apk update && apk add git gcc musl-dev python3-dev libffi-dev openssl-dev cargo
COPY requirements.txt .
RUN python -m venv /venv
ENV PATH="/venv/bin/:$PATH"
RUN pip install -U pip
RUN pip install -r requirements.txt
FROM python:3.10-alpine3.19
ARG APP_VERSION=dev
ARG NEW_INSTALLATION_ENDPOINT=dev
ARG NEW_HEARTBEAT_ENDPOINT=dev
ENV NEW_INSTALLATION_ENDPOINT=$NEW_INSTALLATION_ENDPOINT
ENV NEW_HEARTBEAT_ENDPOINT=$NEW_HEARTBEAT_ENDPOINT
ENV APP_VERSION=$APP_VERSION
COPY --from=build /venv /venv
# Libmagic is required at runtime by python-magic
RUN apk update && apk add sudo libmagic shadow dumb-init;
COPY . /app/
WORKDIR /app
ENTRYPOINT ["dumb-init", "--"]
CMD ["/app/init.sh"]
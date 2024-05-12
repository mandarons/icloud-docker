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
RUN apk add doas; \
    addgroup --gid 1000 icd; \
    adduser -D --uid 1000 icd -G icd; \
    echo "permit nopass :icd as root" > /etc/doas.d/doas.conf
COPY --from=build /venv /venv
USER icd
# Libmagic is required at runtime by python-magic
RUN doas apk update && doas apk add libmagic shadow dumb-init
ENV PATH="/venv/bin/:$PATH"
ENV PYTHONPATH /app
ENV NEW_INSTALLATION_ENDPOINT=$NEW_INSTALLATION_ENDPOINT
ENV NEW_HEARTBEAT_ENDPOINT=$NEW_HEARTBEAT_ENDPOINT
ENV APP_VERSION=$APP_VERSION
COPY . /app/
WORKDIR /app
RUN doas chown -R icd:icd /app
ENTRYPOINT ["dumb-init", "--"]
CMD ["/app/init.sh"]
FROM python:3.9-alpine AS build
RUN apk update && apk add git gcc musl-dev python3-dev libffi-dev openssl-dev cargo
WORKDIR /app
COPY requirements.txt .
RUN python -m venv venv
ENV PATH="/app/venv/bin/:$PATH"
RUN pip install -U pip
RUN pip install -r requirements.txt
FROM python:3.9-alpine
WORKDIR /app
COPY --from=build /app/venv /app/venv
ENV PATH="/app/venv/bin/:$PATH"
ENV PYTHONPATH /app
COPY . /app/
CMD ["python", "-u", "./src/main.py"]

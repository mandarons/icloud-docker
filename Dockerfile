FROM python:3.9-alpine
RUN apk update && apk add git gcc musl-dev python3-dev libffi-dev openssl-dev cargo
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install -U pip
RUN pip install --no-cache-dir -r requirements.txt
ENV PYTHONPATH /app
COPY . /app/
CMD ["python", "-u", "./src/main.py"]
FROM python:3.10-alpine

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install -r requirements.txt

COPY . .

ENTRYPOINT ["python3"]
CMD ["app.py"]

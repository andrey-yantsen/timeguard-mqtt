FROM python:3.9-alpine

WORKDIR /app
ENV PATH=/root/.poetry/bin:$PATH \
    PYTHONUNBUFFERED=1
COPY poetry.lock pyproject.toml /app/
RUN python -c 'from urllib.request import urlopen; f = urlopen("https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py"); print(f.read().decode("utf-8"))' | python -u - \
  && source $HOME/.poetry/env && poetry install --no-dev --no-interaction --no-root
COPY . /app/
EXPOSE 9997/udp
ENTRYPOINT [ "poetry", "run", "timeguard-mqtt" ]

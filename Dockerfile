FROM python:3.9-alpine

RUN adduser -h /home/tg -D -u 1000 tg
USER tg
WORKDIR /home/tg/app
ENV PATH=/home/tg/.poetry/bin:$PATH \
    PYTHONUNBUFFERED=1
COPY poetry.lock pyproject.toml /home/tg/app/
RUN python -c 'from urllib.request import urlopen; f = urlopen("https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py"); print(f.read().decode("utf-8"))' | python -u - \
  && source $HOME/.poetry/env && poetry install --no-dev --no-interaction --no-root
COPY . /home/tg/app/
EXPOSE 9997/udp
ENTRYPOINT [ "poetry", "run", "timeguard-mqtt" ]

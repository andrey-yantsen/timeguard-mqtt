FROM python:3.10-alpine AS builder

RUN apk add curl \
  && adduser -h /home/tg -D -u 1000 tg
USER tg
WORKDIR /home/tg/app
ENV PATH=/home/tg/.local/bin:$PATH \
    PYTHONUNBUFFERED=1
COPY --chown=tg:tg poetry.lock pyproject.toml /home/tg/app/
RUN python3 -m pip install --user pipx \
  && pipx install poetry \
  && poetry config virtualenvs.in-project true \
  && poetry install --only main --no-interaction --no-root --no-ansi

FROM python:3.10-alpine
RUN adduser -h /home/tg -D -u 1000 tg
USER tg
WORKDIR /home/tg/app
ENV PATH=/home/tg/.local/bin:$PATH \
    PYTHONUNBUFFERED=1
COPY --from=builder /home/tg/app /home/tg/app
COPY --chown=tg:tg . /home/tg/app/
EXPOSE 9997/udp
ENTRYPOINT [ "poetry", "run", "timeguard-mqtt" ]

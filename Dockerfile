FROM python:3.12-alpine AS builder

WORKDIR /app

# Install build dependencies for packages that require compilation (like psutil)
RUN apk add --no-cache \
  gcc \
  python3-dev \
  musl-dev \
  linux-headers && \
  rm -rf /var/cache/apk/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
  pip uninstall -y webdriver-manager

# Remove build dependencies to keep image size small
RUN apk del gcc python3-dev musl-dev linux-headers

FROM python:3.12-alpine

WORKDIR /app

RUN apk add --no-cache \
    chromium \
    chromium-chromedriver \
    udev \
    ttf-freefont && \
    rm -rf /var/cache/apk/*

COPY --from=builder /opt/venv /opt/venv

ARG PUID=0
ARG PGID=0
ENV PUID=${PUID}
ENV PGID=${PGID}

COPY main.py .
COPY modules/ ./modules/
COPY config.example.json .

RUN addgroup -g ${PGID} appgroup && \
    adduser -D -u ${PUID} -G appgroup appuser && \
    chown -R appuser:appgroup /opt/venv /app

ENV PATH="/opt/venv/bin:$PATH"
ENV CHROMEDRIVER_PATH="/usr/bin/chromedriver"

USER appuser

CMD ["python", "-u", "main.py"]
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
  wget unzip curl gnupg ca-certificates \
  fonts-liberation libatk-bridge2.0-0 libatk1.0-0 \
  libatspi2.0-0 libxkbcommon-x11-0 libxcomposite1 \
  libxrandr2 libgbm1 libgtk-3-0 libpangocairo-1.0-0 \
  libnss3 libasound2 x11-utils && \
  mkdir -p /etc/apt/keyrings && \
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | tee /etc/apt/keyrings/google-chrome.asc > /dev/null && \
  echo "deb [signed-by=/etc/apt/keyrings/google-chrome.asc] http://dl.google.com/linux/chrome/deb/ stable main" | tee /etc/apt/sources.list.d/google-chrome.list && \
  apt-get update && apt-get install -y --no-install-recommends google-chrome-stable && \
  rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY main.py .
COPY config.example.json .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "-u", "main.py"]

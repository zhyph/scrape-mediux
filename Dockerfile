# Use the official Python image from the Docker Hub
FROM python:3.12-slim

# Copy and Set the working directory
COPY . /app
WORKDIR /app

RUN rm -fr /app/.git /app/out/* /app/*venv /app/config.json

# Install system dependencies
RUN apt-get update && \
  apt-get install -y wget unzip curl gnupg

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
  sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' && \
  apt-get update && \
  apt-get install -y google-chrome-stable

# Install ChromeDriver
RUN CHROMEDRIVER_VERSION=`curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE` && \
  wget -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip && \
  unzip /tmp/chromedriver.zip chromedriver -d /usr/local/bin/

# Set display port to avoid crash
ENV DISPLAY=:99

# Copy the requirements.txt file and install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Command to run the script
CMD ["python", "-u", "main.py"]

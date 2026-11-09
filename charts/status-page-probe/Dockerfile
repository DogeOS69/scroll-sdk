FROM mcr.microsoft.com/playwright/python:v1.64.1-noble
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir playwright==1.64.1 websocket-client==1.9.2
# Application is mounted from the chart ConfigMap; image contains pinned runtimes.
USER pwuser

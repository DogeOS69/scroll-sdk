FROM mcr.microsoft.com/playwright/python:v1.55.0-noble
RUN pip install --no-cache-dir playwright==1.55.0 websocket-client==1.8.0
# Application is mounted from the chart ConfigMap; image contains pinned runtimes.
USER pwuser

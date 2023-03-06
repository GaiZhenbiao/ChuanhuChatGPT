FROM python:3.9-alpine as builder
RUN apk add --no-cache build-base
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.9-alpine
MAINTAINER iskoldt
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
WORKDIR /app
COPY ChuanhuChatbot.py .
ENV my_api_key empty
CMD ["python3", "-u", "ChuanhuChatbot.py", "2>&1", "|", "tee", "/var/log/application.log"]

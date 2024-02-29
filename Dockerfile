FROM python:3.9-slim-buster as builder
RUN apt-get update \
    && apt-get install -y build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /root/.config/pip && \
    echo "[global]" > /root/.config/pip/pip.conf && \
    echo "index-url = https://pypi.tuna.tsinghua.edu.cn/simple" >> /root/.config/pip/pip.conf && \
    echo "no-cache-dir = true" >> /root/.config/pip/pip.conf
COPY requirements.txt .
COPY requirements_advanced.txt .
RUN pip install --user --no-cache-dir -r requirements.txt
# RUN pip install --user --no-cache-dir -r requirements_advanced.txt

FROM python:3.9-slim-buster
LABEL maintainer="shawn"
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY . /app
WORKDIR /app
ENV dockerrun=yes
CMD ["python3", "-u", "sdb_chat.py","2>&1", "|", "tee", "/var/log/application.log"]

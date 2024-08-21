FROM python:3.10-slim-buster as builder

# Install build essentials, Rust, and additional dependencies
RUN apt-get update \
    && apt-get install -y build-essential curl cmake pkg-config libssl-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# Add Cargo to PATH
ENV PATH="/root/.cargo/bin:${PATH}"

# Upgrade pip and install maturin
RUN pip install --upgrade pip \
    && pip install maturin

COPY requirements.txt .
COPY requirements_advanced.txt .

# Install Python packages, handling primp separately
RUN pip install --user --no-cache-dir $(grep -v primp requirements.txt) \
    && RUSTFLAGS="-C target-feature=-crt-static" pip install --user --no-cache-dir primp
# RUN pip install --user --no-cache-dir -r requirements_advanced.txt

FROM python:3.10-slim-buster
LABEL maintainer="iskoldt"

# Copy Rust and Cargo from builder
COPY --from=builder /root/.cargo /root/.cargo
COPY --from=builder /root/.rustup /root/.rustup

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Set up environment
ENV PATH=/root/.local/bin:/root/.cargo/bin:$PATH
ENV RUSTUP_HOME=/root/.rustup
ENV CARGO_HOME=/root/.cargo

COPY . /app
WORKDIR /app
ENV dockerrun=yes
CMD ["python3", "-u", "ChuanhuChatbot.py","2>&1", "|", "tee", "/var/log/application.log"]
EXPOSE 7860
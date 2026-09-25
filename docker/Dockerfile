ARG UBUNTU=20.04
FROM --platform=linux/arm64 ubuntu:${UBUNTU}
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git ca-certificates pkg-config \
    libsdl2-dev libsdl2-image-dev libsdl2-ttf-dev libasound2-dev \
 && rm -rf /var/lib/apt/lists/*

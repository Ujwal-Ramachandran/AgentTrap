FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends sudo bash \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash lowpriv \
    && printf '%s\n' \
       'lowpriv ALL=(root) NOPASSWD: /usr/bin/find' \
       > /etc/sudoers.d/agenttrap-find \
    && chmod 0440 /etc/sudoers.d/agenttrap-find \
    && mkdir -p /root \
    && chmod 0700 /root

WORKDIR /tmp

COPY entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

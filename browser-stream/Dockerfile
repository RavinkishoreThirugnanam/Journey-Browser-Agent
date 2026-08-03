FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium xvfb x11vnc novnc fluxbox websockify x11-utils dbus-x11 ca-certificates curl socat \
    && rm -rf /var/lib/apt/lists/*
COPY start-stream.sh /usr/local/bin/start-stream.sh
COPY cdp-proxy.py /usr/local/bin/cdp-proxy.py
RUN chmod +x /usr/local/bin/start-stream.sh /usr/local/bin/cdp-proxy.py
EXPOSE 7900 9222
CMD ["/usr/local/bin/start-stream.sh"]

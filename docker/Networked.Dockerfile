# Evaluator still runs with network=none; only the Unix-socket relay is added.
ARG EXPANDED_BASE=crosscode-evaluator-expanded:latest
FROM ${EXPANDED_BASE}
COPY docker/worker.py /opt/worker.py
COPY docker/egress_relay.py /opt/egress_relay.py

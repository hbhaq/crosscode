# Extends the verified pilot image; build evidence records the resolved base ID.
# Core pilot package versions are constrained; no evaluator/test source changes.
ARG PILOT_BASE=crosscode-evaluator-integration:latest
FROM ${PILOT_BASE}
USER root
RUN python -m pip freeze --exclude bigcodebench > /tmp/base-constraints.txt
COPY docker/expanded.requirements.txt /opt/expanded.requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -c /tmp/base-constraints.txt -r /opt/expanded.requirements.txt
ENV NLTK_DATA=/opt/nltk_data
RUN python -c "import nltk; nltk.download('stopwords', download_dir='/opt/nltk_data', raise_on_error=True)"
USER 65534:65534

# Small selected-task integration environment. Not the full benchmark image.
FROM python:3.10-slim-bookworm@sha256:5be5aaecb962a41567bc8041f1e9e3432cb085b037fe057f9a562630b2e4b370
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/bigcode-project/bigcodebench /opt/bigcodebench && git -C /opt/bigcodebench checkout 09dd993f46c3fbf3a799465bb96d524edcb0b199
RUN pip install --no-cache-dir setuptools==80.9.0 setuptools-scm==8.3.1 && pip install --no-deps /opt/bigcodebench
RUN --mount=type=cache,target=/root/.cache/pip pip install numpy==1.24.3 pyarrow==14.0.1 datasets==2.17.0 appdirs==1.4.4 fire==0.7.0 multipledispatch==1.0.0 pqdm==0.2.0 tempdir==0.7.1 termcolor==2.5.0 tqdm==4.67.1 tree-sitter==0.22.3 tree-sitter-python==0.21.0 wget==3.2 transformers==4.51.3 gradio-client==1.10.0 rich==14.0.0 e2b==1.0.6 pandas==2.0.3 matplotlib==3.7.0 scikit-learn==1.3.1 scipy==1.10.1 statsmodels==0.14.0
COPY docker/worker.py /opt/worker.py
ENV PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
WORKDIR /work
USER 65534:65534
ENTRYPOINT ["python", "/opt/worker.py"]

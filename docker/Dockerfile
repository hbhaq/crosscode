# Official dependency environment, frozen by registry manifest digest.
# Evaluator Python code is overlaid from its separately pinned commit.
FROM bigcodebench/bigcodebench-evaluate@sha256:a3cd34ec3840a49d6b7afb240f4bdd47c350bc5991043fd0a91773830f7cd405
USER root
RUN git -C /bigcodebench fetch origin 09dd993f46c3fbf3a799465bb96d524edcb0b199 && git -C /bigcodebench checkout 09dd993f46c3fbf3a799465bb96d524edcb0b199 && pip install --no-deps /bigcodebench
COPY docker/worker.py /opt/worker.py
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /work
USER 65534:65534
ENTRYPOINT ["python", "/opt/worker.py"]

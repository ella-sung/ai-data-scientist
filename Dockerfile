# Used only by --backend docker. Build once:  docker build -t ds-agent:latest .
FROM python:3.11-slim
RUN pip install --no-cache-dir pandas numpy scikit-learn matplotlib
RUN useradd -m analyst
USER analyst
WORKDIR /work

FROM python:3.12-slim
RUN useradd -u 1000 -m seeder
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY assets ./assets
COPY config ./config
RUN mkdir output && chown seeder output
USER 1000
ENTRYPOINT ["seeder"]
CMD ["--help"]

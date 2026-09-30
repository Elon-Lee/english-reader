FROM debian:bookworm-slim AS whisper-builder
RUN apt-get update && apt-get install -y --no-install-recommends cmake build-essential && rm -rf /var/lib/apt/lists/*
COPY tools/vendor/whisper.cpp/ /src/whisper.cpp/
RUN cmake -S /src/whisper.cpp -B /src/whisper.cpp/build -DCMAKE_BUILD_TYPE=Release -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF \
 && cmake --build /src/whisper.cpp/build --target whisper-cli -j2

FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl sqlite3 ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY reader/ /app/reader/
COPY tools/*.py /app/tools/
COPY tools/deployment/ /app/tools/deployment/
COPY --from=whisper-builder /src/whisper.cpp/build/bin/ /opt/shiyue/whisper/
ENV READER_HOST=0.0.0.0 READER_PORT=8765 SHIYUE_RUNTIME_MODE=reader
ENV LD_LIBRARY_PATH=/opt/shiyue/whisper
ENV SHIYUE_WHISPER_CLI=/opt/shiyue/whisper/whisper-cli SHIYUE_WHISPER_MODEL=/opt/shiyue/models/ggml-base.en.bin
EXPOSE 8765
CMD ["python3","tools/reader_server.py"]

# syntax=docker/dockerfile:1.7
FROM jbarlow83/ocrmypdf:latest

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/data/bin:$PATH

# OCRmyPDF image includes Tesseract and Ghostscript; no extra Python deps required

WORKDIR /

CMD ["newdata-ingest"]

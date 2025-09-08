from fastapi import FastAPI

app = FastAPI(title="PersonalCodex API", version="0.1.0")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/")
def root():
    return {
        "name": "PersonalCodex API",
        "status": "ready",
        "docs": "/docs",
    }


# Small Fastapi app the provides a single post webhook

from fastapi import FastAPI, APIRouter, HTTPException
from pydantic_settings import BaseSettings
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import util


class Settings(BaseSettings):
    GITHUB_REPO: str
    DOWNLOAD_DIRECTORY: str


settings = Settings()


async def update():
    await util.update(settings.GITHUB_REPO, settings.DOWNLOAD_DIRECTORY)


@asynccontextmanager
async def lifespan(app: FastAPI):

    # Load in the initial releases
    await update()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(update, "interval", minutes=1)
    scheduler.start()

    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"message": "Hello World, check out the /docs page for more information"}


@app.post("/api/hooks/release-download-toggle")
async def release_download_toggle():

    try:
        await update()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": "success"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import APIKeyHeader
import config

api_scheme = APIKeyHeader(name="authorization")


async def verify_key(key: str = Depends(api_scheme)):
    if key != config.FASTAPI_KEY:
        raise HTTPException(status_code=403)


app = FastAPI(dependencies=[Depends(verify_key)])
from core import bot


@app.get("/")
async def root():
    return {"ping": str(bot)}


from .routes._bot import router as _bot_router
from .routes._image import router as _image_router

app.include_router(_bot_router)
app.include_router(_image_router)

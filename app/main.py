from fastapi import FastAPI
from app.database import Base, engine
from app.api.skills import router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agent Skills Platform")

app.include_router(router, prefix="/api")

@app.get("/")
def root():
    return {"message": "Agent Skills API Running"}
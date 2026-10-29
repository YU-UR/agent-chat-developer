from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
# from contextlib import asynccontextmanager
# from app.infrastructure.kafka.producer import kafka_producer


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     await kafka_producer.start()
#
#     try:
#         yield
#
#     finally:
#         await kafka_producer.stop()


app = FastAPI(
    title="AI Chat Backend",
    # lifespan=lifespan,
)

app.add_middleware(

    CORSMiddleware,

    allow_origins=[
        "http://localhost:5173"
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"]

)

app.include_router(
    chat_router,
    prefix="/api"
)


@app.get("/health")
async def health():
    return {
        "status": "ok"
    }

from contextlib import asynccontextmanager

from fastapi import FastAPI

from mqtt_client import iniciar_mqtt


mqtt_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):

    global mqtt_client

    print("Iniciando backend da estacao...")

    mqtt_client = iniciar_mqtt()

    yield

    print("Encerrando conexao MQTT...")

    if mqtt_client is not None:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()


app = FastAPI(
    lifespan=lifespan
)


@app.get("/")
def inicio():

    return {
        "status": "ok",
        "mensagem": "API da estacao meteorologica funcionando"
    }


@app.get("/teste")
def teste():

    return {
        "temperatura": 25.5,
        "umidade": 67.6
    }
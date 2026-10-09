from fastapi import FastAPI
#=====================================
# API FAST DO RENDER
#======================================
app = FastAPI()

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


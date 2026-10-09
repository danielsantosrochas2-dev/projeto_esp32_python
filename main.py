import time
import json
import dht22
import ldr
import mq135
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

# ============================================================
# LOOP PRINCIPAL
# ============================================================

while True:

    print()
    print("================================")
    print("LEITURA DOS SENSORES")
    print("================================")


    # --------------------------------------------------------
    # DHT22
    # --------------------------------------------------------

    temperatura_dht, umidade = dht22.ler()

    print()
    print("DHT22")
    print("Temperatura:", temperatura_dht, "C")
    print("Umidade:", umidade, "%")


    # --------------------------------------------------------
    # LDR
    # --------------------------------------------------------

    valor_ldr = ldr.ler()

    print()
    print("LDR")
    print("Luminosidade:", valor_ldr)


    # --------------------------------------------------------
    # MQ-135
    # --------------------------------------------------------

    valor_mq135, estado_mq135 = mq135.ler()

    print()
    print("MQ-135")
    print("Analogico:", valor_mq135)
    print("Digital:", estado_mq135)


    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    dados = {
        "temperatura": temperatura_dht,
        "umidade": umidade,
        "luminosidade": valor_ldr,
        "gas": valor_mq135,
        "gas_digital": estado_mq135
    }

    mensagem = json.dumps(dados)


    print()
    print("JSON:")
    print(mensagem)


    # --------------------------------------------------------
    # INTERVALO
    # --------------------------------------------------------

    time.sleep(2)
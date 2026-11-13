
from machine import Pin


# ============================================================
# LDR
# DO -> GPIO 32
# VCC -> 3V3
# GND -> GND
# ============================================================

def criar():

    sensor_digital = Pin(32, Pin.IN)

    return sensor_digital


# Inicializa o sensor
sensor = criar()


# REINICIALIZAÇÃO

def reinicializar():
    global sensor
    sensor = criar()

    print("LDR digital reinicializado")


# LEITURA DO LDR

def ler():

    try:

        valor = sensor.value()

        return valor

    except (OSError, ValueError) as erro:

        print()
        print("Erro no LDR:", erro)

        return None


# TESTE INDIVIDUAL

if __name__ == "__main__":

    import asyncio

    async def testar():

        for numero in range(1, 6):

            valor = ler()

            print()
            print("Leitura", numero)
            print("Estado LDR:", valor)

            await asyncio.sleep_ms(1000)

    asyncio.run(testar())

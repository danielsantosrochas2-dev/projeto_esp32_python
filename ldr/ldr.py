from machine import Pin, ADC


# ============================================================
# LDR
# AO -> GPIO 32
# VCC -> 3V3
# GND -> GND
# ============================================================

def criar():

    sensor_adc = ADC(Pin(32))
    sensor_adc.atten(ADC.ATTN_11DB)

    return sensor_adc

# Inicializa o sensor
sensor = criar()

# REINICIALIZAÇÃO

def reinicializar():
    global sensor
    sensor = criar()

    print("ADC do LDR reinicializado")

# LEITURA DO LDR

def ler():

    try:

        valor = sensor.read()

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
            print("Valor LDR:", valor)

            await asyncio.sleep_ms(1000)

    asyncio.run(testar())
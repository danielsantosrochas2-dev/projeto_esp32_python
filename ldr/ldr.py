from machine import Pin, ADC


# ============================================================
# LDR
# AO -> GPIO 32
# VCC -> 3V3
# GND -> GND
# ============================================================

def criar():

    sensor = ADC(Pin(32))
    sensor.atten(ADC.ATTN_11DB)

    return sensor


sensor = criar()


def ler():

    try:

        valor = sensor.read()

        return valor

    except Exception as erro:

        print()
        print("Erro no LDR:", erro)

        return None
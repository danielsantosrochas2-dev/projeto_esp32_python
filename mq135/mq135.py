from machine import Pin, ADC


# ============================================================
# MQ-135
# AOUT -> GPIO 34
# DOUT -> GPIO 14
# VCC  -> 5V
# GND  -> GND
# ============================================================

analogico = ADC(Pin(34))
analogico.atten(ADC.ATTN_11DB)

digital = Pin(23, Pin.IN)


def ler():

    try:

        valor_analogico = analogico.read()
        estado_digital = digital.value()

        return valor_analogico, estado_digital

    except Exception as erro:

        print()
        print("Erro no MQ-135:", erro)

        return None, None
from machine import Pin
import dht


# ============================================================
# DHT22
# DATA -> GPIO 15
# VCC  -> 3V3
# GND  -> GND
# ============================================================

sensor = dht.DHT22(Pin(15))


def ler():
    try:
        sensor.measure()

        temperatura = sensor.temperature()
        umidade = sensor.humidity()

        return temperatura, umidade

    except Exception as erro:

        print()
        print("Erro no DHT22:", erro)

        return None, None
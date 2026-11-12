from machine import Pin
import dht


# ============================================================
# DHT22
# DATA -> GPIO 15
# VCC  -> 3V3
# GND  -> GND
# ============================================================

PINO_DHT22 = 15
sensor = dht.DHT22(Pin(PINO_DHT22))

# ============================================================
# Leitura do sensor
# ============================================================

def ler():
    try:
        sensor.measure()

        temperatura = sensor.temperature()
        umidade = sensor.humidity()

        # Validacao dos resultados
        return temperatura, umidade

    except (OSError, ValueError) as erro:

        print("Erro no DHT22:", erro)

        return None, None
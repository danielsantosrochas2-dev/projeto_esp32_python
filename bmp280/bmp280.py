from machine import Pin, I2C
import struct
import time


# ==========================================
# CONFIGURACAO DO BMP280
# ==========================================

ENDERECO = 0x76

i2c = I2C(
    0,
    scl=Pin(22),
    sda=Pin(21),
    freq=100000
)


# ==========================================
# IDENTIFICACAO DO SENSOR
# ==========================================

identificador = i2c.readfrom_mem(
    ENDERECO, 0xD0, 1
)[0]

if identificador != 0x58:
    raise ValueError("BMP280 nao identificado")


# ==========================================
# COEFICIENTES DE CALIBRACAO
# ==========================================

calibracao = i2c.readfrom_mem(
    ENDERECO, 0x88, 24
)

(
    T1, T2, T3,
    P1, P2, P3, P4, P5,
    P6, P7, P8, P9
) = struct.unpack("<HhhHhhhhhhhh", calibracao)


# ==========================================
# ATIVAR MEDICOES
# ==========================================

i2c.writeto_mem(
    ENDERECO,
    0xF4,
    b'\x27'
)

inicio_medicao = time.ticks_ms()


# ==========================================
# LEITURA DO BMP280
# ==========================================

def ler():

    if time.ticks_diff(
        time.ticks_ms(),
        inicio_medicao
    ) < 100:
        return None, None

    try:

        dados = i2c.readfrom_mem(
        ENDERECO, 0xF7, 6
        )

    except OSError as erro:

        print("Erro de comunicacao BMP280:", erro)

        return None, None

    pressao_bruta = (
        (dados[0] << 12) |
        (dados[1] << 4) |
        (dados[2] >> 4)
    )

    temperatura_bruta = (
        (dados[3] << 12) |
        (dados[4] << 4) |
        (dados[5] >> 4)
    )

    # Compensacao da temperatura
    var1 = (
        temperatura_bruta / 16384.0
        - T1 / 1024.0
    ) * T2

    var2 = (
        temperatura_bruta / 131072.0
        - T1 / 8192.0
    ) ** 2 * T3

    t_fine = var1 + var2

    temperatura = t_fine / 5120.0

    # Compensacao da pressao
    var1 = t_fine / 2.0 - 64000.0

    var2 = var1 * var1 * P6 / 32768.0
    var2 = var2 + var1 * P5 * 2.0
    var2 = var2 / 4.0 + P4 * 65536.0

    var1 = (
        P3 * var1 * var1 / 524288.0
        + P2 * var1
    ) / 524288.0

    var1 = (1.0 + var1 / 32768.0) * P1

    if var1 == 0:
        raise ValueError("Erro na compensacao da pressao")

    pressao = 1048576.0 - pressao_bruta

    pressao = (
        pressao - var2 / 4096.0
    ) * 6250.0 / var1

    var1 = P9 * pressao * pressao / 2147483648.0
    var2 = pressao * P8 / 32768.0

    pressao = pressao + (var1 + var2 + P7) / 16.0

    # Converter Pa para hPa
    pressao_hpa = pressao / 100.0
    if not (-40 <= temperatura <= 85):
     return None, None

    if not (300 <= pressao_hpa <= 1100):
     return None, None

    return round(temperatura, 2), round(pressao_hpa, 2)


# ==========================================
# TESTE INDIVIDUAL
# ==========================================

if __name__ == "__main__":

    import asyncio

    async def testar():

        # Aguarda a primeira conversao sem bloquear
        await asyncio.sleep_ms(120)

        for numero in range(1, 6):

            temperatura, pressao = ler()

            print()
            print("Leitura", numero)

            if temperatura is not None and pressao is not None:

                print("Temperatura BMP280:", temperatura, "C")
                print("Pressao atmosferica:", pressao, "hPa")

            else:

                print("Leitura indisponivel")

            # Intervalo assincrono entre as leituras
            await asyncio.sleep_ms(1000)

    asyncio.run(testar())
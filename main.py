
import asyncio
import json
import network
import time
import machine
import binascii

from umqtt.simple import MQTTClient


# =========================================================
# CONFIGURAÇÕES MQTT - EMQX
# =========================================================

MQTT_CLIENT_ID = (
    b"esp32-estacao-" +
    binascii.hexlify(machine.unique_id())
)

MQTT_BROKER = "xe4f1e16.ala.us-east-1.emqxsl.com"
MQTT_PORT = 8883

# Preencha com as credenciais atuais.
MQTT_USER = b"teste"
MQTT_PASSWORD = b"1234567"

MQTT_TOPIC = b"estacao/dados"


# =========================================================
# CONFIGURAÇÕES GERAIS
# =========================================================

INTERVALO_LEITURA = 2000
QUANTIDADE_TESTES = 5

MQ135_ATIVO = True

# Calibração experimental do MQ-135
CALIBRAR_MQ135_AO_INICIAR = True
FORCAR_NOVA_CALIBRACAO = False

PPM_REFERENCIA_MQ135 = 420.0
QUANTIDADE_AMOSTRAS_CALIBRACAO = 120


# =========================================================
# CONFIGURAÇÕES WI-FI
# =========================================================

SSID = "Galaxy S23 27DE"
SENHA = "16082014"


# =========================================================
# ETAPA 1 - INICIALIZAR SENSORES
# =========================================================

def inicializar_sensores():

    print()
    print("============================")
    print("INICIALIZANDO SENSORES")
    print("============================")

    import dht22
    import bmp280
    import ldr
    import mq135

    print("DHT22: inicializado")
    print("BMP280: inicializado")
    print("LDR: inicializado")
    print("MQ-135: GPIO34 / divisor 15k + 15k")
    print("MQ-135 digital: GPIO23")

    return dht22, bmp280, ldr, mq135


# =========================================================
# ETAPA 2 - LEITURA ORGANIZADA DOS SENSORES
# =========================================================

def ler_todos_sensores(dht22, bmp280, ldr, mq135):

    # DHT22
    temperatura, umidade = dht22.ler()

    # BMP280
    temperatura_bmp, pressao = bmp280.ler()

    # LDR
    luminosidade = ldr.ler()

    # MQ135
    if MQ135_ATIVO:
        leitura_gas = mq135.ler()
    else:
        leitura_gas = {
            "adc": None,
            "digital": None,
            "tensao_sensor": None,
            "rs_r0": None,
            "co2_equivalente_ppm_estimado": None,
            "status_calibracao": "desativado"
        }

    dados = {
        "temperatura": temperatura,
        "umidade": umidade,

        "temperatura_bmp280": temperatura_bmp,
        "pressao": pressao,

        "luminosidade": luminosidade,

        "qualidade_ar": leitura_gas["adc"],
        "gas_digital": leitura_gas["digital"],

        "mq135_tensao_sensor": leitura_gas["tensao_sensor"],
        "mq135_rs_r0": leitura_gas["rs_r0"],

        "co2_equivalente_ppm_estimado":
            leitura_gas["co2_equivalente_ppm_estimado"],

        "mq135_status_calibracao":
            leitura_gas["status_calibracao"]
    }

    return dados


# =========================================================
# ETAPA 3 - TESTAR SENSORES
# =========================================================

async def testar_sensores(dht22, bmp280, ldr, mq135):

    print()
    print("=========================")
    print("TESTANDO SENSORES")
    print("=========================")

    dados = None

    for numero in range(1, QUANTIDADE_TESTES + 1):

        print()
        print("Leitura:", numero)

        dados = ler_todos_sensores(
            dht22,
            bmp280,
            ldr,
            mq135
        )

        mensagem = json.dumps(dados)

        print("JSON:")
        print(mensagem)

        if numero < QUANTIDADE_TESTES:
            await asyncio.sleep_ms(INTERVALO_LEITURA)

    return dados


# =========================================================
# ETAPA 4 - CALIBRAÇÃO DO MQ135
# =========================================================

def preparar_calibracao_mq135(mq135):

    if not MQ135_ATIVO:
        print("MQ-135 desativado. Calibração ignorada.")
        return

    if not CALIBRAR_MQ135_AO_INICIAR:
        print("Calibração automática desativada.")
        return

    print()
    print("================================")
    print("VERIFICANDO CALIBRACAO MQ-135")
    print("================================")

    try:

        if FORCAR_NOVA_CALIBRACAO:
            print("Apagando calibração anterior...")
            mq135.apagar_calibracao()

        calibracao_existente = mq135._carregar_calibracao()

        if calibracao_existente is not None:

            print("Calibração anterior encontrada.")
            print(
                "Referência:",
                calibracao_existente["ppm_referencia"],
                "PPM"
            )

            print("Mantendo calibração existente.")
            return

        print("Nenhuma calibração encontrada.")

        print("Iniciando calibração experimental...")
        print("Referência configurada:", PPM_REFERENCIA_MQ135)

        resultado = mq135.calibrar_ambiente(
            ppm_referencia=PPM_REFERENCIA_MQ135,
            quantidade=QUANTIDADE_AMOSTRAS_CALIBRACAO
        )

        print("Calibração experimental concluída!")
        print("Resultado:", json.dumps(resultado))

    except Exception as erro:

        print("Falha na calibração do MQ-135:")
        print(erro)

        print("O sensor continuará funcionando sem PPM.")
        print("Verifique a alimentação e as leituras ADC.")


# =========================================================
# ETAPA 5 - CONEXÃO WI-FI
# =========================================================

async def conectar_wifi(ssid, senha):

    print()
    print("======================")
    print("CONECTANDO AO WIFI")
    print("======================")

    wifi = network.WLAN(network.STA_IF)
    wifi.active(True)

    if not wifi.isconnected():

        wifi.connect(ssid, senha)

        inicio = time.ticks_ms()

        while not wifi.isconnected():

            if time.ticks_diff(
                time.ticks_ms(),
                inicio
            ) >= 15000:

                print("Tempo limite de conexão atingido.")
                return None

            await asyncio.sleep_ms(250)

    print("Wi-Fi conectado!")
    print("Endereço IP:", wifi.ifconfig()[0])

    return wifi


# =========================================================
# ETAPA 5.1 - TESTAR RECONEXÃO WI-FI
# =========================================================

async def testar_reconexao_wifi(wifi, ssid, senha):

    print()
    print("=========================")
    print("TESTANDO RECONEXAO WIFI")
    print("=========================")

    print("Desconectando Wi-Fi...")

    wifi.disconnect()
    wifi.active(False)

    await asyncio.sleep_ms(1000)

    print("Wi-Fi desconectado!")
    print("Tentando reconectar...")

    wifi = await conectar_wifi(ssid, senha)

    if wifi is None:

        print("Falha na reconexão.")
        return None

    print("Reconexão realizada com sucesso!")

    return wifi


# =========================================================
# ETAPA 6 - CONEXÃO MQTT
# =========================================================

async def conectar_mqtt():

    print()
    print("================================")
    print("CONECTANDO AO MQTT - EMQX")
    print("================================")

    try:

        client = MQTTClient(
            MQTT_CLIENT_ID,
            MQTT_BROKER,
            port=MQTT_PORT,
            user=MQTT_USER,
            password=MQTT_PASSWORD,
            keepalive=60,
            ssl=True,
            ssl_params={
                "server_hostname": MQTT_BROKER
            }
        )

        client.connect()

        print("MQTT conectado!")
        print("Broker:", MQTT_BROKER)
        print("Porta:", MQTT_PORT)
        print("Tópico:", MQTT_TOPIC)

        return client

    except Exception as erro:

        print("Falha na conexão MQTT:")
        print(erro)

        return None


# =========================================================
# ETAPA 7 - PUBLICAÇÃO CONTÍNUA
# =========================================================

async def publicar_dados(
    client,
    dht22,
    bmp280,
    ldr,
    mq135
):

    print()
    print("============================")
    print("PUBLICACAO CONTINUA MQTT")
    print("============================")

    while True:

        try:

            # LEITURA DOS SENSORES

            dados = ler_todos_sensores(
                dht22,
                bmp280,
                ldr,
                mq135
            )

            # CONVERTER PARA JSON

            mensagem = json.dumps(dados)

            # PUBLICAR MQTT

            client.publish(
                MQTT_TOPIC,
                mensagem.encode()
            )

            print("JSON publicado:")
            print(mensagem)

        except OSError as erro:

            print("Erro na publicação MQTT:")
            print(erro)

            return

        except Exception as erro:

            print("Erro na leitura dos sensores:")
            print(erro)

        await asyncio.sleep_ms(INTERVALO_LEITURA)


# =========================================================
# FUNÇÃO PRINCIPAL
# =========================================================

async def main():

    print()
    print("================================")
    print("INICIANDO ESTACAO METEOROLOGICA")
    print("================================")

    # ETAPA 1 - INICIALIZAR SENSORES

    dht22, bmp280, ldr, mq135 = inicializar_sensores()

    # AGUARDAR PRIMEIRA CONVERSÃO DO BMP280

    await asyncio.sleep_ms(150)

    # ETAPA 2 - TESTAR SENSORES

    await testar_sensores(
        dht22,
        bmp280,
        ldr,
        mq135
    )

    print()
    print("Primeira etapa concluída.")

    # ETAPA 3 - CALIBRAR MQ135

    preparar_calibracao_mq135(mq135)

    # ETAPA 4 - CONECTAR WI-FI

    wifi = await conectar_wifi(
        SSID,
        SENHA
    )

    if wifi is None:

        print("Falha na conexão Wi-Fi.")
        return

    print("Primeira conexão Wi-Fi concluída.")

    # ETAPA 4.1 - TESTAR RECONEXÃO

    wifi = await testar_reconexao_wifi(
        wifi,
        SSID,
        SENHA
    )

    if wifi is None:

        print("Teste de reconexão falhou.")
        return

    # REINICIALIZAR ADC DO LDR

    ldr.reinicializar()

    await asyncio.sleep_ms(150)

    # SEGUNDO TESTE DOS SENSORES

    print()
    print("TESTANDO SENSORES COM WIFI CONECTADO")

    await testar_sensores(
        dht22,
        bmp280,
        ldr,
        mq135
    )

    # ETAPA 5 - GERENCIAMENTO MQTT

    while True:

        # VERIFICAR WI-FI

        if wifi is None or not wifi.isconnected():

            print("Wi-Fi desconectado!")
            print("Tentando reconectar...")

            wifi = await conectar_wifi(
                SSID,
                SENHA
            )

            if wifi is None:

                print("Nova tentativa em 3 segundos.")
                await asyncio.sleep_ms(3000)
                continue

            ldr.reinicializar()

        # CONECTAR MQTT

        client = await conectar_mqtt()

        if client is None:

            print("Nova tentativa MQTT em 3 segundos.")
            await asyncio.sleep_ms(3000)
            continue

        # PUBLICAÇÃO CONTÍNUA

        try:

            await publicar_dados(
                client,
                dht22,
                bmp280,
                ldr,
                mq135
            )

        finally:

            try:
                client.disconnect()
            except OSError:
                pass

        await asyncio.sleep_ms(3000)


# =========================================================
# INICIAR FIRMWARE
# =========================================================

asyncio.run(main())




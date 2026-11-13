import asyncio
import json
import network
import time
import machine
import binascii
from umqtt.simple import MQTTClient

# DADOS DE CONEXAO MQTT -> EQMX

MQTT_CLIENT_ID = (
    b"esp32-estacao-" +
    binascii.hexlify(machine.unique_id()))

MQTT_BROKER = "xe4f1e16.ala.us-east-1.emqxsl.com"
MQTT_PORT = 8883

MQTT_USER = b"teste"
MQTT_PASSWORD = b"1234567"

MQTT_TOPIC = b"estacao/dados"

# CONFIGURAÇÕES

INTERVALO_LEITURA = 2000
QUANTIDADE_TESTES = 5
MQ135_ATIVO = True

# ETAPA 1 - INICIALIZAR SENSORES

def inicializar_sensores():

    print()
    print("============================")
    print("INICIALIZANDO SENSORES")
    print("============================")

    import dht22
    import bmp280
    import ldr
    import mq135

    print("DHT22: inicializando")
    print("BMP280: inicializando")
    print("LDR: inicializando")
    print("MQ-135: inicializando")

    return dht22, bmp280, ldr, mq135

# ETAPA 2 - TESTAR SENSORES

async def testar_sensores(dht22, bmp280, ldr, mq135):

    print()
    print("=========================")
    print("TESTANDO SENSORES")
    print("=========================")

    for numero in range(1, QUANTIDADE_TESTES + 1):

        print()
        print("Leitura:", numero)

        # DHT22
        temperatura, umidade = dht22.ler()

        # BMP280
        temperatura_bmp, pressao = bmp280.ler()

        # LDR
        estado_ldr = ldr.ler()

        # MQ 135

        valor_mq135, estado_mq135 = mq135.ler()

        # ORGANIZAR OS DADOS

        dados = {
            "temperatura": temperatura,
            "umidade": umidade,
            "temperatura_bmp": temperatura_bmp,
            "pressao": pressao,
            "luminosidade": estado_ldr,
            "mq135": valor_mq135,
            "mq135_digital": estado_mq135
        }

        # CONVERTER PARA JSON

        mensagem = json.dumps(dados)

        print()
        print("JSON:")
        print(mensagem)

        # INTERVALO ENTRE LEITURAS

        if numero < QUANTIDADE_TESTES:
            await asyncio.sleep_ms(INTERVALO_LEITURA)

    return dados

# ETAPA 3 - CONEXAO WIFI

SSID = "Galaxy S23 27DE"
SENHA = "16082014"

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

            if time.ticks_diff(time.ticks_ms(), inicio) >= 15000:
                print("Tempo limite de conexao atingido")
                return None

            await asyncio.sleep_ms(250)

    print("Wi-Fi conectado!")
    print("Endereço IP:", wifi.ifconfig()[0])
    return wifi

# ETAPA 3.2 - TESTAR RECONEXÃO DO WIFI

async def testar_reconexao_wifi(wifi, ssid, senha):
    
    print()
    print("=========================")
    print("TESTANDO RECONEXAO WIFI")
    print("=========================")

    # DESCONECTAR
    print("Desconectando Wi-Fi...")

    wifi.disconnect()
    wifi.active(False)

    await asyncio.sleep_ms(1000)
    print("Wi-Fi desconectado!")

    # RECONECTAR

    print("Tentando reconectar...")

    wifi = await conectar_wifi(ssid, senha)

    if wifi is None:
        print("Falha na reconexao")
        return None

    print("Reconexao realizada com sucesso!")

    return wifi


# FUNÇÃO PRINCIPAL

async def main():

    print("Iniciando estacao metereologica")

    # ETAPA 1 

    dht22, bmp280, ldr, mq135 = inicializar_sensores()

    # AGUARDA A PRIMEIRA CONVERSAO DO BMP280
    await asyncio.sleep_ms(150)

    # ETAPA 2
    await testar_sensores(dht22, bmp280, ldr, mq135)
    
    print("Primeira etapa concluida")

    # ETAPA 3 - TESTAR CONEXAO WIFI

    wifi = await conectar_wifi(SSID, SENHA)

    if wifi is None:
        print("Falha na conexao Wi-Fi")
        return

    print("Primeira conexao Wi-Fi concluida")

    # ETAPA 3.2 - RECONEXAO WIFI
    
    wifi = await testar_reconexao_wifi(wifi, SSID, SENHA)

    if wifi is None:
        print("Teste de reconexao falhou")
        return

    # ETAPA 4 - REINICIALIZAR ADC DO LDR

    ldr.reinicializar()

    await asyncio.sleep_ms(150)

    # SEGUNDO TESTE DOS SENSORES

    print()
    print("TESTANDO SENSORES COM WIFI CONECTADO")

    await testar_sensores(dht22, bmp280, ldr, mq135)

    # TESTE 5 - GERENCIAMENTO DA CONEXAO COM O MQTT  

    while True:

        # VERIFICAR CONEXAO WIFI 

        if wifi is None or not wifi.isconnected():

            print("Wi-Fi desconectado!")
            print("Tentando reconectar!")

            nova_conexao = await conectar_wifi(SSID, SENHA)

            if nova_conexao is None:

                print("Nova Tentativa em 3 segundos")
                await asyncio.sleep_ms(3000)
                continue

            wifi = nova_conexao

            # REINICIALIZAR ADC APOS RECONEXAO
            ldr.reinicializar()

        # ETAPA 6 - CONECTAR AO MQTT

        client = await conectar_mqtt()

        if client is None:

            print("Nova tentativa MQTT em 3 segundos")
            await asyncio.sleep_ms(3000)
            continue

        # ETAPA 7 - PUBLICACAO CONTINUA

        try:
            await publicar_dados(client, dht22, bmp280, ldr, mq135)

        finally:
            try:
                client.disconnect()
            except OSError:
                pass

        await asyncio.sleep_ms(3000)

# ETAPA 5 - CONEXAO MQTT    

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
        print("Topico:", MQTT_TOPIC)

        return client

    except Exception as erro:

        print()
        print("Falha na conexao MQTT")
        print("Erro:", erro)

        return None

# ETAPA 7 - PUBLICACAO CONTINUA

async def publicar_dados(client, dht22, bmp280, ldr, mq135):

    print()
    print("============================")
    print("PUBLICACAO CONTINUA MQTT")
    print("============================")

    while True:

        # LEITURA DOS SENSORES

        temperatura, umidade = dht22.ler()
        temperatura_bmp, pressao = bmp280.ler()
        estado_ldr = ldr.ler()
        valor_mq135, estado_mq135 = mq135.ler()

        # ORGANIZAR JSON

        dados = {
            "temperatura": temperatura,
            "umidade": umidade,
            "temperatura_bmp": temperatura_bmp,
            "pressao": pressao,
            "luminosidade": estado_ldr,
            "mq135": valor_mq135,
            "mq135_digital": estado_mq135
        }

        mensagem = json.dumps(dados)

        # PUBLICAR MQTT

        try:

            client.publish(
                MQTT_TOPIC,
                mensagem.encode()
            )

            print("JSON publicado:", mensagem)

        except OSError as erro:

            print("Erro na publicacao MQTT:", erro)
            return

        # INTERVALO ASSINCRONO

        await asyncio.sleep_ms(INTERVALO_LEITURA)

# INICIAR FIRMWARE

asyncio.run(main())



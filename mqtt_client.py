import os
import ssl
import paho.mqtt.client as mqtt


MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "estacao/dados")


def ao_conectar(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("MQTT conectado com sucesso!")

        client.subscribe(MQTT_TOPIC)

        print("Inscrito no topico:", MQTT_TOPIC)

    else:
        print("Falha ao conectar no MQTT:", reason_code)


def ao_receber(client, userdata, mensagem):
    try:
        conteudo = mensagem.payload.decode()

        print()
        print("================================")
        print("MENSAGEM MQTT RECEBIDA")
        print("================================")

        print("Topico:", mensagem.topic)
        print("Dados:", conteudo)

    except Exception as erro:
        print("Erro ao processar mensagem:", erro)


def iniciar_mqtt():

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="render-backend"
    )

    client.username_pw_set(
        MQTT_USER,
        MQTT_PASSWORD
    )

    client.tls_set(
        cert_reqs=ssl.CERT_REQUIRED
    )

    client.on_connect = ao_conectar
    client.on_message = ao_receber

    print("Conectando ao EMQX...")

    client.connect(
        MQTT_BROKER,
        MQTT_PORT,
        keepalive=60
    )

    client.loop_start()

    return client
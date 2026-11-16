
"""
MQ-135 FC-22 - ESP32 / MicroPython

LIGAÇÕES:

MQ-135 VCC -> 5V
MQ-135 GND -> GND comum

AOUT -> resistor superior 15k -> GPIO34
GPIO34 -> resistor inferior 15k -> GND

DOUT -> GPIO23

ATENÇÃO:
A estimativa de PPM representa CO2 equivalente experimental.
O MQ-135 não é seletivo para CO2 e não fornece um índice oficial
de qualidade do ar.

A temporização é responsabilidade do main.py.
"""

from machine import ADC, Pin
import json
import os
import math


# =========================================================
# CONFIGURAÇÕES
# =========================================================

GPIO_MQ135 = 34
GPIO_MQ135_DO = 23

RESISTOR_SUPERIOR_OHM = 15000.0
RESISTOR_INFERIOR_OHM = 15000.0

FATOR_DIVISOR = (
    RESISTOR_SUPERIOR_OHM + RESISTOR_INFERIOR_OHM
) / RESISTOR_INFERIOR_OHM

TENSAO_CIRCUITO_V = 5.0
ADC_MAX = 4095

QUANTIDADE_AMOSTRAS = 10

ARQUIVO_CALIBRACAO = "mq135_calibracao.json"

# Curva empírica aproximada
COEFICIENTE_CURVA = 116.602
EXPOENTE_CURVA = 2.769

VERSAO_CALIBRACAO = 1


# =========================================================
# INICIALIZAÇÃO
# =========================================================

adc = ADC(Pin(GPIO_MQ135))
adc.atten(ADC.ATTN_11DB)
adc.width(ADC.WIDTH_12BIT)

pino_digital = Pin(GPIO_MQ135_DO, Pin.IN)

_calibracao = None


# =========================================================
# LEITURA ANALÓGICA
# =========================================================

def _ler_amostra_sensor():
    """
    Retorna:
    ADC, tensão no GPIO34 e tensão reconstruída em AOUT.
    """

    valor_adc = adc.read()

    if hasattr(adc, "read_uv"):
        tensao_adc = adc.read_uv() / 1000000.0
    else:
        tensao_adc = (valor_adc / ADC_MAX) * 3.3

    tensao_ao = tensao_adc * FATOR_DIVISOR

    return valor_adc, tensao_adc, tensao_ao


def _media_tensao(quantidade=QUANTIDADE_AMOSTRAS):
    """
    Calcula a média das amostras sem bloquear o programa
    com temporizações artificiais.
    """

    soma_adc = 0
    soma_tensao_adc = 0.0
    soma_tensao_ao = 0.0

    for _ in range(quantidade):

        valor_adc, tensao_adc, tensao_ao = (
            _ler_amostra_sensor()
        )

        soma_adc += valor_adc
        soma_tensao_adc += tensao_adc
        soma_tensao_ao += tensao_ao

    return (
        soma_adc / quantidade,
        soma_tensao_adc / quantidade,
        soma_tensao_ao / quantidade
    )


# =========================================================
# CÁLCULOS
# =========================================================

def _fator_sensor(tensao_ao):
    """
    Calcula o fator proporcional a Rs/RL:

    (Vc / Vout) - 1

    O divisor externo deve permanecer conectado
    tanto na calibração quanto na operação.
    """

    if tensao_ao <= 0.01:
        return None

    if tensao_ao >= TENSAO_CIRCUITO_V:
        return None

    return (TENSAO_CIRCUITO_V / tensao_ao) - 1.0


def _calcular_razao(fator_atual, fator_referencia):

    if fator_atual is None:
        return None

    if fator_referencia is None or fator_referencia <= 0:
        return None

    return fator_atual / fator_referencia


def _calcular_ppm(razao):
    """
    Estimativa experimental de CO2 equivalente.
    """

    if razao is None or razao <= 0:
        return None

    ppm = COEFICIENTE_CURVA * math.pow(
        razao,
        -EXPOENTE_CURVA
    )

    if not math.isfinite(ppm):
        return None

    return round(ppm, 1)


# =========================================================
# CALIBRAÇÃO
# =========================================================

def calibrar_ambiente(ppm_referencia=420.0, quantidade=120):
    """
    Calibração experimental com concentração de referência.

    420 ppm é apenas uma referência aproximada de ar externo.
    Não equivale a uma calibração com gás padrão certificado.

    O sensor deve estar termicamente estabilizado e em ambiente
    externo adequado, longe de fontes de gases interferentes.
    """

    global _calibracao

    ppm_referencia = float(ppm_referencia)

    if ppm_referencia <= 0:
        raise ValueError("PPM de referência inválido.")

    if quantidade < 10:
        raise ValueError("Utilize pelo menos 10 amostras.")

    soma_fator = 0.0
    soma_tensao = 0.0
    validas = 0

    for _ in range(quantidade):

        _, _, tensao_ao = _ler_amostra_sensor()

        fator = _fator_sensor(tensao_ao)

        if fator is not None and fator > 0:

            soma_fator += fator
            soma_tensao += tensao_ao

            validas += 1

    if validas < quantidade * 0.8:
        raise ValueError(
            "Leituras inválidas. Confira alimentação e divisor."
        )

    fator_medio = soma_fator / validas
    tensao_media = soma_tensao / validas

    razao_referencia = math.pow(
        COEFICIENTE_CURVA / ppm_referencia,
        1.0 / EXPOENTE_CURVA
    )

    fator_referencia = fator_medio / razao_referencia

    _calibracao = {
        "versao": VERSAO_CALIBRACAO,
        "ppm_referencia": ppm_referencia,
        "tensao_ao_calibracao_v": round(tensao_media, 4),
        "fator_referencia": fator_referencia,
        "amostras_validas": validas,
        "divisor_superior_ohm": RESISTOR_SUPERIOR_OHM,
        "divisor_inferior_ohm": RESISTOR_INFERIOR_OHM,
        "tensao_circuito_v": TENSAO_CIRCUITO_V,
        "curva": "MQ135_CO2_equivalente_aproximada_v1"
    }

    with open(ARQUIVO_CALIBRACAO, "w") as arquivo:
        arquivo.write(json.dumps(_calibracao))

    return dict(_calibracao)


# =========================================================
# CARREGAMENTO DA CALIBRAÇÃO
# =========================================================

def _carregar_calibracao():
    global _calibracao

    if _calibracao is not None:
        return _calibracao

    try:

        with open(ARQUIVO_CALIBRACAO, "r") as arquivo:
            dados = json.loads(arquivo.read())

        if (
            dados.get("versao") == VERSAO_CALIBRACAO
            and dados.get("fator_referencia", 0) > 0
            and dados.get("ppm_referencia", 0) > 0
        ):
            _calibracao = dados

    except (OSError, ValueError, TypeError):
        _calibracao = None

    return _calibracao


def apagar_calibracao():
    """
    Remove a calibração salva para permitir nova calibração.
    """

    global _calibracao

    _calibracao = None

    try:
        os.remove(ARQUIVO_CALIBRACAO)
    except OSError:
        pass


# =========================================================
# LEITURA PRINCIPAL
# =========================================================

def ler():
    """
    Retorna os dados do MQ-135 para o main.py.
    """

    adc_medio, tensao_adc, tensao_ao = _media_tensao()

    fator_atual = _fator_sensor(tensao_ao)

    calibracao = _carregar_calibracao()

    razao = None
    ppm = None
    status = "pendente"

    if fator_atual is None:

        status = "erro"

    elif calibracao is not None:

        razao = _calcular_razao(
            fator_atual,
            calibracao["fator_referencia"]
        )

        ppm = _calcular_ppm(razao)

        if ppm is not None:
            status = "estimativa_experimental"
        else:
            status = "erro"

    return {
        "adc": int(adc_medio + 0.5),

        "digital": pino_digital.value(),

        "tensao_adc": round(tensao_adc, 4),

        "tensao_sensor": round(tensao_ao, 4),

        "rs_r0": round(razao, 5) if razao is not None else None,

        "co2_equivalente_ppm_estimado": ppm,

        "status_calibracao": status
    }


# =========================================================
# DIAGNÓSTICO
# =========================================================

def diagnostico():
    """
    Retorna dados complementares para testes.
    """

    dados = ler()

    dados["fator_divisor"] = FATOR_DIVISOR
    dados["gpio_analogico"] = GPIO_MQ135
    dados["gpio_digital"] = GPIO_MQ135_DO
    dados["calibracao_carregada"] = (
        _carregar_calibracao() is not None
    )

    return dados

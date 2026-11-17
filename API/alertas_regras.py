"""Regras configuráveis de alertas ambientais da estação.

Os limites abaixo são OPERACIONAIS/DE DEMONSTRAÇÃO, não limites legais,
clínicos ou índices oficiais de qualidade do ar. Ajuste à instalação.
MQ-135 não é um medidor seletivo de CO2 nem fornece AQI por contagem ADC.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Limites exemplificativos, não caracterizam risco à saúde por si só.
LIMITES = {
    "temperatura": {"unidade": "°C", "baixo_aviso": 0, "baixo_critico": -10,
                    "alto_aviso": 40, "alto_critico": 50},
    "umidade": {"unidade": "%", "baixo_aviso": 20, "baixo_critico": 10,
                "alto_aviso": 90, "alto_critico": 98},
}


def novo_alerta(codigo: str, gravidade: str, categoria: str, mensagem: str,
                campo: str | None = None, valor: Any = None) -> dict:
    return {"codigo": codigo, "gravidade": gravidade, "categoria": categoria,
            "mensagem": mensagem, "campo": campo, "valor": valor,
            "gerado_em": datetime.now(timezone.utc).isoformat()}


def avaliar_alertas(dados: dict, avisos: list[str], invalidos: list[str],
                    status_calibracao: str | None,
                    gas_digital_ativo: int | None = None) -> list[dict]:
    """Classifica leituras já validadas; não modifica valores nem os descarta."""
    alertas: list[dict] = []
    for campo, cfg in LIMITES.items():
        valor = dados.get(campo)
        if valor is None:
            continue
        unidade = cfg["unidade"]
        if valor <= cfg["baixo_critico"] or valor >= cfg["alto_critico"]:
            gravidade = "critico"
        elif valor <= cfg["baixo_aviso"] or valor >= cfg["alto_aviso"]:
            gravidade = "atencao"
        else:
            continue
        alertas.append(novo_alerta(f"limite_{campo}", gravidade, "ambiental",
                                  f"{campo}: {valor} {unidade} fora da faixa operacional configurada",
                                  campo, valor))

    for aviso in avisos:
        gravidade = "atencao"
        if aviso == "Grande diferença entre os sensores de temperatura":
            a, b = dados.get("temperatura"), dados.get("temperatura_bmp280")
            if a is not None and b is not None and abs(a - b) > 15:
                gravidade = "critico"
        alertas.append(novo_alerta("anomalia_" + aviso.lower().replace(" ", "_"),
                                  gravidade, "sensor", aviso))

    for campo in invalidos:
        alertas.append(novo_alerta("invalido_" + campo, "atencao", "integridade",
                                  f"Dado inválido recebido no campo {campo}", campo))

    if status_calibracao == "erro":
        alertas.append(novo_alerta("mq135_calibracao_erro", "atencao", "mq135",
                                  "MQ-135: erro de calibração; não interpretar estimativa de CO2"))
    elif status_calibracao == "pendente":
        # Estado informativo disponível em /alertas/ativos, não é perigo ambiental.
        alertas.append(novo_alerta("mq135_calibracao_pendente", "informativo", "mq135",
                                  "MQ-135: calibração pendente; estimativa de CO2 indisponível"))

    if gas_digital_ativo in (0, 1) and dados.get("gas_digital") == gas_digital_ativo:
        alertas.append(novo_alerta("mq135_saida_digital", "atencao", "mq135",
                                  "MQ-135: saída digital acionada; verificar circuito e limiar do módulo",
                                  "gas_digital", dados["gas_digital"]))
    # Sem limiar numérico de CO2: o MQ-135 não sustenta alarmes confiáveis em ppm.
    # Sem limiar do valor ADC bruto: 'qualidade_ar' não é AQI.
    return alertas

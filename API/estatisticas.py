
import math
import statistics


MINIMO_AMOSTRAS_OUTLIERS = 4
LIMITE_MODIFIED_Z_SCORE = 3.5


def eh_valor_numerico_valido(valor):
    """Verifica se o valor é numérico, finito e não booleano."""
    return (
        isinstance(valor, (int, float))
        and not isinstance(valor, bool)
        and math.isfinite(valor)
    )


def validar_valores(valores):
    """
    Separa valores válidos, ausentes e inválidos.

    None é considerado ausente.
    Texto, booleanos, NaN e infinito são considerados inválidos.
    """
    dados = []
    ausentes = 0
    descartados = 0

    for valor in valores:
        if valor is None:
            ausentes += 1
            continue

        if not eh_valor_numerico_valido(valor):
            descartados += 1
            continue

        dados.append(float(valor))

    return dados, ausentes, descartados


def calcular_media(valores):
    dados, _, _ = validar_valores(valores)
    return statistics.mean(dados) if dados else None


def calcular_mediana(valores):
    dados, _, _ = validar_valores(valores)
    return statistics.median(dados) if dados else None


def calcular_desvio_padrao(valores):
    """Desvio-padrão populacional da janela analisada."""
    dados, _, _ = validar_valores(valores)

    if not dados:
        return None

    return statistics.pstdev(dados)


def calcular_mad(valores):
    """Desvio absoluto mediano em relação à mediana."""
    dados, _, _ = validar_valores(valores)

    if not dados:
        return None

    mediana = statistics.median(dados)
    desvios = [abs(valor - mediana) for valor in dados]

    return statistics.median(desvios)


def identificar_outliers(valores, limite=LIMITE_MODIFIED_Z_SCORE):
    """
    Identifica possíveis valores atípicos pelo Modified Z-Score.

    Se MAD for zero, não tenta substituir o método por IQR.
    Nesse cenário, a dispersão não permite uma classificação
    robusta por este método.

    Os índices retornados correspondem à lista de valores válidos.
    """
    dados, _, _ = validar_valores(valores)

    if len(dados) < MINIMO_AMOSTRAS_OUTLIERS:
        return [], "amostras_insuficientes"

    if (
        isinstance(limite, bool)
        or not isinstance(limite, (int, float))
        or not math.isfinite(limite)
        or limite <= 0
    ):
        raise ValueError("O limite precisa ser um número finito maior que zero.")

    mediana = statistics.median(dados)
    mad = calcular_mad(dados)

    if mad is None or mad == 0:
        return [], "mad_zero_sem_classificacao"

    encontrados = []

    for indice, valor in enumerate(dados):
        escore = 0.6745 * (valor - mediana) / mad

        if abs(escore) > limite:
            encontrados.append({
                "indice": indice,
                "valor": valor,
                "escore": escore,
            })

    return encontrados, "modified_z_score"


def classificar_sequencias(outliers):
    """
    Diferencia suspeitas isoladas de suspeitas consecutivas.

    A sequência considera posições consecutivas entre as
    amostras válidas da janela.
    """
    if not outliers:
        return []

    ordenados = sorted(outliers, key=lambda item: item["indice"])

    grupos = []
    grupo_atual = [ordenados[0]]

    for item in ordenados[1:]:
        indice_anterior = grupo_atual[-1]["indice"]

        if item["indice"] == indice_anterior + 1:
            grupo_atual.append(item)
        else:
            grupos.append(grupo_atual)
            grupo_atual = [item]

    grupos.append(grupo_atual)

    resultado = []

    for grupo in grupos:
        tamanho = len(grupo)

        for item in grupo:
            resultado.append({
                **item,
                "classificacao_temporal": (
                    "consecutivo" if tamanho > 1 else "isolado"
                ),
                "tamanho_sequencia": tamanho,
            })

    return resultado


def calcular_estatisticas(valores):
    """
    Calcula estatísticas descritivas e possíveis outliers.

    Não modifica nem remove os dados originais.
    O arredondamento acontece somente na resposta.
    """
    dados, ausentes, descartados = validar_valores(valores)

    quantidade_recebida = len(valores)
    quantidade_validos = len(dados)

    resultado_base = {
        "quantidade_recebida": quantidade_recebida,
        "quantidade": quantidade_validos,
        "quantidade_ausentes": ausentes,
        "quantidade_descartada": descartados,
        "minimo": None,
        "maximo": None,
        "media": None,
        "mediana": None,
        "desvio_padrao": None,
        "mad": None,
        "outliers": [],
        "metodo_outliers": "nao_aplicavel",
        "status": "sem_dados",
    }

    if not dados:
        return resultado_base

    media = statistics.mean(dados)
    mediana = statistics.median(dados)
    desvio = statistics.pstdev(dados)
    mad = calcular_mad(dados)

    outliers, metodo = identificar_outliers(dados)

    resultado_base.update({
        "minimo": round(min(dados), 2),
        "maximo": round(max(dados), 2),
        "media": round(media, 2),
        "mediana": round(mediana, 2),
        "desvio_padrao": round(desvio, 2),
        "mad": round(mad, 2),
        "metodo_outliers": metodo,
    })

    if quantidade_validos < MINIMO_AMOSTRAS_OUTLIERS:
        resultado_base["status"] = "amostras_insuficientes"

    elif metodo == "mad_zero_sem_classificacao":
        resultado_base["status"] = "outliers_nao_avaliados_mad_zero"

    else:
        resultado_base["status"] = "calculado"

    outliers = classificar_sequencias(outliers)

    resultado_base["outliers"] = [
        {
            **item,
            "valor": round(item["valor"], 2),
            "escore": round(item["escore"], 2),
        }
        for item in outliers
    ]

    return resultado_base


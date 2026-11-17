import asyncio
import json
import logging
import math
import os
import queue
import secrets
import ssl
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable, Literal, NamedTuple
import certifi
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field
from supabase import create_client
from alertas_regras import avaliar_alertas, LIMITES
from estatisticas import (
    calcular_estatisticas,
    eh_valor_numerico_valido,
)
# ----------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
ARQUIVO_ENV = BASE_DIR / ".env"
load_dotenv(ARQUIVO_ENV, override=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("estacao")
if not ARQUIVO_ENV.exists():
    logger.warning(f"O arquivo {ARQUIVO_ENV} não existe. O nome precisa ser '.env'.")
def env(nome: str, padrao: str | None = None) -> str | None:
    """Lê a variável removendo espaços e aspas que sobram no .env."""
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    valor = valor.strip().strip('"').strip("'").strip()
    return valor or padrao
# Segredos e endereços não têm valor padrão no código: ficam só no .env.
MQTT_HOST = env("MQTT_HOST")
MQTT_PORTA = int(env("MQTT_PORT", "8883"))
MQTT_USUARIO = env("MQTT_USERNAME")
MQTT_SENHA = env("MQTT_PASSWORD")
MQTT_TOPICO = env("MQTT_TOPIC", "estacao/dados")
SUPABASE_URL = (env("SUPABASE_URL") or "").rstrip("/")
if SUPABASE_URL.endswith("/rest/v1"):
    SUPABASE_URL = SUPABASE_URL[: -len("/rest/v1")]
SUPABASE_CHAVE = env("SUPABASE_SERVICE_KEY")
SUPABASE_TABELA = env("SUPABASE_TABLE", "leituras")
WS_TOKEN = env("WS_TOKEN")
CORS_ORIGENS = [
    o.strip() for o in (env("CORS_ORIGINS", "*") or "*").split(",") if o.strip()
]
INTERVALO_ESPERADO = float(env("INTERVALO_ESPERADO_S", "2"))
PRESSAO_UNIDADE = (env("PRESSAO_UNIDADE", "hPa") or "hPa").lower()
if PRESSAO_UNIDADE not in ("hpa", "pa"):
    raise ValueError("PRESSAO_UNIDADE deve ser hPa ou Pa")
LIMITE_OBSOLETO_S = float(
    env("LIMITE_OBSOLETO_S", str(max(10.0, INTERVALO_ESPERADO * 5)))
)
# Salva os dois sensores extras por padrão; requer colunas no Supabase.
SALVAR_EXTRAS_NO_BANCO = (env("SALVAR_EXTRAS_NO_BANCO", "true") or "").lower() in (
    "1", "true", "sim", "yes",
)
TAMANHO_LOTE = 50
ARQUIVO_NAO_GRAVADAS = BASE_DIR / "leituras_nao_gravadas.jsonl"
# Colunas que já existem na tabela. id_leitura e data_hora são preenchidas pelo banco.
COLUNAS_BANCO = [
    "temperatura",
    "umidade",
    "pressao",
    "qualidade_ar",
    "luminosidade",
    "mq135_tensao_sensor",
    "mq135_rs_r0",
    "co2_equivalente_ppm_estimado",
    "mq135_status_calibracao",
]
# Sensores extras gravados no banco quando habilitados.
COLUNAS_EXTRAS = ["temperatura_bmp280", "gas_digital"]
COLUNAS_ESCRITA = COLUNAS_BANCO + (COLUNAS_EXTRAS if SALVAR_EXTRAS_NO_BANCO else [])
COLUNAS_LEITURA = ["id_leitura", "data_hora", *COLUNAS_ESCRITA]
# Estado em memória
ultima_leitura: "Registro | None" = None
trava = Lock()
cliente_mqtt = None
cliente_supabase = None
loop_principal: asyncio.AbstractEventLoop | None = None
fila_gravacao: "queue.Queue[dict]" = queue.Queue(maxsize=5000)
parar_escritor = Event()
thread_escritor: Thread | None = None
# Alertas usam fila e thread próprias para não bloquear a recepção MQTT.
fila_alertas: "queue.Queue[dict]" = queue.Queue(maxsize=1000)
thread_alertas: Thread | None = None
ULTIMO_ALERTA: dict[str, float] = {}
ALERTAS_ATIVOS: set[str] = set()
alertas_ativos_detalhados: list[dict] = []
# Somente habilite após confirmar a polaridade da saída digital no módulo.
MQ135_DIGITAL_ATIVO = env("MQ135_DIGITAL_ATIVO")
if MQ135_DIGITAL_ATIVO not in (None, "0", "1"):
    raise ValueError("MQ135_DIGITAL_ATIVO deve ser 0, 1 ou ficar vazio")
INTERVALO_REPETICAO_ALERTA_S = 300  # 5 minutos por mensagem
ARQUIVO_ALERTAS_PENDENTES = BASE_DIR / "alertas_nao_gravados.jsonl"
estatisticas = {
    "gravadas": 0,
    "falhas": 0,
    "descartadas": 0,
    "ultimo_erro": None,
    "ultimo_sucesso": None,
}
# ----------------------------------------------------------------------
# Validação dos sensores
# ----------------------------------------------------------------------
class Campo(NamedTuple):
    minimo: float
    maximo: float
    inteiro: bool = False
    nomes_antigos: tuple[str, ...] = ()  # nomes alternativos aceitos (o ESP32 envia estes)
    conversor: Callable[[float], float] | None = None
def pressao_para_hpa(valor: float) -> float:
    """Converte a unidade configurada no .env para hPa."""
    return valor / 100 if PRESSAO_UNIDADE == "pa" else valor
"""
# Validação DHT22
"""
def calcular_mq135(razao_rs_r0: float | None):
    """Calcula CO2 equivalente estimado a partir de Rs/R0 enviado pelo firmware.
    É uma curva empírica aproximada do MQ-135, não uma medição seletiva de CO2.
    A calibração e a compensação do divisor são realizadas no firmware.
    """
    if razao_rs_r0 is None or not isinstance(razao_rs_r0, (int, float)):
        return None
    if not math.isfinite(razao_rs_r0) or razao_rs_r0 <= 0:
        return None
    ppm = 116.602 * (float(razao_rs_r0) ** -2.769)
    if not math.isfinite(ppm) or ppm < 0 or ppm > 100000:
        return None
    return round(ppm, 1)
CAMPOS = {
    "temperatura": Campo(-40, 80),  # DHT22
    "temperatura_bmp280": Campo(-40, 85, nomes_antigos=("temperatura_bmp",)),
    "umidade": Campo(0, 100),
    "pressao": Campo(300, 1100, conversor=pressao_para_hpa),
    "qualidade_ar": Campo(0, 4095, inteiro=True, nomes_antigos=("mq135", "gas")),
    "mq135_tensao_sensor": Campo(0.01, 5.0),
    "mq135_rs_r0": Campo(0.000001, 100000),
    "co2_equivalente_ppm_estimado": Campo(0, 100000),
    "luminosidade": Campo(0, 1, inteiro=True),
    "gas_digital": Campo(0, 1, inteiro=True, nomes_antigos=("mq135_digital",)),
}
def validar_valor(valor, campo: Campo):
    """Devolve o valor limpo ou None se for inválido."""
    if isinstance(valor, bool):
        return None
    if not isinstance(valor, (int, float)) or not math.isfinite(valor):
        return None
    if campo.conversor:
        valor = campo.conversor(valor)
    if campo.inteiro:
        if isinstance(valor, float):
            if not valor.is_integer():
                return None
            valor = int(valor)
    if not campo.minimo <= valor <= campo.maximo:
        return None
    return valor if campo.inteiro else round(float(valor), 2)
def validar_campos(brutos: dict):
    """Valida campo a campo. Um campo ruim não derruba a leitura inteira."""
    dados, invalidos, ausentes = {}, [], []
    for nome, campo in CAMPOS.items():
        chaves = (nome, *campo.nomes_antigos)
        bruto = next((brutos[c] for c in chaves if brutos.get(c) is not None), None)
        if bruto is None:
            dados[nome] = None
            ausentes.append(nome)
            continue
        valor = validar_valor(bruto, campo)
        if valor is None:
            logger.warning(f"Campo '{nome}' inválido descartado: {bruto!r}")
            invalidos.append(nome)
        dados[nome] = valor
    return dados, invalidos, ausentes
# ----------------------------------------------------------------------
# Modelos
# ----------------------------------------------------------------------
class Registro(BaseModel):
    """Leitura em memória / WebSocket (todos os sensores + metadados)."""
    temperatura: float | None = None
    temperatura_bmp280: float | None = None
    umidade: float | None = None
    pressao: float | None = None
    qualidade_ar: int | None = None
    mq135_tensao_sensor: float | None = None
    mq135_rs_r0: float | None = None
    co2_equivalente_ppm_estimado: float | None = None
    mq135_status_calibracao: Literal["calibrado", "pendente", "erro"] | None = None
    luminosidade: int | None = None
    gas_digital: int | None = None
    recebido_em: datetime
    intervalo_desde_anterior_s: float | None = None
    status_frequencia: Literal[
        "primeira_leitura",
        "mais_rapido_que_o_configurado",
        "atrasado",
        "normal",
    ]
    campos_invalidos: list[str] = Field(default_factory=list)
    campos_ausentes: list[str] = Field(default_factory=list)
    campos_suspeitos: list[str] = Field(default_factory=list)
    classificacao: Literal["valida", "parcial", "suspeita"] = "valida"
    avisos: list[str] = Field(default_factory=list)
class LeituraBanco(BaseModel):
    """Linha da tabela 'leituras' (o que o histórico devolve)."""
    id_leitura: int | None = None
    data_hora: datetime | None = None
    temperatura: float | None = None
    umidade: float | None = None
    pressao: float | None = None
    qualidade_ar: float | None = None
    mq135_tensao_sensor: float | None = None
    mq135_rs_r0: float | None = None
    co2_equivalente_ppm_estimado: float | None = None
    mq135_status_calibracao: str | None = None
    luminosidade: float | None = None
# Preenchidos quando SALVAR_EXTRAS_NO_BANCO=true.
    temperatura_bmp280: float | None = None
    gas_digital: int | None = None
# ----------------------------------------------------------------------
# Anomalias e frequência
# ----------------------------------------------------------------------
VARIACOES_MAXIMAS = [
    ("temperatura", 3, "Variação brusca na temperatura DHT22"),
    ("temperatura_bmp280", 3, "Variação brusca na temperatura BMP280"),
    ("umidade", 20, "Variação brusca na umidade"),
    ("pressao", 3, "Variação brusca na pressão"),
]
def detectar_anomalias(dados: dict, anterior: Registro | None, intervalo) -> list[str]:
    avisos = []
    t_dht = dados["temperatura"]
    t_bmp = dados["temperatura_bmp280"]
    if t_dht is not None and t_bmp is not None and abs(t_dht - t_bmp) > 8:
        avisos.append("Grande diferença entre os sensores de temperatura")
# Só compara com a leitura anterior se ela for recente.
    if anterior is None or intervalo is None or not 0 < intervalo <= 15:
        return avisos
    for campo, limite, mensagem in VARIACOES_MAXIMAS:
        atual = dados[campo]
        antigo = getattr(anterior, campo)
        if atual is not None and antigo is not None and abs(atual - antigo) > limite:
            avisos.append(mensagem)
    return avisos
def verificar_frequencia(intervalo) -> str:
    if intervalo is None:
        return "primeira_leitura"
    tolerancia_baixa = max(1.0, INTERVALO_ESPERADO * 0.5)
    tolerancia_alta = max(3.0, INTERVALO_ESPERADO)
    if intervalo < INTERVALO_ESPERADO - tolerancia_baixa:
        return "mais_rapido_que_o_configurado"
    if intervalo > INTERVALO_ESPERADO + tolerancia_alta:
        return "atrasado"
    return "normal"
# ----------------------------------------------------------------------
# WebSocket (gerenciador de conexões)
# ----------------------------------------------------------------------
class GerenciadorWS:
    def __init__(self):
        self.conexoes: set[WebSocket] = set()
    async def conectar(self, ws: WebSocket):
        await ws.accept()
        self.conexoes.add(ws)
    def desconectar(self, ws: WebSocket):
        self.conexoes.discard(ws)
    async def _enviar(self, ws: WebSocket, texto: str):
        try:
            await asyncio.wait_for(ws.send_text(texto), timeout=2)
        except Exception:
            self.desconectar(ws)
    async def broadcast(self, mensagem: dict):
        if not self.conexoes:
            return
        texto = json.dumps(mensagem)
        await asyncio.gather(*(self._enviar(ws, texto) for ws in list(self.conexoes)))
gerenciador = GerenciadorWS()
def publicar_ws(mensagem: dict):
    """Chamado da thread do MQTT: agenda o broadcast no loop do FastAPI."""
    if loop_principal is not None and loop_principal.is_running():
        asyncio.run_coroutine_threadsafe(
            gerenciador.broadcast(mensagem), loop_principal
        )
# ----------------------------------------------------------------------
# Gravação no Supabase
# ----------------------------------------------------------------------
PREFIXOS_ERRO_PERMANENTE = ("42", "22", "23", "PGRST1", "PGRST2")
def erro_permanente(erro: Exception) -> bool:
    """Erros de SQL/dados não adianta repetir; erros de rede sim."""
    if isinstance(erro, APIError):
        return str(erro.code or "").startswith(PREFIXOS_ERRO_PERMANENTE)
    return False
def salvar_nao_gravadas(lote: list[dict]):
    try:
        with open(ARQUIVO_NAO_GRAVADAS, "a", encoding="utf-8") as arquivo:
            for registro in lote:
                arquivo.write(json.dumps(registro) + "\n")
        logger.error(f"{len(lote)} leituras salvas em {ARQUIVO_NAO_GRAVADAS.name}.")
    except OSError as erro:
        logger.error(f"Não foi possível salvar as leituras pendentes: {erro}")
def escritor_supabase():
    """Agrupa leituras e grava no Postgres sem bloquear o MQTT."""
    lote: list[dict] = []
    espera = 1.0
    while True:
        if not lote:
            try:
                lote.append(fila_gravacao.get(timeout=1))
            except queue.Empty:
                if parar_escritor.is_set():
                    break
                continue
            while len(lote) < TAMANHO_LOTE:
                try:
                    lote.append(fila_gravacao.get_nowait())
                except queue.Empty:
                    break
        try:
            # Defesa final: nunca enviar avisos ou metadados para leituras.
            lote = [
                {chave: valor for chave, valor in registro.items()
                 if chave in COLUNAS_ESCRITA}
                for registro in lote
            ]
            cliente_supabase.table(SUPABASE_TABELA).insert(lote).execute()
            estatisticas["gravadas"] += len(lote)
            estatisticas["ultimo_sucesso"] = datetime.now(timezone.utc).isoformat()
            estatisticas["ultimo_erro"] = None
            logger.info(f"Gravadas {len(lote)} leituras em '{SUPABASE_TABELA}'.")
            lote = []
            espera = 1.0
        except Exception as erro:
            estatisticas["falhas"] += 1
            estatisticas["ultimo_erro"] = str(erro)[:300]
            logger.error(f"Falha ao gravar no Supabase ({len(lote)} leituras): {erro}")
            if erro_permanente(erro) or parar_escritor.is_set():
                estatisticas["descartadas"] += len(lote)
                salvar_nao_gravadas(lote)
                lote = []
                continue
            logger.warning(f"Nova tentativa em {espera:.0f}s.")
            parar_escritor.wait(espera)
            espera = min(espera * 2, 30)
def enfileirar_gravacao(registro: Registro):
    linha = {campo: getattr(registro, campo) for campo in COLUNAS_ESCRITA}
    try:
        fila_gravacao.put_nowait(linha)
    except queue.Full:
        estatisticas["descartadas"] += 1
        logger.error("Fila de gravação cheia: salvando leitura no arquivo de pendências.")
        salvar_nao_gravadas([linha])
def enfileirar_alertas(avisos: list[str]):
    """Registra cada tipo de aviso no máximo uma vez a cada 5 minutos."""
    agora = time.monotonic()
    global ALERTAS_ATIVOS
    atuais = set(avisos)
    for mensagem in atuais:
        anterior = ULTIMO_ALERTA.get(mensagem)
# Se a anomalia desapareceu e voltou, registra novo evento.
        if mensagem not in ALERTAS_ATIVOS:
            anterior = None
        if anterior is not None and agora - anterior < INTERVALO_REPETICAO_ALERTA_S:
            continue
        try:
            fila_alertas.put_nowait({"mensagem": mensagem})
        except queue.Full:
            logger.error("Fila de alertas cheia: salvando alerta pendente: %s", mensagem)
            salvar_alertas_pendentes([{"mensagem": mensagem}])
        else:
            ULTIMO_ALERTA[mensagem] = agora
    ALERTAS_ATIVOS = atuais
def salvar_alertas_pendentes(alertas: list[dict]):
    """Guarda localmente alertas que não puderam ser gravados."""
    try:
        with ARQUIVO_ALERTAS_PENDENTES.open("a", encoding="utf-8") as arquivo:
            for alerta in alertas:
                arquivo.write(json.dumps(alerta, ensure_ascii=False) + "\n")
        logger.warning("%d alertas pendentes em %s", len(alertas), ARQUIVO_ALERTAS_PENDENTES.name)
    except OSError:
        logger.exception("Não foi possível salvar os alertas pendentes")
def escritor_alertas_supabase():
    """Grava alertas na tabela existente sem bloquear o MQTT."""
    pendente = None
    espera = 1.0
    while True:
        if pendente is None:
            try:
                pendente = fila_alertas.get(timeout=1)
            except queue.Empty:
                if parar_escritor.is_set():
                    break
                continue
        try:
            cliente_supabase.table("alertas").insert(pendente).execute()
            logger.info("Alerta gravado no Supabase: %s", pendente["mensagem"])
            pendente = None
            espera = 1.0
        except Exception as erro:
            logger.error("Falha ao gravar alerta no Supabase: %s", erro)
            if erro_permanente(erro) or parar_escritor.is_set():
                salvar_alertas_pendentes([pendente])
                pendente = None
                continue
            parar_escritor.wait(espera)
            espera = min(espera * 2, 30)
def recuperar_pendencias(caminho: Path, fila: queue.Queue):
    """Recoloca registros de backup na fila sem apagar itens não processados."""
    if not caminho.exists():
        return
    try:
        linhas = caminho.read_text(encoding="utf-8").splitlines()
    except OSError:
        logger.exception("Falha ao ler backup %s", caminho.name)
        return
    restantes = []
    recuperadas = 0
    for linha in linhas:
        if not linha.strip():
            continue
        try:
            item = json.loads(linha)
            if not isinstance(item, dict):
                raise ValueError("Registro não é objeto JSON")
            # Backups de versões anteriores podem conter avisos/metadados.
            # Leituras só devem usar colunas da tabela leituras.
            if caminho == ARQUIVO_NAO_GRAVADAS:
                item = {chave: valor for chave, valor in item.items()
                        if chave in COLUNAS_ESCRITA}
                if not item:
                    raise ValueError("Leitura pendente sem campos reconhecidos")
            fila.put_nowait(item)
            recuperadas += 1
        except queue.Full:
            restantes.append(linha)
        except (ValueError, TypeError):
            logger.error("Linha inválida preservada em %s", caminho.name)
            restantes.append(linha)
# Só remove o arquivo após enfileirar. Se houver queda entre gravação
# e remoção, alguns itens poderão ser reenviados: operação não é exatamente-uma-vez.
    try:
        if restantes:
            caminho.write_text("\n".join(restantes) + "\n", encoding="utf-8")
        else:
            caminho.unlink(missing_ok=True)
    except OSError:
        logger.exception("Falha ao atualizar backup %s", caminho.name)
    logger.info("Recuperados %d registros de %s", recuperadas, caminho.name)
def verificar_tabela():
    """Testa a tabela e as colunas usadas pela API ao iniciar."""
    try:
        (
            cliente_supabase.table(SUPABASE_TABELA)
            .select(",".join(COLUNAS_LEITURA))
            .limit(1)
            .execute()
        )
        logger.info(f"Tabela '{SUPABASE_TABELA}' OK ({', '.join(COLUNAS_LEITURA)}).")
    except Exception as erro:
        logger.error(
            f"PROBLEMA NA TABELA '{SUPABASE_TABELA}': {erro}. "
            f"Colunas esperadas: {', '.join(COLUNAS_LEITURA)}."
        )
    if not SALVAR_EXTRAS_NO_BANCO:
        logger.info(
            f"Sensores sem coluna no banco (só API/WebSocket): {', '.join(COLUNAS_EXTRAS)}."
        )
# ----------------------------------------------------------------------
# MQTT
# ----------------------------------------------------------------------
def ao_conectar(cliente, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        logger.error(f"Erro de conexão MQTT: {reason_code}")
        return
    logger.info("MQTT conectado com sucesso!")
    cliente.subscribe(MQTT_TOPICO, qos=1)
    logger.info(f"Inscrito no tópico: {MQTT_TOPICO}")
def ao_desconectar(cliente, userdata, disconnect_flags, reason_code, properties):
    if reason_code.is_failure:
        logger.warning(f"MQTT desconectado: {reason_code}")
def ao_receber(cliente, userdata, mensagem):
    global ultima_leitura
    try:
        bruto = json.loads(mensagem.payload.decode("utf-8"))
        if not isinstance(bruto, dict):
            logger.error(f"O payload não é um objeto JSON: {bruto!r}")
            return
        dados, invalidos, ausentes = validar_campos(bruto)
        status_calibracao = bruto.get("mq135_status_calibracao")
        if status_calibracao in ("calibrado", "pendente", "erro"):
            dados["mq135_status_calibracao"] = status_calibracao
        else:
            dados["mq135_status_calibracao"] = None
            if status_calibracao is not None:
                invalidos.append("mq135_status_calibracao")
# A API recalcula o PPM estimado a partir de Rs/R0 para manter
# uma única fórmula no backend e não confiar cegamente no valor recebido.
        dados["co2_equivalente_ppm_estimado"] = calcular_mq135(
            dados.get("mq135_rs_r0")
        ) if status_calibracao == "calibrado" else None
        # O status de calibração é metadado, não uma medição.
        # Não gravar um registro totalmente vazio só por conter status="pendente".
        campos_medidos = [nome for nome in CAMPOS if nome != "co2_equivalente_ppm_estimado"]
        if all(dados.get(nome) is None for nome in campos_medidos):
            logger.warning(
                "Leitura descartada: nenhuma medição válida (%d inválidos; %d ausentes).",
                len(invalidos), len(ausentes),
            )
            return
        agora = datetime.now(timezone.utc)
        with trava:
            anterior = ultima_leitura
            intervalo = (
                (agora - anterior.recebido_em).total_seconds()
                if anterior is not None
                else None
            )
            avisos = detectar_anomalias(dados, anterior, intervalo)
            campos_suspeitos = []
            if "Grande diferença entre os sensores de temperatura" in avisos:
                campos_suspeitos.extend(["temperatura", "temperatura_bmp280"])
            for nome, _, mensagem_aviso in VARIACOES_MAXIMAS:
                if mensagem_aviso in avisos and nome not in campos_suspeitos:
                    campos_suspeitos.append(nome)
            # Suspeito é um dado numericamente válido que merece revisão.
            # Parcial indica pelo menos um campo ausente ou inválido.
            classificacao = (
                "suspeita" if campos_suspeitos else
                "parcial" if invalidos or ausentes else
                "valida"
            )
            registro = Registro(
                **dados,
                recebido_em=agora,
                intervalo_desde_anterior_s=(
                    round(intervalo, 2) if intervalo is not None else None
                ),
                status_frequencia=verificar_frequencia(intervalo),
                campos_invalidos=invalidos,
                campos_ausentes=ausentes,
                campos_suspeitos=campos_suspeitos,
                classificacao=classificacao,
                avisos=avisos,
            )
            ultima_leitura = registro
        novos_alertas = avaliar_alertas(
            dados, registro.avisos, invalidos, status_calibracao,
            int(MQ135_DIGITAL_ATIVO) if MQ135_DIGITAL_ATIVO is not None else None,
        )
        with trava:
            global alertas_ativos_detalhados
            alertas_ativos_detalhados = novos_alertas
        enfileirar_gravacao(registro)
        # Preserva a estrutura existente da tabela alertas (coluna mensagem).
        # Não persiste estados informativos repetitivos de calibração pendente.
        enfileirar_alertas([
            f"[{alerta['gravidade'].upper()}] {alerta['mensagem']}"
            for alerta in novos_alertas if alerta["gravidade"] != "informativo"
        ])
        publicar_ws({"tipo": "alertas", "dados": novos_alertas})
        publicar_ws({
            "tipo": "leitura",
            "dados": registro.model_dump(mode="json"),
        })
        logger.info(f"Nova leitura: {registro.model_dump_json()}")
    except (json.JSONDecodeError, UnicodeDecodeError) as erro:
        logger.error(f"JSON inválido: {erro}")
    except Exception:
        logger.exception("Erro inesperado ao processar a mensagem MQTT")
# ----------------------------------------------------------------------
# Ciclo de vida
# ----------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global cliente_mqtt, cliente_supabase, thread_escritor, thread_alertas, loop_principal
    obrigatorias = [
        ("MQTT_HOST", MQTT_HOST),
        ("MQTT_USERNAME", MQTT_USUARIO),
        ("MQTT_PASSWORD", MQTT_SENHA),
        ("SUPABASE_URL", SUPABASE_URL),
        ("SUPABASE_SERVICE_KEY", SUPABASE_CHAVE),
    ]
    faltando = [nome for nome, valor in obrigatorias if not valor]
    if faltando:
        raise RuntimeError(f"Configure no .env: {', '.join(faltando)}")
    if "*" in CORS_ORIGENS:
        logger.warning(
            "CORS_ORIGINS='*': qualquer site pode chamar a API. "
            "Em produção, defina o domínio do dashboard."
        )
    if not WS_TOKEN:
        logger.warning("WS_TOKEN não definido: o WebSocket está aberto a qualquer cliente.")
    loop_principal = asyncio.get_running_loop()
    logger.info(f"Supabase: {SUPABASE_URL} | tabela: {SUPABASE_TABELA}")
    cliente_supabase = create_client(SUPABASE_URL, SUPABASE_CHAVE)
    verificar_tabela()
    parar_escritor.clear()
    recuperar_pendencias(ARQUIVO_NAO_GRAVADAS, fila_gravacao)
    recuperar_pendencias(ARQUIVO_ALERTAS_PENDENTES, fila_alertas)
    thread_escritor = Thread(
        target=escritor_supabase, name="escritor-supabase", daemon=True
    )
    thread_escritor.start()
    thread_alertas = Thread(
        target=escritor_alertas_supabase, name="escritor-alertas", daemon=True
    )
    thread_alertas.start()
    cliente = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=env("MQTT_CLIENT_ID", "python-estacao-api"),
    )
    cliente.username_pw_set(MQTT_USUARIO, MQTT_SENHA)
    cliente.tls_set(ca_certs=certifi.where(), cert_reqs=ssl.CERT_REQUIRED)
    cliente.reconnect_delay_set(min_delay=1, max_delay=30)
    cliente.on_connect = ao_conectar
    cliente.on_disconnect = ao_desconectar
    cliente.on_message = ao_receber
    cliente_mqtt = cliente
    cliente.connect_async(MQTT_HOST, MQTT_PORTA, keepalive=60)
    cliente.loop_start()
    logger.info("Iniciando o backend da estação...")
    try:
        yield
    finally:
        cliente.disconnect()
        cliente.loop_stop()
        cliente_mqtt = None
        parar_escritor.set()
        thread_escritor.join(timeout=10)
        if thread_alertas is not None:
            thread_alertas.join(timeout=10)
        alertas_restantes = []
        while True:
            try:
                alertas_restantes.append(fila_alertas.get_nowait())
            except queue.Empty:
                break
        if alertas_restantes:
            salvar_alertas_pendentes(alertas_restantes)
        restantes = []
        while True:
            try:
                restantes.append(fila_gravacao.get_nowait())
            except queue.Empty:
                break
        if restantes:
            salvar_nao_gravadas(restantes)
        loop_principal = None
        logger.info("Backend encerrado.")
# ----------------------------------------------------------------------
# Rotas HTTP
# ----------------------------------------------------------------------
app = FastAPI(
    title="API da Estação Meteorológica",
    description="Backend de monitoramento ambiental",
    version="3.4.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGENS,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
@app.get("/")
def inicio():
    return {
        "mensagem": "API da Estação Meteorológica funcionando!",
        "status": "online",
        "websocket": "/ws",
        "docs": "/docs",
    }
@app.get("/leituras", response_model=Registro)
def obter_leituras():
    with trava:
        if ultima_leitura is None:
            raise HTTPException(status_code=404, detail="Nenhuma leitura recebida.")
        return ultima_leitura
@app.get("/leituras/historico", response_model=list[LeituraBanco])
def obter_historico(
    limite: int = Query(default=50, ge=1, le=1000),
    desde: datetime | None = Query(
        default=None, description="ISO 8601, ex.: 2026-11-01T00:00:00Z"
    ),
):
    """Histórico do Postgres, do mais antigo para o mais recente."""
    consulta = (
        cliente_supabase.table(SUPABASE_TABELA)
        .select(",".join(COLUNAS_LEITURA))
        .order("data_hora", desc=True)
        .limit(limite)
    )
    if desde is not None:
        consulta = consulta.gte("data_hora", desde.isoformat())
    try:
        resposta = consulta.execute()
    except Exception as erro:
        logger.error(f"Erro ao consultar o Supabase: {erro}")
        raise HTTPException(status_code=502, detail="Erro ao consultar o banco.")
    return list(reversed(resposta.data))


# ----------------------------------------------------------------------
# Estatísticas das últimas leituras
# ----------------------------------------------------------------------


@app.get("/estatisticas/atual")
def obter_estatisticas(
    limite: int = Query(
        default=60,
        ge=1,
        le=1000,
        description="Quantidade de leituras recentes analisadas."
    ),
):
    """
    Calcula estatísticas das últimas leituras armazenadas no Supabase.
    Sensores digitais são ignorados.
    Valores nulos ou inválidos são contabilizados individualmente.
    """

    if cliente_supabase is None:
        raise HTTPException(
            status_code=503,
            detail="Conexão com o banco ainda não está disponível."
        )

    campos_continuos = [
        "temperatura",
        "temperatura_bmp280",
        "umidade",
        "pressao",
        "qualidade_ar",
        "mq135_tensao_sensor",
        "mq135_rs_r0",
        "co2_equivalente_ppm_estimado",
    ]

    # Considera somente campos efetivamente disponíveis na tabela.
    campos_disponiveis = [
        campo
        for campo in campos_continuos
        if campo in COLUNAS_LEITURA
    ]

    try:
        resposta = (
            cliente_supabase
            .table(SUPABASE_TABELA)
            .select(",".join([
                "id_leitura",
                "data_hora",
                *campos_disponiveis
            ]))
            .order("id_leitura", desc=True)
            .limit(limite)
            .execute()
        )

        # Organiza as leituras da mais antiga para a mais recente.
        leituras = list(reversed(resposta.data or []))

    except Exception as erro:
        logger.error(
            "Erro ao consultar leituras para estatísticas: %s",
            erro
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Não foi possível consultar o banco "
                "para calcular as estatísticas."
            )
        )

    inicio = leituras[0].get("data_hora") if leituras else None
    fim = leituras[-1].get("data_hora") if leituras else None

    resultado = {}

    for campo in campos_disponiveis:

        # Mantém os valores originais para contabilizar ausências
        # e dados inválidos.
        valores_brutos = [
            leitura.get(campo)
            for leitura in leituras
        ]

        # Preserva a correspondência entre valores válidos e metadados.
        leituras_validas = [
            leitura
            for leitura in leituras
            if eh_valor_numerico_valido(leitura.get(campo))
        ]

        estatistica = calcular_estatisticas(valores_brutos)

        # Relaciona os outliers com a leitura original no banco.
        for outlier in estatistica["outliers"]:
            indice = outlier["indice"]

            if 0 <= indice < len(leituras_validas):
                outlier["id_leitura"] = (
                    leituras_validas[indice].get("id_leitura")
                )

                outlier["data_hora"] = (
                    leituras_validas[indice].get("data_hora")
                )

        # IMPORTANTE: esta atribuição precisa ficar dentro do FOR.
        resultado[campo] = estatistica

    return {
        "status": "sucesso",
        "janela": {
            "limite_solicitado": limite,
            "quantidade_leituras": len(leituras),
            "inicio": inicio,
            "fim": fim,
        },
        "sensores_digitais": "ignorados",
        "sensores": resultado,
    }


@app.get("/alertas/ativos")
def obter_alertas_ativos():
    """Estados da última leitura; não garante ausência de risco se dados obsoletos."""
    with trava:
        atual = ultima_leitura
        ativos = [dict(a) for a in alertas_ativos_detalhados]
    idade = ((datetime.now(timezone.utc) - atual.recebido_em).total_seconds()
             if atual is not None else None)
    return {"atualizado_em": atual.recebido_em if atual else None,
            "dados_atuais": idade is not None and idade <= LIMITE_OBSOLETO_S,
            "alertas": ativos, "total": len(ativos)}


@app.get("/alertas/historico")
def obter_historico_alertas(limite: int = Query(default=50, ge=1, le=500)):
    """Consulta a tabela já existente: alertas(mensagem, criado_em)."""
    try:
        resposta = (cliente_supabase.table("alertas").select("*")
                    .order("criado_em", desc=True).limit(limite).execute())
        return resposta.data
    except Exception:
        logger.exception("Falha ao consultar histórico de alertas")
        raise HTTPException(status_code=502, detail="Erro ao consultar alertas no banco")


@app.get("/alertas/regras")
def obter_regras_alertas():
    return {"limites_operacionais_exemplificativos": LIMITES,
            "observacao": "Não são limites de saúde pública. MQ-135 não fornece AQI ou CO2 confiável sem validação externa."}


@app.get("/status")
def status_sistema():
    conectado = cliente_mqtt.is_connected() if cliente_mqtt is not None else False
    with trava:
        ultima = ultima_leitura
    idade = None
    dados_atuais = False
    if ultima is not None:
        idade = round(
            (datetime.now(timezone.utc) - ultima.recebido_em).total_seconds(), 1
        )
        dados_atuais = idade <= LIMITE_OBSOLETO_S
    return {
        "api": "online",
        "mqtt_conectado": conectado,
        "topico": MQTT_TOPICO,
        "ultima_leitura": ultima.recebido_em if ultima else None,
        "idade_ultima_leitura_s": idade,
        "dados_atuais": dados_atuais,
        "frequencia": ultima.status_frequencia if ultima else None,
        "intervalo_esperado_segundos": INTERVALO_ESPERADO,
        "clientes_websocket": len(gerenciador.conexoes),
        "banco": {
            "tabela": SUPABASE_TABELA,
            "colunas_gravadas": COLUNAS_ESCRITA,
            "extras_no_banco": SALVAR_EXTRAS_NO_BANCO,
            "escritor_ativo": bool(thread_escritor and thread_escritor.is_alive()),
            "fila_pendente": fila_gravacao.qsize(),
            "gravadas": estatisticas["gravadas"],
            "falhas": estatisticas["falhas"],
            "descartadas": estatisticas["descartadas"],
            "ultimo_sucesso": estatisticas["ultimo_sucesso"],
            "ultimo_erro": estatisticas["ultimo_erro"],
        },
    }
# ----------------------------------------------------------------------
# Rota WebSocket
# ----------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_leituras(ws: WebSocket, token: str | None = None):
# Compara o token sem depender do prefixo correto.
    if WS_TOKEN and not secrets.compare_digest(token or "", WS_TOKEN):
        await ws.close(code=1008)
        return
    await gerenciador.conectar(ws)
    with trava:
        atual = ultima_leitura
    if atual is not None:
        await ws.send_text(json.dumps({
            "tipo": "leitura",
            "dados": atual.model_dump(mode="json"),
        }))
    try:
        while True:
            texto = await ws.receive_text()
            if texto == "ping":
                await ws.send_text(json.dumps({"tipo": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        gerenciador.desconectar(ws)
# ----------------------------------------------------------------------
# Execução direta
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(env("PORT", "8000")))
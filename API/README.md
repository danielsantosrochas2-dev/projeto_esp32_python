Link do video youtube (https://www.youtube.com/watch?v=kg5lzbKT7Sg)

# API — Estação Meteorológica de Baixo Custo

Backend de monitoramento ambiental desenvolvido em **Python e FastAPI** para receber leituras de uma estação baseada em **ESP32**, processá-las e disponibilizá-las para um dashboard.

> **Escopo deste repositório:** API e seus módulos de regras e estatísticas. O firmware do ESP32 e a interface do dashboard não estão incluídos no pacote analisado.

## Visão geral

```text
ESP32 + sensores
       |
       | JSON via MQTT (TLS)
       v
  Broker MQTT
       |
       v
  API FastAPI (main.py)
       |-- validação individual de sensores
       |-- regras de alerta (alertas_regras.py)
       |-- gravação assíncrona via filas
       |-- estatísticas (estatisticas.py)
       |-- REST + WebSocket
       |
       +----> Supabase (PostgreSQL): leituras e alertas
       |
       +----> Dashboard: consultas HTTP e atualizações por WebSocket
```

### Funcionalidades

- Recebimento de mensagens JSON por MQTT, com comunicação TLS.
- Validação individual de campos e tratamento de leituras parciais.
- Normalização opcional de pressão de Pa para hPa.
- Avaliação de mudanças bruscas e regras de alerta configuradas em módulo separado.
- Gravação das leituras e dos alertas no Supabase por filas e threads dedicadas.
- Tentativas de recuperação e arquivos JSONL de pendências quando a gravação falha.
- Histórico e estatísticas descritivas das leituras.
- Identificação de possíveis outliers pelo **Modified Z-Score**, com mediana e MAD.
- Transmissão de novas leituras e alertas por **WebSocket**.
- Endpoint de status com informações de conexão, idade da última leitura e métricas de gravação.

## Tecnologias

- **Python 3** — lógica do backend (o código utiliza anotações compatíveis com Python 3.10+).
- **FastAPI / Pydantic** — API HTTP, modelos e WebSocket.
- **paho-mqtt** — cliente MQTT.
- **Supabase / PostgreSQL** — persistência de dados.
- **python-dotenv** — configuração por variáveis de ambiente.
- **certifi** — certificados para conexão MQTT via TLS.
- **Uvicorn** — servidor ASGI.

## Estrutura do projeto

```text
estacao-meteorologica/
├── main.py                # API, MQTT, persistência, endpoints e WebSocket
├── estatisticas.py        # Estatísticas e identificação de outliers
├── alertas_regras.py      # Regras operacionais e gravidade dos alertas
├── requirements.txt       # Dependências Python
├── .gitignore             # Arquivos excluídos do Git
└── README.md              # Documentação
```

O pacote também possui arquivos de ambiente local e dependências Node.js. Eles não são necessários para executar o backend Python descrito aqui. O `package.json` contém dependências Supabase para JavaScript, mas não há aplicação JavaScript do dashboard no pacote analisado.

## Instalação local

Requer Python 3.10 ou superior, conexão com um broker MQTT acessível e um projeto Supabase com as tabelas esperadas.

```bash
# Na pasta do projeto
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

No Windows, ative o ambiente com `venv\Scripts\activate`.

### Configuração do ambiente

Crie um arquivo **`.env`** na mesma pasta de `main.py`. Exemplo sem credenciais reais:

```dotenv
# MQTT
MQTT_HOST=seu-broker.example.com
MQTT_PORT=8883
MQTT_USERNAME=seu_usuario
MQTT_PASSWORD=sua_senha
MQTT_TOPIC=estacao/dados
MQTT_CLIENT_ID=python-estacao-api

# Supabase
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_SERVICE_KEY=sua_chave_privada_do_backend
SUPABASE_TABLE=leituras

# API e processamento
PORT=8000
PRESSAO_UNIDADE=hPa
INTERVALO_ESPERADO_S=2
LIMITE_OBSOLETO_S=10
SALVAR_EXTRAS_NO_BANCO=true

# Segurança / origem do dashboard
CORS_ORIGINS=http://localhost:5500
WS_TOKEN=defina_um_token_forte

# Polaridade da saída digital MQ-135: 0, 1 ou deixe sem definir
# MQ135_DIGITAL_ATIVO=0
```

**Nunca publique o `.env`, senhas MQTT ou `SUPABASE_SERVICE_KEY`.** A chave de serviço do Supabase é exclusiva do servidor e não pode ser colocada no dashboard. O `WS_TOKEN` configurado no código é validado por parâmetro de consulta do WebSocket; evite expor esse token em URLs públicas, logs ou repositórios. Para produção, prefira um mecanismo de autenticação apropriado para o frontend.

### Executar

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Abra:

- `http://localhost:8000/` — resposta básica da API.
- `http://localhost:8000/docs` — documentação interativa de rotas HTTP.
- `http://localhost:8000/status` — estado da API, MQTT e gravação.

O servidor depende das configurações MQTT e Supabase e verifica sua conexão com a tabela durante a inicialização.

## Formato dos dados MQTT

O backend assina o tópico indicado em `MQTT_TOPIC` (por padrão, `estacao/dados`) e espera um objeto JSON. Exemplo ilustrativo:

```json
{
  "temperatura": 27.4,
  "temperatura_bmp280": 28.8,
  "umidade": 67.2,
  "pressao": 922.38,
  "qualidade_ar": 332,
  "luminosidade": 1,
  "gas_digital": 0,
  "mq135_tensao_sensor": 0.83,
  "mq135_rs_r0": 2.15,
  "mq135_status_calibracao": "pendente"
}
```

**Importante sobre os campos:**

- `luminosidade` é **digital: somente `0` ou `1`**, conforme o firmware desta instalação.
- `gas_digital` também aceita `0` ou `1`; a polaridade considerada ativa depende de `MQ135_DIGITAL_ATIVO`.
- `qualidade_ar` representa a leitura ADC bruta do MQ-135, validada entre `0` e `4095`. **Não é um índice oficial de qualidade do ar (AQI)**.
- `mq135_status_calibracao` informa a situação de calibração. O backend pode derivar `co2_equivalente_ppm_estimado` de `mq135_rs_r0`, mas essa estimativa não equivale a uma medição seletiva e calibrada de CO₂.
- `pressao` é tratada em hPa, ou convertida de Pa quando `PRESSAO_UNIDADE=pa`.
- Campos ausentes ou inválidos podem ser representados como `null`, permitindo processamento parcial.

O exemplo demonstra o esquema de mensagem, não medições reais nem um teste de sensor.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/` | Identificação básica e status online da API. |
| `GET` | `/leituras` | Última leitura recebida na memória. |
| `GET` | `/leituras/historico` | Histórico do Supabase; aceita `limite` e `desde`. |
| `GET` | `/estatisticas/atual` | Estatísticas das últimas leituras; aceita `limite`. |
| `GET` | `/alertas/ativos` | Alertas associados à última leitura e indicação de dados atuais. |
| `GET` | `/alertas/historico` | Histórico de mensagens da tabela `alertas`. |
| `GET` | `/alertas/regras` | Limites operacionais exemplificativos dos alertas. |
| `GET` | `/status` | Conectividade MQTT, frequência, filas e métricas. |
| `WebSocket` | `/ws` | Notificações de leitura e alertas em tempo real. |

Consultas de exemplo:

```text
GET /leituras/historico?limite=50
GET /estatisticas/atual?limite=60
GET /alertas/historico?limite=20
```

As mensagens WebSocket usam os tipos `leitura` e `alertas`, com o conteúdo no campo `dados`. Quando `WS_TOKEN` estiver configurado, a conexão precisa fornecer o token aceito pelo backend.

## Banco de dados

O código pressupõe tabelas já criadas no Supabase; não há migrações SQL neste pacote.

### Tabela `leituras`

Registra as medições ambientais. Os campos utilizados no código incluem:

- `temperatura`, `temperatura_bmp280`, `umidade`, `pressao`;
- `qualidade_ar`, `luminosidade`, `gas_digital`;
- `mq135_tensao_sensor`, `mq135_rs_r0`, `mq135_status_calibracao`;
- `co2_equivalente_ppm_estimado`.

O histórico pressupõe ainda `id_leitura` e `data_hora`. Os campos extras `temperatura_bmp280` e `gas_digital` são enviados ao banco quando `SALVAR_EXTRAS_NO_BANCO=true`.

### Tabela `alertas`

A API grava a coluna `mensagem` e consulta o histórico utilizando `criado_em`; o banco deve fornecer seus próprios identificadores e valores padrão conforme o esquema existente.

## Processamento estatístico

O módulo `estatisticas.py` calcula quantidade de amostras, dados ausentes, dados inválidos, mínimo, máximo, média, mediana, desvio-padrão populacional e MAD. Os possíveis outliers são identificados pelo **Modified Z-Score**, com limite configurado de `3.5` e pelo menos quatro amostras válidas.

Se o MAD for zero, o módulo informa `outliers_nao_avaliados_mad_zero`: isso significa **classificação estatística indisponível**, não ausência comprovada de anomalias. A identificação de outliers é uma comparação estatística com a janela analisada, não um diagnóstico de risco ambiental.

> **Atenção à versão do ZIP:** o arquivo `estatisticas.py` enviado utiliza o Modified Z-Score padrão; a tolerância adicional por sensor discutida anteriormente **não aparece neste pacote**.

## Alertas

O módulo `alertas_regras.py` mantém limites **operacionais de demonstração** para temperatura e umidade, trata avisos de mudanças bruscas, campos inválidos e estado de calibração do MQ-135. As gravidades disponíveis incluem `informativo`, `atencao` e `critico`.

As regras não representam limites clínicos, critérios legais de exposição ou um índice oficial de qualidade do ar.

## Persistência e recuperação

- Uma fila recebe leituras válidas para gravação no Supabase sem bloquear o callback MQTT.
- Uma segunda fila registra mensagens de alertas.
- Em falhas, registros pendentes podem ser salvos em `leituras_nao_gravadas.jsonl` e `alertas_nao_gravados.jsonl`.
- Ao iniciar, a aplicação procura recuperar essas pendências.

**Limitações:** o salvamento local depende de um sistema de arquivos persistente; sem volume persistente, reinicializações ou substituições da instância hospedada podem apagar os backups. A recuperação também não assegura entrega exatamente uma vez, portanto podem existir duplicatas em casos específicos.

## Hospedagem

O código é uma aplicação FastAPI/ASGI e pode ser implantado em um serviço que execute processos Python contínuos, como Railway, desde que o serviço suporte conexões de saída com o broker MQTT e o Supabase.

Instale as dependências com `pip install -r requirements.txt`, configure as variáveis de ambiente no serviço e utilize um comando de inicialização compatível com a porta fornecida pelo provedor, por exemplo:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Não é necessário enviar o `venv/` do Mac ou `node_modules/` para executar a API Python.

## Segurança e observações de revisão

- No código do pacote, `WS_TOKEN` é opcional; se ausente, o WebSocket não exige esse token.
- Os endpoints HTTP de leitura, histórico e estatísticas não possuem autenticação própria.
- `CORS_ORIGINS` controla acesso por origem no navegador, mas **não é autenticação**.
- É recomendável definir políticas de acesso antes de expor o serviço publicamente.
- A versão incluída no pacote ainda requer revisão de alguns detalhes levantados no projeto, como o tratamento do CO₂ derivado entre campos ausentes, os índices temporais de outliers e o envio do estado inicial de alertas no WebSocket. Não trate essas correções como implementadas apenas com base neste README.

## Licença e manutenção

Não há arquivo de licença de aplicação identificado no pacote. Antes de distribuir publicamente ou receber contribuições, defina uma licença e um processo de manutenção compatíveis com o projeto.

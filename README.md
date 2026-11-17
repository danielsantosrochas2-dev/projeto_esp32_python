# Estação Meteorológica IoT para Cidades Inteligentes

Sistema de monitoramento ambiental desenvolvido com **ESP32 e
MicroPython**, sensores físicos, comunicação MQTT, API em
Python/FastAPI, armazenamento no Supabase (PostgreSQL) e painel de
visualização.

O projeto foi concebido como uma solução de baixo custo para aquisição,
transmissão, validação e consulta de dados ambientais. A estação coleta
variáveis do ambiente por meio de sensores conectados ao ESP32, publica
as leituras por MQTT e encaminha os dados para processamento e
armazenamento na nuvem.

> **Importante:** este README documenta a implementação e a montagem
> descritas no projeto. Valores de calibração e estimativas do MQ-135
> são experimentais e não devem ser interpretados como medições
> laboratoriais ou certificadas.

------------------------------------------------------------------------

## Sumário

-   [1. Visão geral](#1-visão-geral)
-   [2. Objetivos](#2-objetivos)
-   [3. Arquitetura do sistema](#3-arquitetura-do-sistema)
-   [4. Hardware utilizado](#4-hardware-utilizado)
-   [5. Esquema elétrico](#5-esquema-elétrico)
-   [6. Pinagem e conexões](#6-pinagem-e-conexões)
-   [7. Funcionamento dos sensores](#7-funcionamento-dos-sensores)
-   [8. Firmware do ESP32](#8-firmware-do-esp32)
-   [9. Comunicação MQTT e EMQX](#9-comunicação-mqtt-e-emqx)
-   [10. API em Python e FastAPI](#10-api-em-python-e-fastapi)
-   [11. Tratamento e validação dos
    dados](#11-tratamento-e-validação-dos-dados)
-   [12. Banco de dados](#12-banco-de-dados)
-   [13. Dashboard](#13-dashboard)
-   [14. Estrutura lógica dos dados](#14-estrutura-lógica-dos-dados)
-   [15. Configuração e execução](#15-configuração-e-execução)
-   [16. Limitações e cuidados
    técnicos](#16-limitações-e-cuidados-técnicos)
-   [17. Melhorias futuras](#17-melhorias-futuras)
-   [18. Tecnologias utilizadas](#18-tecnologias-utilizadas)

------------------------------------------------------------------------

## 1. Visão geral

A Estação Meteorológica IoT é um protótipo de monitoramento ambiental
que utiliza sensores físicos conectados a um microcontrolador ESP32. O
dispositivo realiza leituras periódicas de temperatura, umidade relativa
do ar, pressão atmosférica, luminosidade e resposta a gases.

As leituras são organizadas em mensagens JSON e transmitidas por Wi-Fi
utilizando o protocolo MQTT. O broker EMQX Cloud recebe as publicações e
permite que a aplicação Python/FastAPI consuma os dados. A API valida e
trata as informações antes de disponibilizá-las e encaminhá-las ao banco
de dados Supabase.

O sistema foi desenvolvido com separação de responsabilidades: o
firmware cuida da aquisição e transmissão; a API centraliza validações e
regras de processamento; o banco persiste os registros; e o dashboard
apresenta as informações ao usuário.

### Variáveis monitoradas

  -----------------------------------------------------------------------
  Variável                Sensor                  Informação obtida
  ----------------------- ----------------------- -----------------------
  Temperatura ambiente    DHT22                   Temperatura em °C

  Umidade relativa        DHT22                   Umidade em %

  Temperatura do sensor   BMP280                  Temperatura em °C
  barométrico                                     

  Pressão atmosférica     BMP280                  Pressão atmosférica,
                                                  normalizada pela API
                                                  para hPa

  Qualidade/resposta do   MQ-135                  Leitura bruta do
  ar                                              conversor ADC

  Razão Rs/R0             MQ-135                  Indicador utilizado no
                                                  processamento
                                                  experimental do sensor

  CO₂ equivalente         MQ-135                  Estimativa experimental
  estimado                                        calculada a partir de
                                                  Rs/R0

  Luminosidade            Módulo LDR digital      Estado lógico 0 ou 1
  -----------------------------------------------------------------------

O sistema utiliza duas leituras de temperatura: uma fornecida pelo DHT22
e outra pelo BMP280. Elas são mantidas como campos distintos, pois são
obtidas por sensores diferentes.

------------------------------------------------------------------------

## 2. Objetivos

### Objetivo geral

Desenvolver uma estação de monitoramento ambiental de baixo custo,
conectada à internet, capaz de adquirir dados de sensores físicos,
transmiti-los em tempo real ou próximo do tempo real e disponibilizá-los
para armazenamento, consulta e visualização.

### Objetivos específicos

-   Integrar sensores ambientais a um ESP32.
-   Desenvolver firmware em MicroPython com aquisição periódica.
-   Utilizar comunicação sem fio por Wi-Fi.
-   Publicar leituras utilizando MQTT.
-   Receber e processar as mensagens por uma API em Python/FastAPI.
-   Validar valores recebidos e identificar dados ausentes ou fora dos
    limites definidos.
-   Armazenar as leituras no Supabase, utilizando PostgreSQL.
-   Disponibilizar os dados para visualização em dashboard.
-   Separar a aquisição física, a comunicação, o processamento e a
    persistência em componentes distintos.

------------------------------------------------------------------------

## 3. Arquitetura do sistema

O fluxo principal de dados é:

``` text
SENSORES FÍSICOS
      |
      v
ESP32 - MicroPython
Aquisição e organização das leituras
      |
      v
Wi-Fi
      |
      v
EMQX CLOUD
Broker MQTT
      |
      v
API PYTHON / FASTAPI
Recepção, validação e processamento
      |
      +--------------------+
      |                    |
      v                    v
SUPABASE / POSTGRESQL    WEBSOCKET / API
Persistência             Distribuição dos dados
                           |
                           v
                       DASHBOARD
                       Visualização
```

### Responsabilidade de cada camada

  -----------------------------------------------------------------------
  Camada                              Responsabilidade
  ----------------------------------- -----------------------------------
  Sensores                            Detectar grandezas e condições
                                      ambientais

  ESP32                               Ler os sensores, organizar os dados
                                      e publicar mensagens

  Wi-Fi                               Fornecer conectividade à estação

  EMQX Cloud                          Receber e distribuir mensagens MQTT

  API FastAPI                         Consumir mensagens, validar,
                                      processar e disponibilizar dados

  Supabase                            Armazenar os registros em
                                      PostgreSQL

  WebSocket/API                       Permitir que o dashboard receba
                                      informações da aplicação

  Dashboard                           Apresentar leituras, histórico e
                                      informações do sistema
  -----------------------------------------------------------------------

A comunicação MQTT desacopla o dispositivo físico da aplicação
consumidora. Assim, o ESP32 publica no broker sem precisar conhecer
diretamente a estrutura interna do banco de dados.

------------------------------------------------------------------------

## 4. Hardware utilizado

### 4.1 Microcontrolador --- ESP32 DevKit V1 WROOM-32

O ESP32 é a unidade central de aquisição e comunicação da estação.

Principais recursos utilizados:

-   Processamento das rotinas do firmware.
-   Comunicação Wi-Fi.
-   Entradas e saídas digitais GPIO.
-   Conversor analógico-digital (ADC), utilizado pelo MQ-135.
-   Interface I²C, utilizada pelo BMP280.
-   Execução do firmware em MicroPython.

### 4.2 DHT22 --- Temperatura e umidade

O DHT22 é utilizado para obter:

-   Temperatura ambiente, em graus Celsius.
-   Umidade relativa do ar, em porcentagem.

O módulo utilizado possui três pinos: alimentação, GND e DATA. A
comunicação com o ESP32 ocorre por um sinal digital no GPIO15.

### 4.3 BMP280 --- Pressão atmosférica e temperatura

O BMP280 fornece:

-   Pressão atmosférica.
-   Temperatura medida pelo próprio sensor.

O módulo utilizado possui cinco pinos identificados como VCC, GND, SCL,
SDA e CSB/SDO (conforme a identificação da placa). A comunicação
implementada utiliza I²C:

-   SDA no GPIO21.
-   SCL no GPIO22.
-   CSB em nível alto para seleção do modo I²C.
-   SDO em GND para selecionar o endereço I²C `0x76`, correspondente à
    configuração utilizada nos testes.

O módulo é alimentado em 3,3 V, pois não possui conversor de nível
lógico. Os sinais I²C devem permanecer compatíveis com a lógica de 3,3 V
do ESP32.

### 4.4 MQ-135 --- Sensor de gases

O MQ-135 é utilizado como sensor de resposta a gases e variações na
composição do ar. O módulo fornece uma saída analógica e uma saída
digital.

Conexões utilizadas:

-   AOUT: GPIO34 do ESP32.
-   DOUT: GPIO23 do ESP32.
-   VCC: alimentação de 5 V.
-   GND: referência comum com o ESP32.

O firmware coleta a leitura do ADC e utiliza os dados de calibração para
obter a razão Rs/R0. A aplicação também trabalha com uma estimativa
experimental de CO₂ equivalente.

**Limitação importante:** o MQ-135 é sensível a diferentes gases e
fatores ambientais. Ele não é um sensor seletivo de dióxido de carbono.
Portanto, o campo `co2_equivalente_ppm_estimado` representa uma
estimativa baseada em uma curva empírica, não uma medição certificada de
concentração de CO₂ nem um índice oficial de qualidade do ar.

**Condição da montagem documentada:** AOUT e DOUT estão ligados
diretamente às entradas do ESP32, sem divisor de tensão ou adaptação de
nível lógico confirmados. Essa condição apresenta risco elétrico. A
entrada do ESP32 não é tolerante a 5 V; se qualquer saída do módulo
ultrapassar a tensão permitida, poderá danificar o microcontrolador. A
montagem deve ser corrigida e as tensões verificadas antes de operação
prolongada.

### 4.5 LDR --- Detecção de luminosidade

O módulo LDR utilizado possui três pinos: VCC, GND e DO.

Nesta implementação, é utilizada a saída digital DO conectada ao GPIO32.
Portanto, o firmware recebe um estado lógico, e não uma medição
analógica contínua de intensidade luminosa.

O valor registrado representa o estado detectado pelo comparador do
módulo. A interpretação de 0 ou 1 como claro/escuro depende do ajuste do
módulo e deve ser confirmada experimentalmente.

------------------------------------------------------------------------

## 5. Esquema elétrico

O diagrama abaixo apresenta as conexões elétricas entre o ESP32,
os sensores, a fonte MB102 e as linhas de alimentação da estação.

![Esquema elétrico da estação meteorológica](docs/esquema-eletrico.png)

------------------------------------------------------------------------

## 6. Pinagem e conexões

A tabela apresenta as conexões informadas para a montagem atual.

  -----------------------------------------------------------------------
  Componente              Pino do módulo          Conexão no ESP32 /
                                                  alimentação
  ----------------------- ----------------------- -----------------------
  DHT22                   DATA                    GPIO15

  DHT22                   VCC                     Linha de alimentação de
                                                  3,3 V, conforme módulo
                                                  utilizado

  DHT22                   GND                     GND comum

  BMP280                  SDA                     GPIO21

  BMP280                  SCL                     GPIO22

  BMP280                  VCC                     3,3 V

  BMP280                  GND                     GND comum

  BMP280                  CSB                     3,3 V (modo I²C)

  BMP280                  SDO                     GND (endereço I²C 0x76)

  LDR                     DO                      GPIO32

  LDR                     VCC                     Linha de alimentação de
                                                  3,3 V, conforme módulo
                                                  utilizado

  LDR                     GND                     GND comum

  MQ-135                  AOUT                    GPIO34 (ligação direta
                                                  na montagem atual)

  MQ-135                  DOUT                    GPIO23 (ligação direta
                                                  na montagem atual)

  MQ-135                  VCC                     5 V

  MQ-135                  GND                     GND comum

  Fonte MB102             Saída de 5 V            VIN do ESP32 e VCC do
                                                  MQ-135

  Fonte MB102             Saída de 3,3 V          Alimentação dos módulos
                                                  que utilizam 3,3 V

  Fonte MB102             GND                     Linha negativa comum da
                                                  protoboard
  -----------------------------------------------------------------------

### Distribuição de alimentação

A estação utiliza um módulo MB102 instalado na protoboard, alimentado
por uma fonte externa. Os jumpers do MB102 selecionam as tensões
disponibilizadas nos trilhos de alimentação.

-   O trilho positivo selecionado em 5 V alimenta o VIN do ESP32 e o VCC
    do MQ-135.
-   O trilho positivo selecionado em 3,3 V alimenta os módulos
    compatíveis com essa tensão.
-   O trilho negativo é utilizado como GND comum para o ESP32 e os
    sensores.

A seleção dos jumpers deve ser conferida fisicamente antes de energizar
o circuito. Não se deve aplicar 5 V aos pinos de alimentação ou sinais
de módulos que aceitam somente 3,3 V.

------------------------------------------------------------------------

## 7. Funcionamento dos sensores

### 7.1 Aquisição de temperatura e umidade --- DHT22

O firmware consulta o DHT22 e obtém temperatura e umidade relativa. Os
valores são organizados no objeto de leitura e enviados junto às demais
variáveis da estação.

### 7.2 Aquisição de pressão e temperatura --- BMP280

O BMP280 é inicializado pela interface I²C. O firmware realiza a leitura
de pressão e temperatura. A pressão é tratada pela API conforme a
unidade configurada, sendo normalizada para hPa quando recebida em Pa.

### 7.3 Aquisição do MQ-135

O MQ-135 fornece uma leitura analógica por meio do ADC do ESP32. O
firmware utiliza o valor bruto e os parâmetros de calibração para
calcular a resistência do sensor e a razão Rs/R0.

A calibração realizada no projeto utiliza amostras do sensor e uma
referência configurada de aproximadamente 420 ppm para a curva
experimental. Esse valor é uma referência adotada no procedimento, não
uma garantia de que o ambiente possua exatamente essa concentração.

O firmware publica informações como:

-   `qualidade_ar`: leitura bruta do ADC.
-   `mq135_rs_r0`: razão calculada entre Rs e R0.
-   `mq135_tensao_sensor`: tensão estimada na saída analógica do sensor,
    considerando o divisor configurado no firmware.
-   `co2_equivalente_ppm_estimado`: estimativa calculada pelo firmware.
-   `mq135_status_calibracao`: estado informado pelo procedimento de
    calibração.
-   `gas_digital`: estado lógico da saída DOUT.

Os valores de tensão e calibração dependem da configuração elétrica e
dos parâmetros utilizados no firmware. A compensação de divisor
configurada no software não substitui a existência física de um divisor
de tensão.

### 7.4 Aquisição de luminosidade --- LDR

O módulo LDR disponibiliza uma saída digital. O ESP32 lê o estado lógico
pelo GPIO32 e publica o campo `luminosidade`.

Como a saída é digital, o projeto registra o estado do módulo, não lux
nem uma intensidade luminosa analógica calibrada.

------------------------------------------------------------------------

## 8. Firmware do ESP32

O firmware é desenvolvido em MicroPython e executado no ESP32.

A organização do projeto separa a lógica principal e os módulos
responsáveis pelos sensores, evitando concentrar toda a implementação em
um único arquivo.

### Responsabilidades do firmware

1.  Inicializar os sensores.
2.  Verificar a comunicação e a disponibilidade dos componentes.
3.  Conectar o ESP32 à rede Wi-Fi.
4.  Estabelecer a conexão com o broker MQTT.
5.  Executar as leituras periódicas.
6.  Organizar os valores em uma estrutura JSON.
7.  Publicar as mensagens no tópico MQTT.
8.  Tratar falhas de conexão e permitir tentativas de reconexão.

O intervalo de leitura definido para a rotina principal é de **2.000
milissegundos (2 segundos)**.

A implementação prioriza temporização não bloqueante com rotinas
assíncronas, evitando que a espera de um sensor impeça
desnecessariamente a execução das demais tarefas.

### Exemplo de mensagem publicada

Exemplo ilustrativo de estrutura compatível com as mensagens utilizadas
pelo firmware:

``` json
{
  "qualidade_ar": 521,
  "temperatura": 27.6,
  "mq135_rs_r0": 0.63485,
  "mq135_status_calibracao": "estimativa_experimental",
  "temperatura_bmp280": 28.84,
  "umidade": 63.9,
  "pressao": 923.42,
  "gas_digital": 1,
  "mq135_tensao_sensor": 1.1462,
  "co2_equivalente_ppm_estimado": 410.3,
  "luminosidade": 1
}
```

Os números acima são apenas um exemplo de payload, não uma leitura atual
ou valor de referência permanente.

------------------------------------------------------------------------

## 9. Comunicação MQTT e EMQX

A comunicação entre o ESP32 e a aplicação utiliza MQTT, protocolo leve
de publicação e assinatura de mensagens.

O **EMQX Cloud** atua como broker MQTT.

### Fluxo de comunicação

1.  O ESP32 conecta-se à rede Wi-Fi.
2.  O firmware estabelece conexão com o broker EMQX Cloud.
3.  O ESP32 publica as leituras em formato JSON.
4.  A API Python assina o tópico correspondente.
5.  Ao receber uma publicação, a API interpreta e valida o conteúdo.

### Tópico utilizado

``` text
estacao/dados
```

### Formato de mensagem

As mensagens são codificadas em JSON, permitindo que a API identifique
cada variável pelo nome do campo.

As credenciais do broker e demais dados de conexão devem ser mantidos em
configurações privadas ou variáveis de ambiente. Não publique usuário,
senha, certificados ou tokens no repositório.

------------------------------------------------------------------------

## 10. API em Python e FastAPI

A API foi desenvolvida em Python utilizando FastAPI e integra o
recebimento MQTT, o processamento das leituras e a comunicação com o
banco de dados.

### Responsabilidades

-   Conectar-se ao broker MQTT.
-   Receber mensagens publicadas pela estação.
-   Decodificar o JSON recebido.
-   Validar tipos, limites e campos.
-   Tratar valores inválidos, ausentes ou não finitos.
-   Converter unidades quando necessário.
-   Aplicar a regra de cálculo experimental do MQ-135.
-   Disponibilizar leituras para os consumidores da aplicação.
-   Enfileirar e persistir registros no Supabase.
-   Disponibilizar informações ao dashboard por meio dos mecanismos de
    comunicação implementados, incluindo WebSocket.

### Validação dos campos

A API possui regras específicas para os campos recebidos, incluindo
limites mínimos e máximos, validação de números inteiros e rejeição de
valores inválidos.

Também são reconhecidos alguns nomes antigos de campos para
compatibilidade com versões anteriores do firmware, como:

  Nome antigo         Campo utilizado
  ------------------- ----------------------
  `temperatura_bmp`   `temperatura_bmp280`
  `mq135` ou `gas`    `qualidade_ar`
  `mq135_digital`     `gas_digital`

O firmware atual deve priorizar os nomes padronizados.

### Tratamento do MQ-135 na API

A API recebe a razão `mq135_rs_r0` e utiliza a curva empírica
configurada no backend para calcular `co2_equivalente_ppm_estimado`
quando o status de calibração permite.

A fórmula atualmente utilizada é:

``` python
ppm = 116.602 * (float(razao_rs_r0) ** -2.769)
```

O resultado é tratado como CO₂ equivalente estimado. A API não
transforma o MQ-135 em um sensor seletivo de CO₂.

O campo `mq135_status_calibracao` aceita os estados:

-   `calibrado`
-   `pendente`
-   `erro`
-   `estimativa_experimental`

Quando o status não corresponde a um estado aceito, a API não deve
tratar a estimativa como calibrada.

------------------------------------------------------------------------

## 11. Tratamento e validação dos dados

O tratamento dos dados tem como finalidade reduzir erros de
interpretação, impedir que valores claramente inválidos sejam
persistidos e manter consistência entre as camadas.

Entre as verificações implementadas estão:

-   Verificação de que o payload recebido é um objeto JSON.
-   Validação de campos numéricos.
-   Rejeição de valores booleanos quando um número é esperado.
-   Rejeição de valores não finitos, como NaN e infinito.
-   Aplicação de limites físicos e operacionais definidos por campo.
-   Validação de campos inteiros, como estados digitais e leitura bruta
    do ADC.
-   Conversão de pressão para hPa conforme a unidade configurada.
-   Tratamento específico do status de calibração do MQ-135.

### Limites configurados na API

Os limites abaixo correspondem às regras de validação documentadas na
implementação revisada:

  Campo                              Limite mínimo   Limite máximo
  -------------------------------- --------------- ---------------
  `temperatura`                             -40 °C           80 °C
  `temperatura_bmp280`                      -40 °C           85 °C
  `umidade`                                    0 %           100 %
  `pressao`                                300 hPa        1100 hPa
  `qualidade_ar`                                 0            4095
  `mq135_tensao_sensor`                     0,01 V           5,0 V
  `mq135_rs_r0`                           0,000001          100000
  `co2_equivalente_ppm_estimado`                 0          100000
  `luminosidade`                                 0               1
  `gas_digital`                                  0               1

Esses limites são critérios de validação de software. Eles não
representam, por si só, a faixa de precisão ou calibração metrológica
dos sensores.

------------------------------------------------------------------------

## 12. Banco de dados

O armazenamento utiliza **Supabase**, com banco de dados PostgreSQL.

A API organiza os campos de gravação por meio de listas de colunas,
separando os campos principais dos campos extras. Essa organização
controla quais informações são efetivamente enviadas à tabela de
leituras.

### Tabela `leituras`

Campos principais utilizados:

  -----------------------------------------------------------------------
  Coluna                              Descrição
  ----------------------------------- -----------------------------------
  `temperatura`                       Temperatura do DHT22

  `umidade`                           Umidade relativa do DHT22

  `pressao`                           Pressão atmosférica

  `qualidade_ar`                      Leitura bruta do ADC do MQ-135

  `luminosidade`                      Estado digital do módulo LDR

  `mq135_tensao_sensor`               Tensão estimada na saída do sensor

  `mq135_rs_r0`                       Razão Rs/R0

  `co2_equivalente_ppm_estimado`      Estimativa experimental de CO₂
                                      equivalente

  `mq135_status_calibracao`           Estado da calibração

  `data_hora`                         Data e hora do registro
  -----------------------------------------------------------------------

Campos extras habilitados na configuração atual:

  Coluna                 Descrição
  ---------------------- --------------------------------
  `temperatura_bmp280`   Temperatura obtida pelo BMP280
  `gas_digital`          Estado digital do MQ-135

A persistência dos campos extras depende da configuração
`SALVAR_EXTRAS_NO_BANCO`. Quando habilitada, as colunas correspondentes
precisam existir na tabela do Supabase.

### Tabela `alertas`

A tabela de alertas utilizada pela aplicação contém:

  Coluna        Descrição
  ------------- -------------------------
  `id`          Identificador do alerta
  `mensagem`    Conteúdo do alerta
  `criado_em`   Data e hora de criação

A API mantém a separação entre a estrutura dos registros de leitura e a
estrutura dos alertas.

### Persistência

A aplicação utiliza uma fila de gravação e uma rotina responsável por
inserir os registros no Supabase. A separação entre recepção MQTT e
persistência evita que a rotina de recebimento dependa diretamente da
execução de cada operação de banco.

Os nomes das colunas e o particionamento dos campos devem permanecer
consistentes entre a API e a tabela PostgreSQL.

------------------------------------------------------------------------

## 13. Dashboard

O dashboard é a camada de visualização da estação. Ele consome os dados
disponibilizados pela API para apresentar as condições monitoradas.

A arquitetura prevê a atualização das informações por comunicação em
tempo real ou próximo do tempo real, utilizando os mecanismos
disponibilizados pela API, incluindo WebSocket.

As informações que podem ser apresentadas incluem:

-   Temperatura ambiente.
-   Umidade relativa.
-   Pressão atmosférica.
-   Resposta do sensor MQ-135.
-   Estimativa experimental de CO₂ equivalente.
-   Estado de luminosidade.
-   Histórico das leituras.
-   Alertas gerados pelas regras da aplicação.

A apresentação dos dados deve distinguir claramente leituras diretas dos
sensores e valores calculados ou estimados.

------------------------------------------------------------------------

## 14. Estrutura lógica dos dados

A mensagem publicada pelo ESP32 contém os campos de aquisição e os
indicadores necessários para o processamento.

### Campos de aquisição

  Campo                  Origem
  ---------------------- ------------------------
  `temperatura`          DHT22
  `umidade`              DHT22
  `temperatura_bmp280`   BMP280
  `pressao`              BMP280
  `qualidade_ar`         MQ-135 / ADC
  `gas_digital`          MQ-135 / saída digital
  `luminosidade`         LDR / saída digital

### Campos de processamento do MQ-135

  -----------------------------------------------------------------------
  Campo                               Finalidade
  ----------------------------------- -----------------------------------
  `mq135_tensao_sensor`               Registrar a tensão estimada da
                                      saída analógica

  `mq135_rs_r0`                       Informar a razão entre resistência
                                      do sensor e resistência de
                                      referência

  `co2_equivalente_ppm_estimado`      Informar a estimativa experimental
                                      calculada

  `mq135_status_calibracao`           Identificar a condição da
                                      calibração
  -----------------------------------------------------------------------

A API valida os dados e organiza os campos de acordo com a estrutura de
persistência configurada. O payload MQTT e o registro persistido possuem
finalidades diferentes: o primeiro transporta os dados da estação; o
segundo segue as colunas e regras de gravação do banco.

------------------------------------------------------------------------

## 15. Configuração e execução

Esta seção apresenta o fluxo geral de preparação. Os valores privados de
conexão devem ser preenchidos com as configurações reais do ambiente.

### 15.1 Firmware

Requisitos:

-   ESP32 DevKit V1 WROOM-32.
-   Firmware MicroPython compatível com a placa.
-   Drivers dos sensores utilizados.
-   Rede Wi-Fi disponível.
-   Credenciais e parâmetros de conexão MQTT.

A instalação e transferência dos arquivos do firmware podem ser
realizadas com ferramentas compatíveis com MicroPython, como `mpremote`.

Exemplo de identificação da placa:

``` bash
py -m mpremote connect COM4 repl
```

A porta `COM4` é a utilizada nos testes registrados; ela pode mudar
conforme a porta USB e o computador.

### 15.2 Broker MQTT

Configurar no firmware os parâmetros de conexão fornecidos pelo EMQX
Cloud:

-   Endereço do broker.
-   Porta MQTT/TLS correspondente à configuração.
-   Usuário.
-   Senha.
-   Certificados, quando exigidos.
-   Tópico de publicação.

Não inserir credenciais reais diretamente neste README.

### 15.3 API

Requisitos gerais:

-   Python compatível com as dependências do projeto.
-   FastAPI.
-   Cliente MQTT utilizado pela aplicação.
-   Biblioteca de integração com Supabase.
-   Configurações de conexão ao EMQX e ao Supabase.

As variáveis de ambiente devem ser configuradas no ambiente de execução.
Não versionar arquivos `.env` com credenciais reais.

### 15.4 Supabase

Para executar a persistência, é necessário:

1.  Disponibilizar um projeto Supabase.
2.  Criar a tabela `leituras` com as colunas esperadas pela API.
3.  Criar a tabela `alertas` conforme a estrutura utilizada.
4.  Configurar as credenciais e URL de acesso no ambiente da API.
5.  Conferir a configuração de gravação dos campos extras.

### 15.5 Dashboard

O dashboard deve apontar para os endereços e rotas disponibilizados pela
API no ambiente de execução. Os endereços locais ou de hospedagem devem
ser configurados conforme o ambiente utilizado.

------------------------------------------------------------------------

## 16. Limitações e cuidados técnicos

### 16.1 MQ-135

O MQ-135 possui sensibilidade cruzada a diferentes gases e sofre
influência de fatores como temperatura, umidade, tempo de aquecimento,
alimentação e características do circuito.

A estimativa de CO₂ equivalente depende da curva empírica e do
procedimento de calibração adotado. Ela não substitui um sensor NDIR ou
equipamento certificado para medição de CO₂.

### 16.2 Segurança elétrica do MQ-135

Na montagem documentada, AOUT está ligado diretamente ao GPIO34 e DOUT
diretamente ao GPIO23. O ESP32 utiliza lógica de 3,3 V e suas GPIOs não
devem receber 5 V.

É necessário medir as tensões de AOUT e DOUT em diferentes condições de
operação e implementar adaptação elétrica adequada antes de considerar a
montagem segura. O divisor aplicado à saída analógica não protege
automaticamente a saída digital.

### 16.3 BMP280

O módulo utilizado não possui conversor de nível lógico. Sua alimentação
e seus sinais devem respeitar os níveis elétricos de 3,3 V.

### 16.4 LDR digital

A saída DO representa um estado lógico determinado pelo circuito
comparador do módulo. Sem calibração e conversão apropriadas, ela não
representa uma medição em lux.

### 16.5 Alimentação

A fonte MB102 deve ser utilizada respeitando a tensão selecionada em
cada trilho e a corrente disponível. Antes de conectar os módulos,
conferir a posição dos jumpers e medir as saídas com instrumento
apropriado.

------------------------------------------------------------------------

## 17. Melhorias futuras

Possíveis evoluções técnicas do projeto:

-   Implementar adaptação de nível e proteção elétrica adequada nas
    saídas do MQ-135.
-   Validar a calibração do MQ-135 com procedimento documentado e
    referência apropriada.
-   Avaliar um sensor NDIR caso seja necessária medição mais confiável
    de CO₂.
-   Registrar e monitorar falhas de comunicação e reconexão.
-   Ampliar os testes de integridade e consistência dos dados.
-   Documentar testes de bancada e comparar leituras com instrumentos de
    referência.
-   Melhorar a observabilidade da API, do broker e do processo de
    persistência.
-   Evoluir o dashboard com filtros, histórico e indicadores de estado
    dos sensores.

------------------------------------------------------------------------

## 18. Tecnologias utilizadas

  Tecnologia / componente    Aplicação
  -------------------------- -------------------------------------------
  ESP32 DevKit V1 WROOM-32   Microcontrolador
  MicroPython                Firmware embarcado
  DHT22                      Temperatura e umidade
  BMP280                     Pressão e temperatura
  MQ-135                     Resposta a gases
  LDR digital                Detecção de luminosidade
  MB102                      Distribuição de alimentação na protoboard
  Wi-Fi                      Conectividade
  MQTT                       Transporte de mensagens
  EMQX Cloud                 Broker MQTT
  Python                     Processamento e integração
  FastAPI                    API da aplicação
  Supabase / PostgreSQL      Persistência dos dados
  WebSocket                  Atualização de dados para clientes
  Dashboard web              Visualização das informações

------------------------------------------------------------------------

## Considerações finais

O projeto integra hardware, firmware embarcado, comunicação IoT,
processamento de dados, armazenamento em nuvem e visualização. Sua
arquitetura separa as responsabilidades de cada camada, permitindo
testar e evoluir os componentes de forma independente.

Os resultados devem ser interpretados considerando as características e
limitações dos sensores utilizados, principalmente o MQ-135. A
documentação distingue os valores medidos diretamente, os estados
digitais e as estimativas calculadas pelo firmware ou pela API.

**Projeto acadêmico --- Estação Meteorológica IoT para Cidades
Inteligentes.**

# PokeScan

Automação do Pokémon GO com PokéGenie: conecta ao celular via ADB Wi-Fi,
calibra a tela e o gesto de swipe, e roda um bot que abre a avaliação, tira
print numerado e desliza para o próximo Pokémon — com swipe humanizado.
Inclui também a raspagem da lista do PokéGenie (rankings IV/PvP) para CSV,
via árvore de UI (`uiautomator`), sem OCR e sem calibração.

## Estrutura das pastas

```
pokescan/
├── setup.bat / setup.ps1   Cria a venv e instala tudo (libs + Tesseract via winget)
├── run.bat                 Abre a GUI
├── requirements.txt
├── README.md
├── app/                    O PROGRAMA (todo o código + dados)
│   ├── gui.py              GUI principal — ponto de entrada
│   ├── config.json         Estado salvo (adb, ip, porta, limite)  [não versionado]
│   ├── redes.json          Perfis de rede (SSID -> ip:porta)      [não versionado]
│   ├── calibracao/         Perfis + templates (gerados na calibração) [não versionado]
│   │   └── swipe_horizontal/   Perfil e imagens do gesto de swipe
│   ├── capturas/           Prints da varredura (subpasta por dia) [não versionado]
│   └── exports/            CSVs gerados pela raspagem do PokéGenie [não versionado]
├── testes/                 Scripts de teste/validação (descartáveis)
└── _lixo/                  Dados antigos + cache — pode APAGAR
```

As pastas/arquivos marcados como **não versionado** contêm dados pessoais
(sua coleção, sua rede, sua tela) e estão no `.gitignore` da raiz do repo.

## Módulos (em `app/`)

Conexão
- `adb_connect.py` — camada ADB Wi-Fi (conectar, tap, swipe, screencap, tcpip 5555).
- `config_store.py` — lê/grava `config.json`.

Visão
- `visao.py` — botão X (círculo + 2 diagonais), botão menu (3 barras horizontais),
  `AVALIAR` via OCR, template matching e delimitação do card branco.
- `detectar_icone.py` — bola laranja do PokéGenie (cor HSV) + zona/ponto de clique.
- `regioes.py` — fatiamento da tela em regiões relativas.
- `imgio.py` — leitura/escrita de imagem segura para caminhos com acento (Windows).

Calibração
- `calibracao.py` — "Calibrar Tela de Jogo" (fluxo de 11 passos: laranja, menu, X,
  card branco, AVALIAR).
- `capturar_modelo.py` — captura um print da tela como modelo.

Swipe humanizado
- `calibrar_swipe.py` — "Calibrar Swipe Horizontal" (grava gestos, gera perfil + testes).
- `swipe_calibra.py` — descoberta do touchscreen, getevent, parser, perfil estatístico.
- `gerar_swipe.py` — gera um swipe novo (bootstrap dos gestos reais + variação).
- `swipe_injecao.py` — injeta o gesto via `sendevent` (fallback: `input swipe`).
- `swipe_util.py` — render dos swipes + montagens + geração dos testes.

Bot (Pokémon GO)
- `varredura.py` — o loop da varredura (acha laranja, clica, print, verifica, X, swipe).
- `automation.py` — reservado.

Raspagem PokéGenie
- `pokegenie.py` — lê a lista "Meus Pokemons" pela árvore de UI (`uiautomator
  dump`): aplica cada filtro selecionado (IV / Grande Liga / Ultra Liga /
  Copinha), rola até o fim extraindo o texto real das linhas, deduplica pela
  identidade (Especie+Forma+Genero+PC+PS+IV+Level), valida a contagem contra o
  título "Meu Pokemon (N)" e salva um CSV largo em `exports/`. A navegação é
  resolvida por `resource-id`/texto + fração de tela (independe da resolução);
  a volta ao topo entre filtros usa replay rápido das rolagens da descida;
  abortar gera CSV `_parcial`. Não usa visão computacional: dentro do
  PokéGenie não há risco de detecção de bot, então vale o caminho mais
  preciso.

## Requisitos

- Python 3.10+ (o Tkinter já vem incluso no instalador oficial do Python
  para Windows — não instale nada à parte).
- Android platform-tools (`adb.exe`) — instalável por `winget install Google.PlatformTools`.
- Tesseract OCR — instalado automaticamente pelo `setup.bat` (só usado na calibração,
  para localizar o texto "AVALIAR").

## Instalação e uso

1. `setup.bat` — cria a `.venv`, instala as dependências e o Tesseract.
2. `run.bat` — abre a GUI.
3. Na GUI: conecte o celular e, na seção **Coleta de Dados**:
   - **Pokémon GO**: rode antes "Calibrar Tela de Jogo" e "Calibrar Swipe
     Horizontal", defina o limite de Pokémon e clique em **▶ POKEMON GO**
     (o botão vira **■ ABORTAR** enquanto roda — é o mesmo botão).
   - **PokéGenie**: marque os filtros (IV / Grande Liga / Ultra Liga /
     Copinha) e clique em **▶ POKEGENIE**. Não precisa de calibração.
     O CSV sai em `app/exports/`; abortar salva um CSV `_parcial`.

Em qual tela o celular deve estar (com imagens): ver o
[README da raiz](../README.md#em-qual-tela-deixar-o-celular) — Pokémon GO na
tela de info do primeiro Pokémon (com a bolinha do PokéGenie sobre o card
branco); PokéGenie na lista "Meus Pokemons".

## Limpeza

A pasta `_lixo/`, a pasta vazia `calibracao/` na raiz e o `_moved.txt` podem ser
apagados (o assistente não tem permissão de deletar; apague pelo Explorer).

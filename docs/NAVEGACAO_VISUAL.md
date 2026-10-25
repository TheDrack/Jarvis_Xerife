# Navegação visual por templates

O adaptador `visual_navigation_adapter` roda no computador que controla a interface. Ele usa capturas recentes, PyAutoGUI/OpenCV e templates PNG fornecidos pelo usuário. O arquivo é carregado pelo descobridor do Nexus pelo nome da classe e do módulo.

## Fluxo de uso

1. Chame `observe_screen` para obter `screenshot_path` e `screenshot_data_url`; examine a captura antes de planejar a ação.
2. Prefira DOM, Playwright ou árvore de acessibilidade quando a aplicação expuser elementos semânticos confiáveis. Use coordenadas/imagem só quando esses caminhos não estiverem disponíveis ou não identificarem o controle.
3. Para cada clique, envie uma receita curta `run_visual_recipe`. Cada passo requer um template do alvo e um template distinto que demonstre o estado após o clique.
4. O adaptador captura a tela imediatamente antes do clique, procura uma única ocorrência com `locateAll(..., confidence=..., grayscale=True)`, clica no centro e aguarda a pós-condição.
5. Se o alvo não existir na biblioteca, estiver ausente/ambíguo ou a pós-condição falhar, a receita para e devolve a captura atual. Mostre-a ao usuário; peça que recorte o controle em Win+Shift+S e só então execute `capture_visual_template` em um turno autorizado. A captura é obtida da área de transferência e salva localmente.
6. Use a nova captura da tela e retome a partir do passo que falhou. Não repita automaticamente uma ação cujo resultado seja incerto.

## Exemplo de receita

```json
{
  "steps": [
    {
      "template_id": "menu_configuracoes",
      "verify_template_id": "painel_configuracoes_aberto",
      "action": "click",
      "confidence": 0.88,
      "wait_ms": 350,
      "verify_timeout_seconds": 2
    }
  ]
}
```

A receita aceita até 20 passos, mas mantenha cada chamada curta. Cada passo precisa de uma pós-condição visual. A correspondência deve ser única; não escolha arbitrariamente entre ocorrências repetidas. Ajuste a confiança apenas dentro de 0.65–0.99. O PyAutoGUI FAILSAFE continua ativo.

## Templates e capturas

- Biblioteca padrão: `%LOCALAPPDATA%\\Jarvis_Xerife\\templates`; substitua com `JARVIS_TEMPLATE_DIR`.
- Capturas: `%LOCALAPPDATA%\\Jarvis_Xerife\\visual-captures`.
- IDs: letras, números, hífen e sublinhado; até 64 caracteres.
- Recorte somente o botão/controle e uma pequena margem; PNG com detalhes visuais, mínimo 8×8 e máximo 1200×800.
- Não sobrescreve IDs existentes. O catálogo `catalog.json` guarda nome, dimensões e data.
- `save_visual_template` aceita imagem base64 até 9 MB. Não inclua capturas de dados sensíveis na biblioteca; as capturas temporárias podem conter informação visível na tela.

## Observação e acompanhamento

`watch_screen` retorna uma sequência finita de quadros capturados por alguns segundos, não um fluxo contínuo de vídeo. No caminho antigo da API/LLM, a captura é devolvida ao cliente e não entra automaticamente numa segunda inferência. No novo caminho MCP, `observe_screen`, `run_visual_recipe` e as ações retornam blocos MCP de imagem diretamente ao modelo; ele pode inspecionar a tela, escolher a próxima ferramenta e repetir o ciclo observe/act/verify. O host MCP recebe as imagens para incluí-las no contexto da chamada.

## Agente local e ponte

O agente local anuncia `visual_templates`, `screen_observation` e `screen_stream` e aceita tarefas visuais pela ponte WebSocket. Para despacho pela API, configure o mesmo segredo `API_KEY_LOCAL` no serviço e no agente local. Use `wss://` fora de uma rede local confiável; nunca registre o segredo. O agente local deve rodar na sessão interativa do Windows, pois serviços/headless podem não enxergar o desktop. A captura via clipboard abre o recorte do Windows e aguarda o usuário concluir.

## Dependências

Instale `requirements/edge.txt` no ambiente do agente; correspondência por confiança depende de OpenCV e a captura/recorte usa Pillow. PyAutoGUI e permissões de captura precisam funcionar na sessão desktop. O adaptador não instala dependências por conta própria.

## Resultados e tratamento

Estados relevantes: `observed`, `observed_sequence`, `completed`, `needs_template`, `not_found`, `ambiguous`, `postcondition_failed`, `invalid_recipe`, `unavailable`. Em falha, inspecione a captura, confirme janela/foco/escala, atualize o template com um novo ID se a aparência mudou e peça ao usuário orientação antes de improvisar. Não reporte sucesso sem `status=completed` ou `observed` conforme a tarefa.


## Acesso MCP local pelo Codex

O servidor independente `app/adapters/edge/jarvis_desktop_mcp.py` expõe a sessão interativa pelo transporte MCP `stdio`. As ferramentas devolvem blocos de imagem MCP, portanto a tela capturada entra diretamente no contexto visual do modelo que chamou a ferramenta. A instalação é local; não requer `API_KEY_LOCAL`, endpoint cloud ou túnel.

Ferramentas: `observe_screen`, `watch_screen`, `read_accessibility_tree`, `run_visual_recipe`, `list_visual_templates`, `capture_visual_template`, `click_at`, `type_text`, `press_key` e `scroll`. A árvore UI Automation é preferível quando disponível. Coordenadas são fallback pontual; confirme a tela e o alvo antes de usá-las. Captura de template requer confirmação explícita e usa o recorte do Windows.

O ambiente do MCP pode ser instalado isoladamente, reutilizando as dependências locais de desktop:

```powershell
python -m venv --system-site-packages .venv
.\.venv\Scripts\python.exe -m pip install -r requirements\edge.txt
```

Registre o subprocesso em `%USERPROFILE%/.codex/config.toml`, ajustando o caminho do clone se necessário:

```toml
[mcp_servers.jarvis_desktop]
command = "C:/Users/USER/.copilot/repos/Jarvis_Xerife/.venv/Scripts/python.exe"
args = ["C:/Users/USER/.copilot/repos/Jarvis_Xerife/app/adapters/edge/jarvis_desktop_mcp.py"]
cwd = "C:/Users/USER/.copilot/repos/Jarvis_Xerife"
```

Depois que o Codex carregar a configuração, o modelo terá acesso a ferramentas locais que enxergam e controlam o desktop. Uma conexão MCP recém-configurada não aparece retroativamente no inventário de ferramentas de uma conversa já aberta; reabra/atualize o Codex para carregar o servidor.


## Acesso por Remote Desktop Commander e outros clientes

O servidor local `jarvis_desktop_mcp.py` usa MCP stdio. Clientes que aceitam um servidor local podem registrá-lo diretamente; isso mantém capturas como blocos de imagem MCP e reaproveita o mesmo catálogo.

O Remote Desktop Commander é um conector MCP remoto de arquivos e processos, não um proxy genérico de servidores MCP. Para usá-lo fora do Codex, o CLI `app/adapters/edge/jarvis_desktop_cli.py` oferece dois modos. O modo `--serve` mantém um processo JSONL no dispositivo; cada `interact_with_process` envia uma ação e recebe um resultado com `request_id`, sem criar um arquivo e iniciar um Python novo a cada passo. A captura JPEG segue como caminho; `read_file` a devolve ao modelo como imagem. O modo `--request` permanece como fallback de execução única.

Exemplo de requisição de observação:

```json
{"action":"observe"}
```

Exemplo de receita:

```json
{
  "action": "run_recipe",
  "steps": [
    {
      "template_id": "settings_button",
      "verify_template_id": "settings_panel",
      "action": "click",
      "confidence": 0.88
    }
  ]
}
```

Procedimento no RDM:
1. Consulte `list_sessions`; reutilize o processo `jarvis_desktop_cli.py --serve` se estiver ativo. Caso contrário, inicie na raiz do clone com `start_process`: `.venv\\Scripts\\python.exe app\\adapters\\edge\\jarvis_desktop_cli.py --serve`.
2. Envie uma requisição JSON por vez com `interact_with_process`, passando o PID retornado, um `request_id` e `wait_for_prompt: true`. A ponte usa o prompt reconhecido `>>>` para devolver o JSON sem iniciar um subprocesso por ação.
3. Leia a resposta e abra `screenshot_path` com `read_file`. Em `watch`, abra primeiro `contact_sheet_path` (uma única imagem com os quadros); leia `frame_paths` individuais só para conferir detalhes.
4. A receita retorna o estado, interrompe em alvo ausente/ambíguo e anexa captura; após sucesso, o CLI também inclui uma captura nova para inspeção.
5. Para cadastrar template, peça o recorte e autorização do usuário; envie `capture_template` no processo e consulte `read_process_output` enquanto a captura aguarda o usuário.
6. Se o processo não estiver disponível, use o modo `--request <caminho>` com um JSON temporário como fallback.

O passo `click_at` exige `user_confirmed: true`; prefira a receita por template. Não coloque credenciais em arquivos de requisição temporários. A skill portátil está em `skills/jarvis-visual-navigation/SKILL.md` e contém os nomes de ferramentas, exemplos e recuperação.

## Rota remota principal: RDC → Aperture → Tailscale → Jarvis

**Prioridade P0.** Ao ligar o PC, o Tailscale deve conectar automaticamente à tailnet. Agentes compatíveis com MCP e autorizados usam o gateway do Aperture: `https://aperture.tail350144.ts.net/v1/mcp`. O conector `jarvis` do Aperture encaminha as chamadas ao upstream privado `https://multimetal.tail350144.ts.net/mcp`, publicado pelo Tailscale Serve para o servidor local `127.0.0.1:8765`.

O Aperture centraliza grants e exposição de ferramentas; as ACLs/identidade do Tailscale limitam o alcance de rede. “Qualquer agente” significa qualquer agente compatível e autorizado, não acesso público irrestrito.

RDC diretamente ao bridge JSONL e Aperture diretamente ao upstream Jarvis são alternativas para situações específicas, por exemplo diagnóstico local ou quando a rota principal não pode ser usada. Não são a metodologia padrão. A sessão visual do Windows ainda precisa estar acessível para ferramentas que controlam a interface gráfica.

Detalhes, boot, segurança e critérios de aceitação: `docs/ACESSO_REMOTO_RDC_APERTURE_TAILSCALE.md`.


## Acesso remoto privado com Tailscale

O servidor MCP oferece também Streamable HTTP para clientes em outros dispositivos do mesmo tailnet. O script `scripts/start_jarvis_tailscale.ps1` inicia o servidor em `127.0.0.1:8765`, deriva uma allowlist Host/Origin do DNS privado da máquina e configura **Tailscale Serve** em HTTPS. O backend permanece preso ao loopback; não usa Funnel nem publica a porta local. A autorização de rede fica sob a identidade dos dispositivos e as ACLs do tailnet.

Pré-requisitos: instalar o cliente oficial Tailscale, entrar na mesma conta/tailnet nos dispositivos cliente e anfitrião, habilitar MagicDNS/HTTPS e aprovar Tailscale Serve no tailnet quando o console oficial solicitar. Em seguida, no PowerShell, rode:

```powershell
.\scripts\start_jarvis_tailscale.ps1
```

O script recusa iniciar se a porta 8765 estiver ocupada ou se detectar outra configuração Tailscale Serve, preservando serviços existentes. Ele imprime o endpoint MCP privado, normalmente `https://<dns-da-maquina>.ts.net/mcp`, e grava os logs em `%LOCALAPPDATA%\\Jarvis_Xerife\\logs`. O servidor controla o desktop interativo; inicie-o apenas quando a sessão Windows estiver conectada e você quiser disponibilizar esse controle no tailnet.

Acesso por Tailscale Serve funciona para clientes HTTP MCP cuja máquina cliente também está no tailnet e tem permissão pelas ACLs. O Remote Desktop Commander hospedado não ganha acesso ao tailnet nem passa a montar servidores MCP arbitrários; para ele, continue usando a ponte de processos JSONL. Para um cliente local, prefira stdio. Funnel não é habilitado: ele exporia o endpoint ao público e exigiria uma camada adicional de autenticação.

O MCP Python usa proteção Host/Origin com valores derivados do DNS Tailscale; não desligue essa proteção para contornar erro 421. O transporte de rede é Streamable HTTP, enquanto stdio continua sendo o padrão local.


## Estado semântico compacto (sem screenshot por clique)

A ação `describe_state` retorna uma visão textual limitada da árvore UI Automation (janela, nome acessível, papel, estado habilitado e AutomationId quando existe). Isso reduz o payload enviado ao agente quando a interface expõe controles acessíveis. Use `read_accessibility_tree` para diagnóstico detalhado e `click_accessibility` ou receitas semânticas para agir; depois confirme a pós-condição. Os IDs `wN-eN` são apenas rótulos de leitura daquela resposta, **não** referências executáveis nem estáveis entre observações.

Esse caminho não captura imagem por padrão. Recorra à captura visual apenas quando a árvore não representar o conteúdo relevante (por exemplo, canvas, imagem ou controle customizado), quando o estado semântico for insuficiente ou quando a verificação falhar. A camada compacta limita elementos e caracteres, não inclui coordenadas e não muda os requisitos de confirmação nem os limites de segurança das ações existentes.

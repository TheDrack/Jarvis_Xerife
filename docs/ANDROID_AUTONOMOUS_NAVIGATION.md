# Navegação via Android — capacidade aditiva

## Princípio arquitetural

Jarvis expõe capacidades por interfaces e ferramentas; o software de conexão é escolha do usuário. Tailscale, Aperture e Remote Desktop Commander (RDC) são exemplos de rotas possíveis, não dependências obrigatórias. O requisito é uma conexão compatível e autorizada entre o agente, o servidor MCP/conector e o dispositivo-alvo.

Separar sempre:
- **Capacidade:** observação e interação com a UI Android.
- **Conector/protocolo:** MCP e adaptadores que expõem operações ao agente.
- **Transporte:** rede, túnel, relay ou software escolhido pelo usuário.

Não documentar um produto específico como pré-requisito universal. A conexão selecionada deve ser verificada em tempo de execução.

## Escopo e preservação

- `app/application/ports/android_navigation.py`: contrato isolado para a capacidade Android.
- `app/adapters/edge/android_navigation_adapter.py`: adaptador de baixo nível ADB para dispositivo selecionado explicitamente.
- O transporte MCP existente deve ser reutilizado. A funcionalidade precisa ser exposta como ferramenta/handler aditivo no servidor MCP; não criar um segundo conector MCP sem necessidade.
- Não substituir nem alterar o comportamento da navegação desktop, `VisualNavigationPort`, os adaptadores Android já existentes, MacroDroid ou o registro de dispositivos.
- Um adaptador isolado não significa que as ferramentas MCP já estejam registradas. Confirme a descoberta de ferramentas antes de declarar integração concluída.

## Seleção de dispositivo e conexão

O agente deve selecionar um dispositivo Android identificado e autorizado explicitamente pelo cadastro confiável do Jarvis ou por configuração de implantação. Não aceite um endereço arbitrário vindo apenas da instrução do usuário como prova de identidade.

A implementação ADB atual usa:
- `JARVIS_ANDROID_DEVICE`: serial/endereço ADB do dispositivo autorizado.
- `JARVIS_ADB_PATH`: caminho opcional para o executável ADB; o padrão é `adb` no PATH.

Essas variáveis configuram o adaptador de baixo nível; elas não registram ferramentas MCP nem alteram automaticamente o destino das ferramentas desktop. O transporte de rede é independente: ADB só funcionará se o dispositivo estiver alcançável, emparelhado/autorizado e com o modo de depuração necessário já habilitado. Uma VPN ou túnel, por si só, não habilita ADB.

Não exponha ADB à internet pública. Não habilite depuração, instale software nem altere configurações do telefone sem autorização explícita.

## Ciclo de navegação

1. Descubra no MCP as ferramentas realmente disponíveis e leia os respectivos esquemas.
2. Resolva o alvo explicitamente: desktop ou Android.
3. Observe a tela atual.
4. Identifique o controle-alvo; prefira APIs de acessibilidade quando disponíveis e use coordenadas/imagem como fallback.
5. Execute uma ação compatível com o esquema da ferramenta.
6. Observe novamente e verifique o resultado. Retorno de sucesso da chamada não prova que a UI atingiu o estado desejado.
7. Se falhar, inspecione o erro e o estado atual antes de tentar de novo.

Permita observação, navegação e cliques comuns necessários para cumprir o pedido. Peça autorização antes de fechar aplicações, excluir dados, efetuar compras, enviar comunicações ou alterar segurança/privacidade sem autorização clara para a ação específica.

## Instalação e integração

O caminho de instalação depende do sistema operacional, do conector e do transporte escolhidos pelo usuário. Primeiro inspecione o ambiente e a documentação de instalação vigente; não imponha Tailscale, Aperture ou RDC.

1. Verifique se o servidor Jarvis MCP está instalado e saudável.
2. Escolha ou reutilize um conector MCP e uma rota de transporte compatível, segura e autorizada.
3. Configure o acesso ao alvo sem expor portas ou credenciais.
4. Emparelhe/autorize o dispositivo Android para o método de controle escolhido, quando necessário.
5. Registre/exponha as novas ferramentas Android de forma aditiva no servidor MCP existente.
6. Teste separadamente: saúde do servidor, handshake MCP, descoberta das ferramentas, conectividade do transporte, acessibilidade do alvo e uma chamada real segura.
7. Execute testes unitários e CI; confirme que as ferramentas desktop continuam inalteradas.

## Estado e limites desta etapa

O adaptador ADB é um componente de baixo nível, não um agente de planejamento semântico. Até que a integração aditiva com o servidor MCP seja implementada e verificada, não alegar que o seletor desktop/Android funciona nem que o ChatGPT já consegue controlar o telefone.

Testes com subprocesses simulados verificam construção de comandos e tratamento de erros, mas não provam conectividade real nem compatibilidade ponta a ponta. O teste real exige dispositivo autorizado e ferramenta MCP descoberta pelo agente.

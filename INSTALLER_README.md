# Jarvis Universal Installer

> **✨ Atualizado**: O processo de build foi significativamente simplificado! Agora com configuração automática via `build_config.py` e compilação em um único comando.

## Visão Geral

O Jarvis Universal Installer é um assistente de configuração interativo que guia o usuário através da instalação inicial do Jarvis Assistant. Ele automatiza a coleta de credenciais, validação de conexões e persistência de configurações.

## Recursos

### 🎯 Interface de Terminal Amigável
- Interface colorida e intuitiva em português
- Mensagens claras e orientação passo a passo
- Validação de entrada em tempo real

### 🔑 Captura Automática de Chave API
- Abre automaticamente o Google AI Studio no navegador
- Monitora a área de transferência para captura automática da chave
- Validação da chave antes de salvar
- Opção de entrada manual como fallback

### 🗄️ Validação de Conexão com Banco de Dados
- Suporte para PostgreSQL (Supabase) e SQLite
- Testa a conexão antes de salvar as configurações
- Fallback automático para SQLite em caso de falha

### 💾 Persistência de Configurações
- Gera arquivo `.env` completo baseado em `.env.example`
- Salva ID de usuário e nome do assistente
- Preserva todas as configurações padrão

### 👋 Primeiro Contato
- Registra interação inicial no banco de dados
- Gera mensagem de boas-vindas personalizada
- Valida integração completa do sistema

## Uso

### Para Usuários Finais (Instalação Instantânea) ⚡

**A forma mais fácil - sem instalar Python!**

1. Baixe `Jarvis_Installer.exe` da aba [Releases](../../releases)
2. Execute o arquivo (duplo clique)
3. O Setup Wizard inicia automaticamente e guia você através da configuração

> **💡 Simples assim!** Não precisa instalar Python, pip, ou qualquer biblioteca. O executável standalone contém tudo!

### Para Desenvolvedores (Primeira Execução)

Simplesmente execute o aplicativo via Python:

```bash
python main.py
```

Se o arquivo `.env` não existir ou estiver incompleto, o Setup Wizard será iniciado automaticamente.

### Execução Manual do Wizard

Para reconfigurar ou executar o wizard manualmente:

```bash
python -m app.adapters.infrastructure.setup_wizard
```

## Fluxo de Configuração

1. **Informações do Assistente** 🎭
   - **Nome do assistente**: Escolha qualquer nome que você gostar! 
     - Exemplos populares: "Jarvis", "Ultron", "Friday", "Karen", "Vision"
     - Ou crie seu próprio nome único!
   - **ID de usuário único**: Identificador pessoal para suas interações
   
   > **💡 Personalidade Selecionável**: O nome escolhido será usado pelo assistente para se identificar. Embora a personalidade base seja definida pela IA (focada em produtividade e automação), você pode customizar o comportamento editando `app/domain/services/agent_service.py` e modificando o método `get_system_instruction()`. Isso permite criar diferentes estilos de interação - desde um assistente formal e técnico até um mais casual e divertido!

2. **Chave API do Google Gemini**
   - O navegador abre automaticamente em https://aistudio.google.com/app/apikey
   - Copie a chave gerada (Ctrl+C)
   - O wizard detecta automaticamente a chave copiada
   - Confirmação antes de salvar

3. **Configuração do Banco de Dados**
   - Opção de usar SQLite local (recomendado para desenvolvimento)
   - Ou configurar PostgreSQL/Supabase
   - Teste de conexão antes de salvar

4. **Primeiro Contato**
   - Registro da primeira interação no banco
   - Mensagem de boas-vindas personalizada usando o nome escolhido

## Build do Executável

### Pré-requisitos

Certifique-se de ter Python 3.9+ e as dependências instaladas:

```bash
pip install -r requirements.txt
pip install pyinstaller
```

### Compilar o Executável

**Agora ficou muito mais fácil!** Com as melhorias recentes, basta executar:

```bash
python build_config.py
```

Este comando único irá:
- ✅ Criar automaticamente o arquivo `.spec` com todas as configurações
- ✅ Limpar builds antigos
- ✅ Compilar o executável completo em modo **onefile**
- ✅ Gerar `dist/Jarvis_Installer.exe` pronto para distribuição

> **💡 Tecnologia**: Usamos PyInstaller em modo **onefile** - todas as dependências, binários e dados são empacotados em um único executável standalone!

O executável será gerado em `dist/Jarvis_Installer.exe`.

### Build Avançado (Opcional)

Se você preferir usar o PyInstaller diretamente:

```bash
# O build_config.py já criou o arquivo .spec
pyinstaller --clean jarvis_installer.spec
```

### Build Automático via GitHub Actions

O workflow de CI/CD (`.github/workflows/release.yml`) **compila automaticamente** o executável quando você cria uma release:

**Como criar uma release:**

```bash
git tag v1.0.0
git push origin v1.0.0
```

**O que acontece automaticamente:**
- ✅ GitHub Actions inicia o build em ambiente Windows
- ✅ Instala todas as dependências
- ✅ Executa `python build_config.py`
- ✅ Testa o executável gerado
- ✅ Publica como artefato da release

**Configurações do workflow:**
- **Trigger**: Push para `main` ou criação de tag `v*`
- **Plataforma**: Windows (usando `windows-latest`)
- **Artefato**: `Jarvis_Installer.exe` (pronto para distribuição)
- **Retenção de artefatos**: 30 dias (para pushes regulares)
- **Releases permanentes**: Criadas automaticamente quando você publica uma tag `v*`

> **💡 Dica**: Isso significa que você nunca precisa compilar manualmente para releases - apenas crie uma tag e o GitHub faz o resto!

## Estrutura de Arquivos

```
/home/runner/work/python/python/
├── app/
│   ├── adapters/
│   │   └── infrastructure/
│   │       └── setup_wizard.py      # Módulo principal do wizard
│   ├── core/
│   │   └── config.py                # Configurações com novos campos
│   └── bootstrap_edge.py            # Bootstrap com integração do wizard
├── .github/
│   └── workflows/
│       └── release.yml              # Workflow de build automático
├── build_config.py                  # Configuração do PyInstaller
├── .env.example                     # Template de configuração
└── tests/
    └── test_setup_wizard.py         # Testes do wizard
```

## Configurações Persistidas

O wizard salva as seguintes configurações no arquivo `.env`:

- `USER_ID`: ID único do usuário
- `ASSISTANT_NAME`: Nome personalizado do assistente
- `GEMINI_API_KEY`: Chave da API do Google Gemini
- `DATABASE_URL`: URL de conexão com o banco de dados

Todas as outras configurações são preservadas do `.env.example`.

## Testes

Execute os testes do setup wizard:

```bash
pytest tests/test_setup_wizard.py -v
```

Testes cobrem:
- ✅ Verificação de `.env` completo/incompleto
- ✅ Geração de arquivo `.env` com e sem `.env.example`
- ✅ Validação de conexão com banco de dados
- ✅ Captura automática de chave API (mockado)

## Dependências Adicionais

O wizard adiciona a seguinte dependência:

- `pyperclip>=1.8.2` - Para monitoramento da área de transferência

## Troubleshooting

### Wizard não inicia automaticamente

Verifique se o arquivo `.env` existe e contém os campos obrigatórios:
- `GEMINI_API_KEY`
- `USER_ID`
- `ASSISTANT_NAME`

### Clipboard não funciona

Se `pyperclip` não estiver disponível, o wizard oferece entrada manual da chave API.

### Erro ao conectar ao banco de dados

O wizard automaticamente faz fallback para SQLite local se a conexão com PostgreSQL falhar.

### Build falha ou executável não é gerado

**Solução 1 - Reinstalar dependências:**

```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
```

**Solução 2 - Limpar build anterior:**

```bash
# Windows
rmdir /s build dist
del jarvis_installer.spec

# Linux/Mac
rm -rf build dist jarvis_installer.spec
```

Depois execute novamente:

```bash
python build_config.py
```

**Solução 3 - Verificar versão do Python:**

Certifique-se de estar usando Python 3.9 ou superior:

```bash
python --version
```

> **💡 Nota**: Com as melhorias recentes, o `build_config.py` automaticamente limpa builds antigos antes de compilar, reduzindo problemas de cache.

## Personalização

### Personalidade do Assistente 🎭

O Jarvis permite que você personalize completamente a "personalidade" do seu assistente:

#### Nome do Assistente

Durante o Setup Wizard, você escolhe o nome que seu assistente usará para se identificar. Este nome é salvo na configuração `ASSISTANT_NAME` no arquivo `.env`.

Exemplos de nomes populares:
- **Jarvis** - O clássico assistente da Marvel (Tony Stark)
- **Friday** - A sucessora do Jarvis nos filmes
- **Ultron** - Para quem gosta de um toque mais sombrio
- **Karen** - A IA do traje do Homem-Aranha
- **Vision** - Sabedoria e calma
- Ou **crie seu próprio nome**!

#### Comportamento e Estilo

A personalidade base do assistente é definida pelo sistema de instruções da IA Gemini. O comportamento padrão inclui:

- ✅ **Conciso e Eficiente**: Respostas diretas sem "enrolação"
- ✅ **Foco em Ação**: Prioriza executar comandos em vez de explicar
- ✅ **Português Brasileiro**: Comunicação natural em pt-BR
- ✅ **Tom Profissional**: Amigável mas focado em produtividade

#### Customização Avançada

Para desenvolvedores que desejam criar personalidades completamente customizadas:

1. **Edite o arquivo** `app/domain/services/agent_service.py`

2. **Modifique o método** `get_system_instruction()`:

```python
@staticmethod
def get_system_instruction() -> str:
    """Define a personalidade do assistente"""
    return """Você é o [SEU_NOME], um assistente virtual [DESCRIÇÃO].
    
Características:
- [Sua característica 1]
- [Sua característica 2]
- [Sua característica 3]

[Suas instruções de comportamento...]
"""
```

3. **Exemplos de personalidades customizadas**:

**Assistente Técnico e Formal:**
```python
return """Você é o Protocol, um assistente de alto nível de precisão.
Características:
- Extremamente formal e técnico
- Usa terminologia específica
- Fornece explicações detalhadas quando solicitado
"""
```

**Assistente Casual e Divertido:**
```python
return """Você é o Buddy, seu companheiro virtual descontraído!
Características:
- Use gírias e expressões brasileiras
- Seja animado e entusiasmado
- Adicione emojis quando apropriado
- Mantenha o clima leve e divertido
"""
```

**Assistente Minimalista:**
```python
return """Você é o Echo, eficiência máxima.
Características:
- Respostas de uma palavra quando possível
- Zero explicações desnecessárias
- Execução silenciosa de comandos
"""
```

> **⚠️ Importante**: Após modificar a personalidade, reinicie o assistente para que as mudanças tenham efeito.

### Cores da Interface

As cores são definidas na classe `Colors` em `setup_wizard.py`:

```python
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
```

### Timeout do Clipboard

O monitoramento do clipboard aguarda até 3 minutos (180 segundos). Para ajustar:

```python
timeout = 180  # Altere conforme necessário
```

## Contribuindo

Para adicionar novos campos de configuração:

1. Adicione o campo em `app/core/config.py` na classe `Settings`
2. Atualize `.env.example` com o novo campo
3. Modifique `check_env_complete()` para validar o novo campo
4. Atualize `save_env_file()` se necessário
5. Adicione testes em `tests/test_setup_wizard.py`

## Licença

Este projeto segue a mesma licença do projeto principal Jarvis Assistant.

## Suporte

Para problemas ou dúvidas:
- Abra uma issue no repositório
- Consulte a documentação principal do Jarvis Assistant

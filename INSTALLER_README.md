# Jarvis Universal Installer

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

### Primeira Execução

Simplesmente execute o aplicativo:

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

1. **Informações do Assistente**
   - Nome do assistente (ex: "Jarvis", "Ultron", "Friday")
   - ID de usuário único

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
   - Mensagem de boas-vindas personalizada

## Build do Executável

### Pré-requisitos

```bash
pip install pyinstaller
pip install -r requirements.txt
```

### Compilar

```bash
python build_config.py
```

O executável será gerado em `dist/Jarvis_Installer.exe`.

### Build Automático via GitHub Actions

O workflow de CI/CD (`.github/workflows/release.yml`) compila automaticamente o executável:

- **Trigger**: Push para `main` ou criação de tag `v*`
- **Plataforma**: Windows
- **Artefato**: `Jarvis_Installer.exe`
- **Retenção**: 30 dias

Para criar uma release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

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

### Build falha

Certifique-se de que todas as dependências estão instaladas:

```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
```

## Personalização

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

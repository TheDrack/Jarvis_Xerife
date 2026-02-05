# Jarvis Voice Assistant

Assistente de voz ativado pela palavra-chave "xerife".

## Estrutura do Projeto

```
.
├── app/                      # Módulos principais da aplicação
│   ├── __init__.py
│   ├── jarvis_engine.py     # Motor de reconhecimento de voz
│   ├── command_processor.py # Processador de comandos
│   └── core/
│       └── config.py        # Configurações
├── main.py                  # Ponto de entrada principal
└── requirements.txt         # Dependências do projeto
```

## Instalação

1. Instale as dependências:
```bash
pip install -r requirements.txt
```

## Uso

Execute o assistente:
```bash
python main.py
```

O assistente aguardará pela palavra de ativação **"xerife"**. Após detectar a palavra-chave, ele processará o próximo comando falado.

### Comandos de Exemplo

- **"xerife teste"** - Executa a ação de teste
- **"xerife exemplo"** - Executa outra ação de exemplo
- **"xerife fechar"** ou **"xerife sair"** - Encerra o assistente

## Arquitetura

### JarvisEngine (`app/jarvis_engine.py`)

Responsável por:
- Reconhecimento de voz (Google Speech Recognition)
- Síntese de voz (pyttsx3)
- Detecção da palavra-chave de ativação "xerife"
- Loop principal de escuta

### CommandProcessor (`app/command_processor.py`)

Responsável por:
- Registro de comandos
- Processamento e roteamento de comandos para ações
- Correspondência de palavras-chave usando limites de palavras (word boundaries)

## Extensão

Para adicionar novos comandos, edite `main.py`:

```python
def minha_acao(parametro):
    # Sua implementação aqui
    print(f"Executando: {parametro}")

# No main():
processor.register_command('meu_comando', minha_acao)
```

## Requisitos

- Python 3.7+
- Microfone funcional
- Conexão com internet (para reconhecimento de voz do Google)

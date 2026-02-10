# Mobile Bridge - Guia de Uso

## 📱 Visão Geral

O Mobile Bridge estende o Local Bridge para suportar dispositivos móveis (smartphones e tablets), permitindo que JARVIS execute tarefas específicas de dispositivos móveis através de sensores e APIs nativas.

## 🎯 Recursos do Mobile Bridge

### Para Dispositivos Móveis

Quando o `device_type=mobile`, o JARVIS pode delegar tarefas focadas em sensores:

1. **Tirar Foto** - Acessa a câmera do dispositivo
2. **Gravar Áudio** - Usa o microfone para gravação
3. **Vibrar para Alerta** - Ativa vibração para notificações
4. **Telemetria de Bateria** - Monitora nível de bateria automaticamente
5. **GPS/Localização** - Obtém coordenadas geográficas

## 🔧 Configuração para Mobile

### Passo 1: Conectar do Navegador Mobile

Abra a HUD JARVIS no navegador do seu celular:

```
https://[SEU-RENDER-URL]
```

### Passo 2: Ativar Telemetria

A telemetria é ativada automaticamente quando você faz login na HUD. O sistema detectará automaticamente que você está em um dispositivo móvel.

### Passo 3: Conceder Permissões

Quando solicitado, conceda as seguintes permissões:

- **Localização** - Para GPS tracking
- **Câmera** - Para tirar fotos (quando solicitado)
- **Microfone** - Para gravar áudio (quando solicitado)

## 📊 Telemetria Automática

A HUD envia telemetria a cada 30 segundos com:

```json
{
  "device_type": "Mobile",
  "battery": {
    "level": 85,
    "charging": false
  },
  "location": {
    "latitude": -23.5505,
    "longitude": -46.6333,
    "accuracy": 10
  },
  "timestamp": "2026-02-10T18:00:00Z"
}
```

## ⚡ Modo de Economia de Energia

Quando a bateria está abaixo de 15% e não está carregando:

1. **Alerta Automático**: JARVIS recebe notificação de bateria crítica
2. **Sugestões**: Sistema sugere desativar funções pesadas
3. **Mensagem na HUD**: Você vê recomendações de economia
4. **Redução Automática**: Frequência de telemetria é reduzida

### Exemplo de Alerta

```
⚠️ ALERTA: Bateria baixa (12%). Sugerindo modo de economia de energia.

Sugestões:
- Desativar funções pesadas da HUD
- Reduzir frequência de telemetria
- Considerar modo de economia de energia
```

## 🎮 Ações Suportadas para Mobile

### 1. Vibração (Mobile API)

```javascript
// Ativar vibração de alerta
if ('vibrate' in navigator) {
    navigator.vibrate([200, 100, 200]); // Padrão de vibração
}
```

### 2. Câmera (Media API)

```javascript
// Tirar foto
async function takePhoto() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
            video: { facingMode: 'environment' } 
        });
        // Capturar frame da stream
    } catch (error) {
        console.error('Camera error:', error);
    }
}
```

### 3. Gravação de Áudio

```javascript
// Gravar áudio
async function recordAudio() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mediaRecorder = new MediaRecorder(stream);
        // Iniciar gravação
    } catch (error) {
        console.error('Microphone error:', error);
    }
}
```

## 🧠 Evolução em Tempo Real

A seção "Evolução em Tempo Real" na HUD mostra:

1. **Próximo Plugin**: Qual plugin JARVIS está planejando codificar
2. **Status**: Estado atual da evolução
3. **Contagem**: Número de plugins dinâmicos já criados

### Exemplo de Display

```
⚙️ Evolução em Tempo Real

🧠 Próximo plugin: advanced_image_recognition
Status: Planejando implementação

Plugins dinâmicos: 3
```

## 🔒 Segurança e Privacidade

### Telemetria

- Dados são enviados apenas quando autenticado
- GPS/localização requer permissão explícita do usuário
- Bateria é lida via API padrão do navegador (não invasiva)

### Câmera e Microfone

- Sempre requer permissão explícita
- Acesso é solicitado apenas quando necessário
- Stream é fechado após uso

## 📱 Suporte de Navegadores

### Completamente Suportado

- ✅ Chrome/Edge Mobile (Android)
- ✅ Safari Mobile (iOS)
- ✅ Firefox Mobile (Android)

### Recursos por Navegador

| Recurso | Chrome | Safari | Firefox |
|---------|--------|--------|---------|
| Battery API | ✅ | ❌ | ✅ |
| Geolocation | ✅ | ✅ | ✅ |
| Camera | ✅ | ✅ | ✅ |
| Microphone | ✅ | ✅ | ✅ |
| Vibration | ✅ | ❌ | ✅ |

**Nota**: Safari no iOS não suporta Battery API nem Vibration API.

## 🔧 Desenvolvimento de Handlers Mobile

Para desenvolvedores que querem estender o Mobile Bridge:

### Exemplo: Handler de Foto

```python
# Em jarvis_local_agent.py (futuro suporte mobile)

async def _handle_take_photo(self, params: Dict) -> Dict:
    """Handle take photo action (mobile only)."""
    if self.device_type != "mobile":
        return {
            "success": False,
            "error": "Camera only available on mobile devices"
        }
    
    # Implementação usando bibliotecas mobile
    # (requer app nativo ou Progressive Web App)
    
    return {
        "success": True,
        "result": "Photo captured",
        "filepath": "path/to/photo.jpg"
    }
```

## 📈 Casos de Uso

### 1. Assistente de Campo

JARVIS detecta que você está em campo (GPS) e bateria baixa, automaticamente:
- Reduz telemetria
- Sugere economia de energia
- Prioriza comandos críticos

### 2. Alerta de Urgência

Bateria < 10% e longe de casa:
- JARVIS sugere encontrar carregador
- Desabilita recursos não essenciais
- Mantém apenas funções críticas

### 3. Contexto Geográfico

JARVIS usa GPS para:
- Sugerir ações baseadas em localização
- Adaptar respostas ao contexto
- Priorizar informações locais

## 🐛 Troubleshooting Mobile

### GPS não funciona

1. Verifique permissões do navegador
2. Certifique-se de estar usando HTTPS (wss://)
3. GPS pode não funcionar em modo anônimo

### Battery API retorna N/A

- Normal no Safari iOS
- Funciona em Chrome/Firefox Android
- Não afeta funcionalidade principal

### Telemetria não enviada

1. Verifique conexão de internet
2. Confirme que está autenticado
3. Veja console do navegador para erros

## 🚀 Próximos Passos

- Implementar Progressive Web App (PWA) para acesso offline
- Adicionar notificações push
- Suporte para compartilhamento de arquivos
- Integração com app nativo (iOS/Android)

---

**🤖 JARVIS Mobile Bridge: Seu assistente IA sempre ao seu lado** 📱🌐

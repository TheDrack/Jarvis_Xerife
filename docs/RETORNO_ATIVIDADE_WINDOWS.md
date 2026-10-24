# Jarvis — retorno de atividade no Windows

O briefing de inicialização continua sendo executado pelo atalho existente `Jarvis - Briefing de Inicializacao.lnk`. Este monitor é complementar: depois de cinco minutos sem teclado/mouse, fala uma saudação apenas quando a entrada volta. O limiar pode ser ajustado com `JARVIS_RETURN_IDLE_SECONDS` (mínimo 30 s).

O monitor usa a API Win32 `GetLastInputInfo`, que observa a sessão interativa que o executa. Por isso, deve iniciar no logon do usuário, não como serviço `SYSTEM`; sessões remotas separadas têm contadores próprios. A voz usa `System.Speech` e seleciona `pt-BR` quando disponível. Falhas são registradas em `%LOCALAPPDATA%\Jarvis_Xerife\logs\return_activity.log`.

## Instalar no usuário atual

Execute no PowerShell como usuário normal (não precisa de administrador):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_jarvis_return_activity.ps1
```

O instalador copia o módulo para `%LOCALAPPDATA%\Jarvis_Xerife\runtime` e cria o atalho `Jarvis - Retorno de Atividade.lnk` na pasta Startup. Não altera nem remove o briefing existente. Para testar rapidamente, defina `JARVIS_RETURN_IDLE_SECONDS=30` no ambiente do atalho e aguarde 30 segundos sem tocar no teclado/mouse; ao voltar, o Jarvis fala uma vez.

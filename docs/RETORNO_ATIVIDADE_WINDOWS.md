# Jarvis â€” retorno de atividade no Windows

O briefing de inicializaÃ§Ã£o continua sendo executado pelo atalho existente `Jarvis - Briefing de Inicializacao.lnk`. Este monitor Ã© complementar: depois de cinco minutos sem teclado/mouse, fala uma saudaÃ§Ã£o apenas quando a entrada volta. O limiar pode ser ajustado com `JARVIS_RETURN_IDLE_SECONDS` (mÃ­nimo 30 s).

O monitor usa a API Win32 `GetLastInputInfo`, que observa a sessÃ£o interativa que o executa. Por isso, deve iniciar no logon do usuÃ¡rio, nÃ£o como serviÃ§o `SYSTEM`; sessÃµes remotas separadas tÃªm contadores prÃ³prios. A voz usa `System.Speech` e seleciona `pt-BR` quando disponÃ­vel. Falhas sÃ£o registradas em `%LOCALAPPDATA%\Jarvis_Xerife\logs\return_activity.log`.

## Instalar no usuÃ¡rio atual

Execute no PowerShell como usuÃ¡rio normal (nÃ£o precisa de administrador):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_jarvis_return_activity.ps1
```

O instalador copia o mÃ³dulo para `%LOCALAPPDATA%\Jarvis_Xerife\runtime` e cria o atalho `Jarvis - Retorno de Atividade.lnk` na pasta Startup. NÃ£o altera nem remove o briefing existente. Para testar rapidamente, defina `JARVIS_RETURN_IDLE_SECONDS=30` no ambiente do atalho e aguarde 30 segundos sem tocar no teclado/mouse; ao voltar, o Jarvis fala uma vez.

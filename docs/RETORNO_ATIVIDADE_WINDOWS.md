# Jarvis - retorno de atividade no Windows

O briefing de inicializacao continua sendo executado pelo atalho existente `Jarvis - Briefing de Inicializacao.lnk`. Este monitor e complementar: depois de cinco minutos sem teclado/mouse, fala uma saudacao apenas quando a entrada volta. O limiar pode ser ajustado com `JARVIS_RETURN_IDLE_SECONDS` (minimo 30 s).

O monitor usa a API Win32 `GetLastInputInfo`, que observa a sessao interativa que o executa. Por isso, deve iniciar no logon do usuario, nao como servico `SYSTEM`; sessoes remotas separadas tem contadores proprios. A voz tenta primeiro o endpoint HTTPS de retorno do Jarvis quando `JARVIS_RETURN_ACTIVITY_KEY` esta configurada no ambiente do usuario ou no arquivo `%LOCALAPPDATA%\Jarvis_Xerife\config\return_activity\return_activity.key`. O segredo e dedicado a esta acao e nunca e registrado em logs. Sem a configuracao, o monitor conserva a fala local via `System.Speech`, selecionando `pt-BR` quando disponivel. Falhas sao registradas em `%LOCALAPPDATA%\Jarvis_Xerife\logs\return_activity.log`.

## Instalar no usuario atual

Execute no PowerShell como usuario normal (nao precisa de administrador):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_jarvis_return_activity.ps1
```

O instalador copia o modulo para `%LOCALAPPDATA%\Jarvis_Xerife\runtime` e cria o atalho `Jarvis - Retorno de Atividade.lnk` na pasta Startup. Nao altera nem remove o briefing existente. Para testar rapidamente, defina `JARVIS_RETURN_IDLE_SECONDS=30` no ambiente do atalho e aguarde 30 segundos sem tocar no teclado/mouse; ao voltar, o Jarvis fala uma vez.

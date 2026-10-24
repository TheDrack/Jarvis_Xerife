# Jarvis - retorno de atividade no Windows

O briefing de inicializacao continua sendo executado pelo atalho existente `Jarvis - Briefing de Inicializacao.lnk`. Este monitor e complementar: depois de cinco minutos sem teclado/mouse, fala uma saudacao apenas quando a entrada volta. O limiar pode ser ajustado com `JARVIS_RETURN_IDLE_SECONDS` (minimo 30 s).

O monitor usa a API Win32 `GetLastInputInfo`, que observa a sessao interativa que o executa. Por isso, deve iniciar no logon do usuario, nao como servico `SYSTEM`; sessoes remotas separadas tem contadores proprios. A voz usa `System.Speech`, seleciona `pt-BR` quando disponivel e reproduz pelo dispositivo de audio padrao do Windows. Em PCs sem saida de audio, a reproducao precisa ser roteada para o telefone em uma etapa de integracao separada. Falhas sao registradas em `%LOCALAPPDATA%\Jarvis_Xerife\logs\return_activity.log`.

## Instalar no usuario atual

Execute no PowerShell como usuario normal (nao precisa de administrador):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_jarvis_return_activity.ps1
```

O instalador copia o modulo para `%LOCALAPPDATA%\Jarvis_Xerife\runtime` e cria o atalho `Jarvis - Retorno de Atividade.lnk` na pasta Startup. Nao altera nem remove o briefing existente. Para testar rapidamente, defina `JARVIS_RETURN_IDLE_SECONDS=30` no ambiente do atalho e aguarde 30 segundos sem tocar no teclado/mouse; ao voltar, o Jarvis fala uma vez.

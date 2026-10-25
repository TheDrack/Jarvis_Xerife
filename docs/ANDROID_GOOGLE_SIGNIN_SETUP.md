# Google Sign-In — configuração operacional

O backend já expõe `POST /v1/mobile/session/google`; o Android usa Google Sign-In para obter um ID token e troca esse token por uma sessão Jarvis. O ID token é validado no servidor, incluindo assinatura, validade e audiência, antes de qualquer sessão ser emitida. Consulte também a documentação oficial do Google: https://developers.google.com/identity/sign-in/android/backend-auth?hl=pt-br

## 1. Criar o OAuth client

No Google Cloud Console, selecione/crie um projeto e configure a tela de consentimento OAuth. Crie um OAuth Client ID do tipo **Web application**. Use esse mesmo **Web Client ID** nas duas configurações abaixo. O app Android solicita um ID token destinado ao cliente Web para que o backend possa verificar a audiência.

Se a configuração OAuth exigir um cliente Android, registre também o package name `com.thedrack.jarvismobile` e o SHA-1 do certificado que assina o APK distribuído. O cliente Web continua sendo o valor usado em `requestIdToken`.

## 2. Configurar o backend no Render

No serviço `Jarvis-api`, adicione a variável de ambiente:

- `GOOGLE_CLIENT_ID` = Web Client ID do Google Cloud

Salve a alteração e aguarde o deploy/restart do serviço. Não coloque client secrets OAuth, chaves de service-role ou credenciais privadas no APK.

## 3. Configurar os builds Android no GitHub

Em **Settings → Secrets and variables → Actions → Variables**, crie a variável de repositório:

- `GOOGLE_WEB_CLIENT_ID` = o mesmo Web Client ID

O workflow `Android Mobile Build` passa essa variável ao Gradle. Se ela estiver ausente, o APK continua compilando, mas o botão Google fica desativado e a tela explica que falta configuração.

## 4. Supabase

A migração `google_linked_identities` cria `public.jarvis_external_identities`, habilita RLS e remove acesso dos papéis públicos. O backend usa o cliente administrativo no servidor. Não conceda acesso direto a `anon` ou `authenticated`.

## 5. Política de vínculo

- O login Google não cria contas automaticamente.
- O primeiro vínculo exige que o e-mail verificado corresponda a uma conta Jarvis existente.
- Depois do vínculo, a identidade estável `sub` do Google é a chave externa.
- O token Google não é aceito como token de API Jarvis; o backend emite a sessão Jarvis normal.
- Tailscale continua sendo apenas transporte privado; autenticação e autorização Jarvis permanecem obrigatórias.

## 6. Verificação pós-configuração

1. Gere um APK com `GOOGLE_WEB_CLIENT_ID` configurado e instale-o.
2. Confirme que o botão **Continuar com Google** está habilitado.
3. Teste uma conta Google cujo e-mail verificado corresponda a uma conta Jarvis existente.
4. Confirme que uma conta sem correspondência recebe erro de acesso negado e não é criada.
5. Confirme que o token de acesso e o refresh token retornados permitem os fluxos normais de API, renovação e logout.
6. Teste com um token inválido/expirado e confirme que o backend recusa a sessão.

A autenticação real só pode ser considerada operacional depois de configurar o Web Client ID no Google Cloud, Render e GitHub e concluir esses testes ponta a ponta.

# Google identity linking

Jarvis keeps its existing username/password authentication and mobile refresh-session lifecycle. Google is an alternative sign-in method linked to an existing Jarvis account, not an account-provisioning mechanism.

## API

- `POST /v1/mobile/session/google` accepts `{"id_token":"<Google ID token>","device_id":"<stable device id>"}`.
- Configure `GOOGLE_CLIENT_ID` on the backend with the OAuth client ID used by the mobile application. The backend validates the Google signature, issuer, expiry and audience using Google's public keys; only tokens with `email_verified=true` are accepted.
- The ID token is exchanged for Jarvis-issued access and refresh tokens. Google tokens are never used as Jarvis API bearer tokens.
- The verified Google email must match an existing Jarvis account. This endpoint does not create accounts, does not link unverified emails, and refuses legacy environment-admin accounts without a stable database identity.
- The mapping is stored in the private `jarvis_external_identities` table. Unique constraints prevent one Google identity or one Google identity slot per Jarvis account from being linked twice. The service-role key stays on the backend.

## Deployment

1. Apply `supabase/migrations/20261025090000_google_linked_identities.sql` after existing migrations.
2. Set `GOOGLE_CLIENT_ID` in the backend service. Do not add secrets to the APK or repository.
3. Deploy the backend, then add Google Sign-In UI/client token acquisition in the Android app using the same OAuth client ID.
4. Test against a real Google OAuth client and an existing Jarvis account before enabling the button in production.

Tailscale remains private transport only. Every request still requires Jarvis authentication and authorization; tailnet reachability does not grant an identity or permission.

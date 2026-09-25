# TerraSatch internal team inbox (draft beta)

A separate, small FastAPI/SQLite app for TerraSatch staff. It does not grant customer workspace users access to staff email. Reuses canonical Satchy artwork and locally hosted Barlow, Rajdhani and JetBrains Mono fonts (Google Fonts, SIL Open Font License files included).

## What works

- Staff sign-in, explicit per-user mailbox permissions, mailbox switching, latest 100 messages per folder and local search.
- Plain-text reading and draft creation. Saving a draft never sends it. Sending requires a separate confirmation and is disabled by default.
- Resend signed inbound webhooks, receiving API retrieval and duplicate suppression.
- Outbound idempotency keys, conservative app-wide budgets (25 attempts/24 hours; 750 attempts/31 days). Uncertain sends remain pending for operator reconciliation; there is no automatic resend.
- Twelve-hour HttpOnly sessions, password-change session invalidation, CSRF/origin checks, login throttling, no remote images or email HTML execution, and 5,000-message storage ceiling.

This is not yet a complete mail client: no attachments, rich HTML, IMAP/POP, threading, draft editing/deleting, automatic delivery confirmation, MFA or self-service password recovery. Search only covers the latest 100 messages in the selected folder. Do not use it as the only archive. Provider acceptance does not mean delivery. A production deployment and real send/receive smoke test remain outstanding.

## Existing Oracle instance

Use the existing Always Free VM only after checking its remaining memory, disk, traffic and free-tier eligibility. The container binds only to `127.0.0.1:8024`, uses at most 256 MB/0.5 CPU and has bounded logs. Do not replace the API's proxy or databases. Use a separate hostname, proposed `mail.terrasatch.com`, with HTTPS through the existing reverse proxy. No instance, paid service, DNS record or mailbox has been provisioned by this change.

On that Linux host, from this directory:

1. Copy `.env.example` to `.env`; keep permissions `600`. Generate the session secret locally (`python3 -c 'import secrets; print(secrets.token_urlsafe(48))'`). Set the exact HTTPS origin. Never commit secrets or paste them into a task.
2. Build with `docker compose build`. Create the persistent directory with `mkdir -p data && sudo chown 10001:10001 data && sudo chmod 700 data`.
3. Add each staff account interactively with `docker compose run --rm inbox python add_user.py`. Enter its allowed mailboxes explicitly, for example `keaton@terrasatch.com` and/or `ops@terrasatch.com`. The account creation utility prompts privately for a 16+ character password. Do not reuse preview credentials.
4. Start with `docker compose up -d`. Check local HTTP responses before adding the host to the existing proxy. Keep port 8024 inaccessible externally. The example Caddy fragment assumes Caddy runs on the host; adapt the upstream if it runs in a container.
5. Configure the real domain and receive/send capability in the existing Resend account. Use the exact MX/DKIM/SPF records the provider returns. Check existing DNS first; preserve other senders and do not create a second SPF record. Add an appropriate DMARC policy after alignment checks. The September 25 public DNS audit found no apex MX record; recheck before changing it.
6. Install the provider API key and webhook secret in `.env` on the host. Subscribe the verified endpoint `/webhooks/resend` to `email.received`. Confirm incoming messages reach only their assigned mailbox and duplicate events do not create duplicates.
7. Only after domain/provider verification, set `INBOX_SENDING_ENABLED=true`, recreate the container and perform one explicitly authorized send/reply test. Verify SPF/DKIM/DMARC results, bounce behavior, quotas and restart persistence before relying on the mailbox.

## Preserve billing email events

Resend's current Free plan lists one webhook endpoint. Do not overwrite an existing billing webhook blindly. This app can relay non-inbound events to the existing production or staging billing endpoint using `INBOX_BILLING_WEBHOOK_URL`; set it to the appropriate exact URL allowed in `app.py`. The downstream billing verifier must use the same webhook signing secret as this endpoint. Validate a signed delivery event through both services before cutover. Failed relays return 503 so Resend retries; the billing consumer must retain its own deduplication. If that coordinated setup is unavailable, leave the existing billing webhook unchanged and keep this inbox in setup mode.

## Cost and maintenance boundaries

Oracle hosting and Resend Free can avoid a new recurring subscription while within their current allocations. This app cannot guarantee a permanently free service: provider limits can change, inbound mail and other applications share the account's quota, and backups/storage/traffic use resources. The internal send budget is not a global provider quota monitor. Keep the provider on its free plan, do not enable paid upgrades/add-ons, and monitor the account's aggregate usage. Check current terms at https://resend.com/pricing and https://www.oracle.com/cloud/free/ before deployment.

Back up `data/` with a SQLite-consistent backup and protect the copy as private mail. Test restore. Monitor disk usage, webhook failures and pending sends. Rotate staff passwords to revoke their sessions; rotate the session secret to revoke all sessions. Store `.env` and user hashes outside source control. No automatic deletion occurs at the storage ceiling; an administrator must establish an approved retention/export process before reaching it. Provider-side retention is limited and is not your backup.

## Verification

Install `requirements.txt` plus pytest and run `pytest test_inbox.py --confcutdir=.`. Tests use fake credentials and a mocked provider; they send no real email. Check desktop/mobile sign-in, mailbox switching, draft save/read, disabled-send state and canonical artwork in a browser. For deployment, additionally verify TLS, proxy/body limits, actual DNS, provider signing and an authorized end-to-end message.

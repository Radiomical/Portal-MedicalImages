# Transactional email over Resend SMTP

## Opt-in configuration

Set `EMAIL_PROVIDER=resend` only in the private deployment environment. This pins
the SMTP backend, `smtp.resend.com`, port 587, username `resend`, STARTTLS and a
20-second network timeout. It cannot silently send to console or another host.

Provide these deployment values separately:

- `DEFAULT_FROM_EMAIL`: the approved no-reply address on the verified sending
  subdomain. For example, `no-reply@notifications.example.com` (not a mailbox).
- `EMAIL_HOST_PASSWORD`: the Resend API key, retrieved from the secret store and
  injected into the environment. Never commit it to source, images, examples,
  compose files or logs. A sending-only, domain-scoped key is sufficient.

`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_USE_TLS` and `EMAIL_BACKEND`
are pinned in Resend mode. Do not use them to override this mode. Missing sender
or credential fails startup. Existing custom SMTP configuration stays available
with the default `EMAIL_PROVIDER=custom`. Tests use an in-memory backend; staging
continues to disable mail. No email is sent on startup or by changing settings.

Signup and password-reset mail continue to use `DEFAULT_FROM_EMAIL`. They do not
add Reply-To. Recipients replying to no-reply may not reach an attended inbox.
Adding an attended Reply-To later is a separate configuration/product decision,
not an invented contact address. A provider change does not change application
recipients, reset tokens, activation URLs, templates or audience permissions.

## Domain preparation

Verify the sending subdomain in Resend. Copy the exact records from the account,
not generic SPF/DKIM values. Some accounts use provider-managed CNAMEs. Do not
replace them with guessed TXT/MX values. In the root Cloudflare DNS zone, a record
for the sending subdomain's DMARC policy uses `_dmarc.notifications`, not only
`_dmarc`. Begin with `v=DMARC1; p=none;` and do not change existing root policy
without reviewing its impact. Verify the actual public DNS before testing.

Keep sending on, receiving off, click tracking off and open tracking off. The
Ireland sending region does not imply all account metadata/logs stay in the EU.
Do not include clinical data in transactional mail.

## Controlled test and activation gates

Before a live test, approve the exact sender, recipient, subject and body. Use
one test message, no clinical data or token links, and no blind retry after an
uncertain SMTP DATA result. Resend supports a `Resend-Idempotency-Key` header for
controlled SMTP tests. Record SMTP acceptance separately from delivery. Verify
actual mailbox arrival/folder and Authentication-Results (SPF, DKIM and DMARC).
An aligned valid DKIM signature is sufficient for DMARC alignment; a missing
DMARC policy is not proof of a DKIM failure.

A sending-only API key cannot read sent-email status. Do not expand it just to
read Delivered if actual mailbox delivery is available. `Delivered` means the
recipient's mail server accepted the message, not that it reached Inbox or was
read. API event success is not a replacement for app signup/reset tests.

Activating production still requires the existing deployment/backup/rollback
gates. This change only prepares configuration. Do not edit production SMTP
settings, restart services or send unsolicited mail as part of creating a PR.
Rollback uses the retained previous private configuration, never a plaintext or
console fallback for real mail. Diagnose authentication failures without blindly
resetting credentials or retrying real messages.

## References

- SMTP configuration and idempotency:
  https://resend.com/docs/send-with-smtp
- DMARC preparation:
  https://resend.com/docs/dashboard/domains/dmarc
- Delivered semantics:
  https://resend.com/docs/webhooks/emails/delivered

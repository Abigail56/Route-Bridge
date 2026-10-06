# Personal-data breach response — DRAFT runbook

> Engineering draft for review by counsel / the DPO. **[CONFIRM]** the statutory deadlines and notification content
> against the current Nigeria Data Protection Act 2023 and NDPC guidance before relying on this. As understood at the
> time of writing, the NDPC must be notified within **72 hours** of becoming aware of a breach likely to risk the rights
> and freedoms of individuals, and affected individuals must be told without undue delay where the risk is high.

## Roles
- **Incident lead:** on-call engineer who declares the incident. **DPO / legal:** decides notification. **Comms:** drafts customer/tenant messages.

## First hour — contain
1. Declare an incident; start a log (who, what, when). Note the time you became aware (the 72-hour clock starts here).
2. Stop the bleeding, preserving evidence:
   - Leaked tracking link → `POST /tenants/{id}/delivery-jobs/{job_id}/tracking-link/reissue`.
   - Lost/stolen driver phone → `PATCH /tenants/{id}/drivers/{driver_id}` with `{"status":"offline"}`; token also expires on its own.
   - Compromised operator → deactivate in Clerk and `PATCH /tenants/{id}/members/{membership_id}` `{"status":"inactive"}`.
   - Leaked secret (webhook, driver-token, SMS, S3) → rotate it in the secret manager and redeploy; rotating `ROUTEBRIDGE_DRIVER_TOKEN_SECRET` signs out every driver device.
   - Suspected data exfiltration → block at the ingress/WAF; snapshot the database and keep logs.
3. Do **not** delete logs or the append-only audit trail.

## Assess (same day)
- What data, whose, how many people, which tenants? Use `GET /tenants/{id}/audit` (filter by aggregate/event type) and the JSON access logs (`request_id` correlates a request across services).
- Was the data readable (plaintext phone/address) or protected? Photos in S3 are private; verify no public ACL/bucket policy.
- Likely harm to individuals (stalking risk from location data, fraud from phone numbers, health context for pharmacy orders).

## Notify (decision by DPO/counsel) **[CONFIRM]**
- **NDPC:** within 72 hours where required. Include: nature of the breach, categories and approximate number of people and records, likely consequences, measures taken, contact point.
- **Affected individuals:** plain-language message when the risk is high; say what happened, what data, what to do, how to reach us.
- **Tenants (merchants):** as processor, tell affected tenants without undue delay so they can meet their own obligations.
- **Providers:** inform the SMS/cloud/auth provider if their systems are implicated.

## Recover and learn
- Fix the root cause; rotate credentials; restore from backups if integrity was affected (see the operations runbook restore drill).
- Blameless post-incident review within 5 working days: timeline, detection gap, actions with owners.
- Record the incident, assessment, decision on notification and the evidence in the breach register (keep for the period counsel advises).
- Update `dpia.md` risks if the incident exposed a new one.

"""Checks your Twilio (text messages) and Resend (email) setup and says exactly what is missing. It sends NOTHING and prints no secrets.

    docker compose exec -T api python -m routebridge.tools.check_messaging

(or from backend/apps/api with the .env loaded). It only READS from Twilio and Resend: who you are, your numbers, your verified domains.
"""
import re
import sys

import httpx

from routebridge.config.settings import get_settings
from routebridge.providers import RESEND_TEST_SENDER

OK, WARN, BAD = "  ok  ", " WARN ", " FAIL "
problems = 0


def line(kind: str, text: str) -> None:
    global problems
    if kind == BAD:
        problems += 1
    print(f"[{kind}] {text}")


def masked(number: str) -> str:
    return number[:4] + "*" * max(0, len(number) - 7) + number[-3:] if len(number) > 7 else "***"


def check_twilio() -> None:
    s = get_settings()
    print("\nTEXT MESSAGES (Twilio)")
    line(OK if s.sms_provider == "twilio" else WARN, f"SMS_PROVIDER is '{s.sms_provider}'" + ("" if s.sms_provider == "twilio" else (" -> messages are only written to the log. Set SMS_PROVIDER=twilio to send them." if s.sms_provider == "log" else "")))
    if not (s.twilio_account_sid and s.twilio_auth_token):
        line(BAD if s.sms_provider == "twilio" else WARN, "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are not both set (console.twilio.com, dashboard, 'Account Info').")
        return
    line(OK, "account SID and auth token are present")
    auth = (s.twilio_account_sid, s.twilio_auth_token)
    base = f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}"
    try:
        with httpx.Client(timeout=15.0, auth=auth) as client:
            account = client.get(f"{base}.json")
            if account.status_code in (401, 403):
                line(BAD, "Twilio rejected this SID and token (check both were copied whole, and that the token was not rolled).")
                return
            account.raise_for_status()
            info = account.json()
            trial = info.get("type") == "Trial"
            line(OK if info.get("status") == "active" else BAD, f"Twilio login works. Account status: {info.get('status')}, type: {info.get('type')}")
            numbers = [n.get("phone_number", "") for n in client.get(f"{base}/IncomingPhoneNumbers.json").json().get("incoming_phone_numbers", [])]
            services = client.get("https://messaging.twilio.com/v1/Services", auth=auth).json().get("services", [])
            callers = [c.get("phone_number", "") for c in client.get(f"{base}/OutgoingCallerIds.json").json().get("outgoing_caller_ids", [])] if trial else []
    except httpx.HTTPError as exc:
        line(BAD, f"could not reach Twilio ({type(exc).__name__}). Check the internet connection.")
        return

    line(OK if numbers else WARN, f"phone numbers on the account: {', '.join(masked(n) for n in numbers) if numbers else 'none'}")
    line(OK if services else WARN, f"messaging services on the account: {len(services)}")
    sender_set = bool(s.twilio_messaging_service_sid or s.twilio_phone_number or s.sms_sender_id.strip())
    line(OK if sender_set else BAD, "a sender is set (TWILIO_PHONE_NUMBER, TWILIO_MESSAGING_SERVICE_SID or SMS_SENDER_ID)" if sender_set else "no sender is set: set TWILIO_PHONE_NUMBER (a number from the list above) or TWILIO_MESSAGING_SERVICE_SID")
    if s.twilio_phone_number and numbers and s.twilio_phone_number not in numbers:
        line(BAD, f"TWILIO_PHONE_NUMBER ({masked(s.twilio_phone_number)}) is not one of this account's numbers")
    if s.twilio_messaging_service_sid and services and s.twilio_messaging_service_sid not in [x.get("sid") for x in services]:
        line(BAD, "TWILIO_MESSAGING_SERVICE_SID is not one of this account's messaging services")
    alphanumeric = not s.twilio_phone_number and not s.twilio_messaging_service_sid and bool(re.search(r"[A-Za-z]", s.sms_sender_id))
    if alphanumeric:
        line(WARN, f"the sender is the name '{s.sms_sender_id}'. Texts to Nigerian numbers from a sender NAME only arrive if that name is registered with Twilio for Nigeria (a regulatory form that takes days to weeks). Trial accounts cannot use sender names at all.")
    if trial:
        line(WARN, "this is a TRIAL account: it can only text numbers you have verified in Twilio, and each text starts with 'Sent from your Twilio trial account'. Upgrade it to text real customers.")
        line(OK if callers else WARN, f"verified numbers you can text on trial: {', '.join(masked(n) for n in callers) if callers else 'none yet (Twilio console > Phone Numbers > Verified Caller IDs)'}")


def check_resend() -> None:
    s = get_settings()
    print("\nEMAIL (Resend)")
    if not s.resend_api_key:
        line(WARN, "RESEND_API_KEY is not set, so emails are only written to the log. Create a key at resend.com/api-keys.")
        return
    line(OK, "an API key is present")
    if s.email_provider == "log":
        line(WARN, "EMAIL_PROVIDER=log: emails are never sent. Set it to auto.")
    try:
        response = httpx.get("https://api.resend.com/domains", headers={"Authorization": f"Bearer {s.resend_api_key}", "User-Agent": "RouteBridge/1.0"}, timeout=15.0)
    except httpx.HTTPError as exc:
        line(BAD, f"could not reach Resend ({type(exc).__name__}). Check the internet connection.")
        return
    if response.status_code in (401, 403):
        detail = response.json().get("message", "") if response.content else ""
        # a key limited to "sending access" cannot list domains: that is fine for sending
        line(WARN if "restricted" in detail.lower() else BAD, f"Resend answered {response.status_code}: {detail or 'the key was refused'}" + (" (a sending-only key cannot list domains; sending still works)" if "restricted" in detail.lower() else " (check the key was copied whole)"))
        return
    response.raise_for_status()
    domains = {d["name"].lower(): d.get("status", "") for d in response.json().get("data", [])}
    line(OK, "Resend login works")
    line(OK if domains else WARN, "verified/added domains: " + (", ".join(f"{n} ({st})" for n, st in domains.items()) if domains else "none (resend.com/domains)"))
    sender = s.email_from or RESEND_TEST_SENDER
    match = re.search(r"@([^>\s]+)", sender)
    domain = match.group(1).lower() if match else ""
    if not s.email_from or domain == "resend.dev":
        line(WARN, f"sending as {sender}: Resend's test sender ONLY delivers to the email address of your own Resend account. To email shops, verify a domain and set EMAIL_FROM.")
    elif domains.get(domain) == "verified":
        line(OK, f"sending as {sender} (domain verified)")
    else:
        line(BAD, f"EMAIL_FROM uses {domain}, which is not a verified domain in Resend (status: {domains.get(domain, 'not added')}).")


def main() -> int:
    print("RouteBridge messaging check (nothing is sent, no secrets are shown)")
    check_twilio()
    check_resend()
    print("\n" + ("Everything that is switched on works." if not problems else f"{problems} thing(s) need fixing (lines marked FAIL)."))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

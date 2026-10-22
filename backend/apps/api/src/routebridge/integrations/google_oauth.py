"""'Continue with Google': the OAuth 2.0 authorization-code flow with PKCE, run by the API.

The browser is sent to Google with a random state, a PKCE challenge and a nonce (kept in a short-lived signed cookie). Google
sends it back to the callback with a code, which the API exchanges for an ID token and checks against Google's published keys:
signature, audience (our client id), issuer, expiry and the nonce.
"""
import base64
import hashlib
import secrets
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlencode

import httpx
import jwt

from routebridge.config.settings import get_settings

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")


class GoogleSignInError(Exception):
    """Google refused, or what came back could not be trusted. The message is safe to log, never shown verbatim."""


@dataclass(frozen=True)
class GoogleAccount:
    sub: str
    email: str
    email_verified: bool
    name: str | None


@dataclass(frozen=True)
class Attempt:
    state: str
    verifier: str
    nonce: str


def new_attempt() -> Attempt:
    return Attempt(secrets.token_urlsafe(24), secrets.token_urlsafe(48), secrets.token_urlsafe(24))


def authorize_url(attempt: Attempt) -> str:
    settings = get_settings()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(attempt.verifier.encode()).digest()).rstrip(b"=").decode()
    query = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_callback_url,
        "response_type": "code",
        "scope": "openid email profile",
        "state": attempt.state,
        "nonce": attempt.nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


@lru_cache(maxsize=1)
def _keys() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(CERTS_URL)


def exchange_code(code: str, attempt: Attempt, client: httpx.Client | None = None) -> GoogleAccount:
    settings = get_settings()
    form = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_callback_url,
        "grant_type": "authorization_code",
        "code_verifier": attempt.verifier,
    }
    try:
        response = (client or httpx.Client(timeout=10.0)).post(TOKEN_URL, data=form)
    except httpx.HTTPError as exc:
        raise GoogleSignInError(f"could not reach Google: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise GoogleSignInError(f"Google refused the code (HTTP {response.status_code})")
    id_token = response.json().get("id_token")
    if not id_token:
        raise GoogleSignInError("Google sent no ID token")
    return verify_id_token(id_token, attempt.nonce)


def verify_id_token(id_token: str, nonce: str, key=None) -> GoogleAccount:
    settings = get_settings()
    try:
        signing_key = key if key is not None else _keys().get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(id_token, signing_key, algorithms=["RS256"], audience=settings.google_client_id, issuer=ISSUERS, leeway=60)
    except jwt.PyJWTError as exc:
        raise GoogleSignInError(f"ID token rejected: {type(exc).__name__}") from exc
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise GoogleSignInError("ID token nonce does not match")
    if not claims.get("sub") or not claims.get("email"):
        raise GoogleSignInError("ID token has no account id or email")
    return GoogleAccount(sub=str(claims["sub"]), email=str(claims["email"]).strip().lower(), email_verified=claims.get("email_verified") is True, name=claims.get("name"))

"""Print strong values for the secrets the production configuration check requires.

    python -m routebridge.tools.gen_secrets > secrets.env      # then load into your secret manager; never commit it
"""
import secrets


def generate() -> dict[str, str]:
    return {
        "ROUTEBRIDGE_WEBHOOK_SIGNING_SECRET": secrets.token_urlsafe(48),
        "ROUTEBRIDGE_INTERNAL_API_KEY": secrets.token_urlsafe(32),
        "ROUTEBRIDGE_DRIVER_TOKEN_SECRET": secrets.token_urlsafe(48),
    }


if __name__ == "__main__":
    for name, value in generate().items():
        print(f"{name}={value}")
    print("# Also set: ROUTEBRIDGE_DATABASE_URL, ROUTEBRIDGE_REDIS_URL, ROUTEBRIDGE_SMS_API_URL, ROUTEBRIDGE_SMS_API_KEY,")
    print("# ROUTEBRIDGE_S3_ACCESS_KEY, ROUTEBRIDGE_S3_SECRET_KEY, CLERK_SECRET_KEY (values come from Terraform and your vendors).")

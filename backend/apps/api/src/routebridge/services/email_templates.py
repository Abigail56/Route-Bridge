"""The look of RouteBridge emails, and their subject lines.

The message body is plain text (the same text an SMS would carry). It is shown as the plain-text part of the email, and wrapped in a small
branded page (navy header, orange rule) for the HTML part. Everything that came from a person is escaped.
"""
import html
import re

BRAND = "RouteBridge Logistics"
NAVY, ORANGE = "#0f2744", "#ff7a29"

# Subject by notification template. A template that is not listed gets DEFAULT_SUBJECT.
EMAIL_SUBJECTS = {
    "merchant_welcome": "Welcome to RouteBridge Logistics",
    "merchant_order_created": "New order received",
    "claim_update": "An update on your claim",
}
DEFAULT_SUBJECT = "An update from RouteBridge Logistics"

_URL = re.compile(r"(https?://[^\s<]+[^\s<.,;:!?)\]])")


def subject_for(template: str) -> str:
    return EMAIL_SUBJECTS.get(template, DEFAULT_SUBJECT)


def _paragraph(text: str) -> str:
    safe = html.escape(text.strip(), quote=True)
    safe = _URL.sub(lambda m: f'<a href="{m.group(1)}" style="color:#c2410c">{m.group(1)}</a>', safe)
    return f'<p style="margin:0 0 14px;font-size:16px;line-height:1.55">{safe.replace(chr(10), "<br>")}</p>'


def render_email_html(subject: str, body: str) -> str:
    paragraphs = "".join(_paragraph(part) for part in re.split(r"\n\s*\n", body.strip()) if part.strip()) or _paragraph(body)
    return (
        '<!doctype html><html><body style="margin:0;background:#f3f6fa;font-family:Arial,Helvetica,sans-serif;color:' + NAVY + '">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">'
        '<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden">'
        f'<tr><td style="background:{NAVY};padding:18px 24px;color:#ffffff;font-size:18px;font-weight:700">{html.escape(BRAND)}</td></tr>'
        f'<tr><td style="height:4px;background:{ORANGE};font-size:0;line-height:0">&nbsp;</td></tr>'
        f'<tr><td style="padding:26px 24px 12px"><h1 style="margin:0 0 16px;font-size:22px;color:{NAVY}">{html.escape(subject)}</h1>{paragraphs}</td></tr>'
        '<tr><td style="padding:0 24px 24px;font-size:12px;color:#566a82">You get this because your shop is registered with ' + html.escape(BRAND) + '. '
        'Reply to this email if something looks wrong.</td></tr>'
        '</table></td></tr></table></body></html>'
    )

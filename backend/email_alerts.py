import os
import ssl
import smtplib
import asyncio
import logging
from html import escape
from email.message import EmailMessage

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
APP_NAME = "ColdChain Dashboard"

SUBJECTS = {
    "warning": "[ADVERTENCIA] {name}: temperatura cerca del límite ({t:.2f} °C)",
    "critical": "[CRÍTICO] {name}: temperatura fuera de rango ({t:.2f} °C)",
    "normal": "[NORMALIZADO] {name}: temperatura de vuelta en rango ({t:.2f} °C)",
}
INTROS = {
    "warning": "La temperatura del dispositivo está cerca del límite del rango seguro (2–8 °C). Se recomienda acción preventiva.",
    "critical": "La temperatura del dispositivo salió del rango seguro (2–8 °C). La cadena de frío puede estar comprometida.",
    "normal": "La temperatura del dispositivo volvió al rango seguro (2–8 °C).",
}
COLORS = {"warning": "#b45309", "critical": "#be123c", "normal": "#047857"}


def is_configured() -> bool:
    return bool(os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD"))


def build_email(state: str, device_id: str, device_name: str, temperature: float, ts: str):
    subject = SUBJECTS[state].format(name=device_name, t=temperature)
    rows = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#64748b">{k}</td>'
        f'<td style="padding:4px 0;color:#0f172a;font-family:monospace">{escape(str(v))}</td></tr>'
        for k, v in (("Dispositivo", device_name), ("ID", device_id),
                     ("Temperatura", f"{temperature:.2f} °C"), ("Fecha (UTC)", ts))
    )
    html = (
        '<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif">'
        f'<h2 style="margin:0 0 12px;color:{COLORS[state]}">{escape(subject)}</h2>'
        f'<p style="color:#334155">{INTROS[state]}</p>'
        f'<table role="presentation" style="margin:16px 0">{rows}</table>'
        '<p style="color:#334155">Revisa el panel para más detalles.</p>'
        f'<p style="font-size:12px;color:#94a3b8">Aviso automático de {APP_NAME}.</p>'
        '</td></tr></table>'
    )
    return subject, html


def _send_sync(recipients: list, subject: str, html: str):
    user = os.environ["GMAIL_USER"]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{APP_NAME} <{user}>"
    msg["To"] = user
    msg["Bcc"] = ", ".join(recipients)
    msg.set_content(subject)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=20) as s:
        s.login(user, os.environ["GMAIL_APP_PASSWORD"].replace(" ", ""))
        s.send_message(msg)


async def send_alert_email(recipients: list, subject: str, html: str):
    await asyncio.to_thread(_send_sync, recipients, subject, html)

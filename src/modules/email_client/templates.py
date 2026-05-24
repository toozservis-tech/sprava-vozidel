from __future__ import annotations

from html import escape
from typing import Iterable, Mapping, Sequence

from src.core.branding import APP_DISPLAY_NAME, APP_EMAIL_MOOD_LINE, APP_EMAIL_TAGLINE
from src.core.config import PUBLIC_API_BASE_URL

EMAIL_BRAND_LOGO_PATH = "/web/assets/toozservis-logo-icon.png"


def build_app_url(path: str = "/web/index.html") -> str:
    base = str(PUBLIC_API_BASE_URL or "").strip().rstrip("/")
    if not base:
        return f"https://hub.toozservis.cz{path}"
    if base.endswith("/web/index.html") and path == "/web/index.html":
        return base
    if base.endswith("/index.html") and path == "/web/index.html":
        return base
    return f"{base}{path}"


def _email_public_origin() -> str:
    """Kořen webu pro absolutní odkazy v e-mailech (logo — stejná logika jako u vstupní URL aplikace)."""
    base = str(PUBLIC_API_BASE_URL or "").strip().rstrip("/")
    if not base:
        return "https://hub.toozservis.cz"
    for suf in ("/web/index.html", "/index.html"):
        if base.endswith(suf):
            trimmed = base[: -len(suf)].rstrip("/")
            return trimmed if trimmed else "https://hub.toozservis.cz"
    return base


def build_public_asset_url(path: str) -> str:
    """Absolutní URL k veřejnému assetu (logo v HTML e-mailu)."""
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{_email_public_origin()}{normalized}"


def html_multiline(text: str | None) -> str:
    return "<br>".join(escape(str(text or "")).splitlines()) or "Neuvedeno"


def render_rows(rows: Sequence[tuple[str, object]]) -> str:
    """Řádky štítek / hodnota — pod sebou (lepší čitelnost v úzkém e-mailu)."""
    rendered = []
    n = len(rows)
    for idx, (label, value) in enumerate(rows):
        safe_value = escape(str(value if value not in (None, "") else "Neuvedeno"))
        border = "" if idx == n - 1 else "border-bottom:1px solid #f1f5f9;"
        rendered.append(
            f"""
            <tr>
              <td style="padding:10px 0;{border}">
                <div style="font-size:12px;font-weight:500;color:#94a3b8;margin:0 0 4px;">
                  {escape(str(label))}
                </div>
                <div style="font-size:14px;color:#334155;font-weight:400;line-height:1.5;">
                  {safe_value}
                </div>
              </td>
            </tr>
            """
        )
    return "".join(rendered)


def render_panel(
    *,
    title: str,
    rows: Sequence[tuple[str, object]] | None = None,
    message: str | None = None,
    raw_html: str | None = None,
    accent: str = "#4f46e5",
    tone: str = "#fafbfc",
) -> str:
    rows_html = ""
    if rows:
        rows_html = f"""
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
          {render_rows(rows)}
        </table>
        """
    message_html = ""
    if message:
        message_html = (
            f'<div style="color:#334155; font-size:14px; line-height:1.65; white-space:normal;">{html_multiline(message)}</div>'
        )
    if raw_html:
        message_html += raw_html
    accent_safe = escape(accent)
    tone_safe = escape(tone)
    # Levý akcent místo výrazného pruhu přes celou šířku — vizuálně tišší než starý layout
    return f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:18px 0;border-collapse:separate;border-radius:12px;border:1px solid #eef1f6;border-left:3px solid {accent_safe};background:{tone_safe};overflow:hidden;">
      <tr>
        <td style="padding:14px 16px 8px;">
          <div style="font-size:12px;font-weight:600;color:#64748b;letter-spacing:0.02em;">{escape(title)}</div>
        </td>
      </tr>
      <tr>
        <td style="padding:0 16px 14px;">
          {rows_html}
          {message_html}
        </td>
      </tr>
    </table>
    """


def render_email_callout(
    *,
    title: str,
    rows: Sequence[tuple[str, object]],
    accent: str = "#4f46e5",
    lead_emoji: str = "\U0001f698",  # 🚘 — téma vozidel (dobře se zobrazí v Gmail / iOS Mail)
) -> str:
    """
    Zvýrazněný blok typu „důležité info“ — zaoblená karta, emoji, bez ostrých barevných ploch.
    Použití: demo odkaz, klíčové podmínky, upozornění.
    """
    acc = escape(accent)
    rows_html = ""
    if rows:
        rows_html = f"""
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
          {render_rows(rows)}
        </table>
        """
    head_cell = ""
    if lead_emoji:
        head_cell = f"""
                <td width="40" valign="top" style="padding:0 10px 0 0;font-size:22px;line-height:1.1;">{lead_emoji}</td>"""
    return f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:22px 0;border-collapse:separate;border-radius:18px;border:1px solid #e2e8f0;background:#f8fafc;overflow:hidden;">
      <tr>
        <td style="padding:0;margin:0;height:3px;background:{acc};line-height:3px;font-size:0;">&nbsp;</td>
      </tr>
      <tr>
        <td style="padding:16px 18px 12px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
            <tr>
              {head_cell}
              <td valign="top" style="padding:0;">
                <span style="font-size:13px;font-weight:700;color:#0f172a;letter-spacing:-0.015em;">{escape(title)}</span>
              </td>
            </tr>
          </table>
        </td>
      </tr>
      <tr>
        <td style="padding:0 18px 18px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;border-radius:14px;background:#ffffff;border:1px solid #eef2f7;">
            <tr>
              <td style="padding:14px 16px;">
                {rows_html}
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
    """


def render_list(items: Iterable[str], *, bullet_color: str = "#4f46e5") -> str:
    parts = []
    bc = escape(bullet_color)
    for item in items:
        if not str(item or "").strip():
            continue
        parts.append(
            f"""
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:0 0 10px;border-collapse:collapse;">
              <tr>
                <td width="28" valign="top" style="color:{bc};font-size:18px;line-height:1.2;font-weight:700;">•</td>
                <td valign="top" style="color:#334155;font-size:14px;line-height:1.6;padding-top:2px;">{html_multiline(item)}</td>
              </tr>
            </table>
            """
        )
    if not parts:
        return ""
    return f'<div style="margin:16px 0 0;">{"".join(parts)}</div>'


def render_summary_steps(
    *,
    title: str,
    items: Sequence[str],
    accent: str = "#4f46e5",
) -> str:
    """
    Číslovaný seznam kroků / změn — přehlednější než tabulka „Úprava 1“.
    """
    blocks: list[str] = []
    i = 0
    for raw in items:
        text = str(raw or "").strip()
        if not text:
            continue
        i += 1
        blocks.append(
            f"""
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:0 0 10px;border-collapse:separate;border-radius:12px;border:1px solid #e2e8f0;background:#ffffff;overflow:hidden;">
              <tr>
                <td width="48" valign="middle" align="center" bgcolor="{escape(accent)}"
                    style="background:{escape(accent)};color:#ffffff;font-weight:700;font-size:15px;padding:12px 8px;mso-line-height-rule:exactly;line-height:1.2;">
                  {i}
                </td>
                <td valign="middle" style="padding:14px 16px;font-size:14px;line-height:1.55;color:#0f172a;">
                  {html_multiline(text)}
                </td>
              </tr>
            </table>
            """
        )
    if not blocks:
        return ""
    return f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:20px 0;border-collapse:separate;border-radius:14px;border:1px solid #e2e8f0;overflow:hidden;background:#fafbfc;">
      <tr>
        <td style="padding:0;margin:0;">
          <div style="height:3px;background:{escape(accent)};line-height:3px;font-size:0;">&nbsp;</div>
        </td>
      </tr>
      <tr>
        <td style="padding:16px 18px 10px;background:#f8fafc;border-bottom:1px solid #e2e8f0;">
          <div style="font-size:13px;font-weight:700;color:#0f172a;">{escape(title)}</div>
        </td>
      </tr>
      <tr>
        <td style="padding:14px 14px 18px;">
          {"".join(blocks)}
        </td>
      </tr>
    </table>
    """


def render_email_layout(
    *,
    title: str,
    subtitle: str,
    intro: str,
    panels: Sequence[str] | None = None,
    paragraphs: Sequence[str] | None = None,
    cta_label: str | None = None,
    cta_url: str | None = None,
    accent: str = "#4f46e5",
    footer_note: str | None = None,
) -> str:
    panel_html = "".join(panels or [])
    paragraph_html = "".join(
        f'<p style="margin:0 0 14px; color:#475569; font-size:15px; line-height:1.65;">{html_multiline(paragraph)}</p>'
        for paragraph in (paragraphs or [])
        if str(paragraph or "").strip()
    )
    cta_html = ""
    if cta_label and cta_url:
        safe_url = escape(cta_url, quote=True)
        cta_html = f"""
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin:28px 0 0;border-collapse:collapse;">
          <tr>
            <td align="center" style="padding:0;">
              <a href="{safe_url}" style="display:inline-block;background:{escape(accent)};color:#ffffff !important;text-decoration:none;font-weight:600;font-size:15px;padding:14px 32px;border-radius:999px;mso-padding-alt:0;">
                {escape(cta_label)}
              </a>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:14px 8px 0;color:#94a3b8;font-size:12px;line-height:1.6;">
              Pokud tlačítko nefunguje, zkopírujte odkaz do prohlížeče:<br>
              <a href="{safe_url}" style="color:{escape(accent)};word-break:break-all;text-decoration:underline;">{escape(cta_url)}</a>
            </td>
          </tr>
        </table>
        """
    if footer_note and str(footer_note).strip():
        footer_block_html = html_multiline(footer_note)
    else:
        footer_block_html = f"""
              <span style="display:block;margin-bottom:10px;line-height:1.55;font-size:13px;">
                <strong style="font-weight:600;color:#334155;">{escape(APP_DISPLAY_NAME)}</strong>
              </span>
              <span style="display:block;margin-bottom:14px;font-size:11px;line-height:1.55;color:#94a3b8;">
                {escape(APP_EMAIL_TAGLINE)}
              </span>
              <span style="display:block;font-size:12px;line-height:1.65;color:#64748b;">
                Tento e-mail byl odeslán automaticky z ověřeného systému {escape(APP_DISPLAY_NAME)}. Pokud jste tuto zprávu neočekávali, zkontrolujte svůj účet nebo kontaktujte podporu.
              </span>
            """.strip()
    logo_src = escape(build_public_asset_url(EMAIL_BRAND_LOGO_PATH), quote=True)
    home_url = escape(build_app_url(), quote=True)
    acc = escape(accent)
    return f"""
<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <title>{escape(title)} · {escape(APP_DISPLAY_NAME)}</title>
</head>
<body style="margin:0;padding:0;background:#e2e8f0;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#e2e8f0;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;border-collapse:separate;border-spacing:0;">
          <tr>
            <td style="border-radius:24px;overflow:hidden;border:1px solid #d0d9e8;background:#ffffff;box-shadow:0 18px 48px rgba(15,23,42,0.08);">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                <tr>
                  <td style="height:4px;background:{acc};line-height:4px;font-size:0;">&nbsp;</td>
                </tr>
                <tr>
                  <td style="padding:26px 28px 6px;background:#ffffff;">
                    <table role="presentation" cellspacing="0" cellpadding="0" width="100%" style="border-collapse:collapse;">
                      <tr>
                        <td width="52" valign="top" style="padding:0;">
                          <a href="{home_url}" style="text-decoration:none;border:0;">
                            <img src="{logo_src}" width="44" height="44" alt="{escape(APP_DISPLAY_NAME)}" border="0" style="display:block;width:44px;height:44px;border-radius:14px;border:1px solid #e8edf3;">
                          </a>
                        </td>
                        <td valign="middle" style="padding:0 0 0 14px;">
                          <a href="{home_url}" style="text-decoration:none;color:inherit;">
                            <span style="display:block;font-size:18px;font-weight:700;color:#0f172a;letter-spacing:-0.02em;line-height:1.25;">
                              {escape(APP_DISPLAY_NAME)}
                            </span>
                            <span style="display:block;margin-top:5px;font-size:12px;line-height:1.45;color:#64748b;">
                              {escape(APP_EMAIL_TAGLINE)}
                            </span>
                          </a>
                        </td>
                      </tr>
                    </table>
                    <div style="height:1px;background:#e8edf3;margin:18px 0 0;line-height:1px;font-size:0;">&nbsp;</div>
                    <p style="margin:14px 0 0;font-size:12px;line-height:1.55;color:#64748b;font-style:italic;">
                      {escape(APP_EMAIL_MOOD_LINE)}
                    </p>
                    <h1 style="margin:16px 0 8px;font-size:22px;line-height:1.25;font-weight:700;color:#0f172a;letter-spacing:-0.02em;">
                      {escape(title)}
                    </h1>
                    <p style="margin:0 0 0;font-size:15px;line-height:1.5;color:#64748b;">
                      {escape(subtitle)}
                    </p>
                  </td>
                </tr>
                <tr>
                  <td style="padding:12px 28px 28px;background:#ffffff;">
                    <p style="margin:0 0 16px;color:#0f172a;font-size:16px;line-height:1.6;font-weight:500;">
                      {html_multiline(intro)}
                    </p>
                    {paragraph_html}
                    {panel_html}
                    {cta_html}
                  </td>
                </tr>
                <tr>
                  <td style="padding:20px 28px;background:#f1f5f9;border-top:1px solid #e2e8f0;text-align:left;">
                    <p style="margin:0;font-size:12px;line-height:1.65;color:#64748b;">
                      {footer_block_html}
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

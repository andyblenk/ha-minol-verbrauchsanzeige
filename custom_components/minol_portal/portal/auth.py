"""Resident SAML/B2C login. No browser, credentials logging or cookie files.

This implementation uses the portal's current SETTINGS contract and guarded I/O.
"""

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlsplit

from yarl import URL

from .errors import AuthenticationError, ProtocolError
from .models import Credentials
from .transport import PortalTransport, origin_of


@dataclass(frozen=True)
class Form:
    action: str = field(repr=False)
    fields: dict[str, str] = field(repr=False)


class _Forms(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms: list[Form] = []
        self.current: Form | None = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form":
            self.current = Form(values.get("action") or "", {})
            self.forms.append(self.current)
        elif tag == "input" and self.current and values.get("name"):
            self.current.fields[values["name"]] = values.get("value") or ""

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


def parse_forms(html: str) -> list[Form]:
    parser = _Forms()
    parser.feed(html)
    return parser.forms


def saml_form(html: str) -> Form | None:
    return next((form for form in parse_forms(html) if form.fields.get("SAMLResponse")), None)


@dataclass(frozen=True)
class LoginPage:
    csrf: str = field(repr=False)
    transaction: str = field(repr=False)
    tenant_path: str
    api: str
    signin_field: str

    @classmethod
    def parse(cls, html: str):
        match = re.search(r"\bSETTINGS\s*=\s*", html)
        try:
            if match is None:
                raise ValueError
            settings, _ = json.JSONDecoder().raw_decode(html[match.end():])
            csrf = settings["csrf"]
            transaction = settings["transId"]
            tenant_path = settings["hosts"]["tenant"]
            api = settings["api"]
            if not all(isinstance(value, str) and value for value in (csrf, transaction, tenant_path, api)):
                raise ValueError
            if not re.fullmatch(r"/[A-Za-z0-9._-]+/[A-Za-z0-9_-]+", tenant_path):
                raise ValueError
            if not re.fullmatch(r"[A-Za-z0-9_-]+", api):
                raise ValueError
            field_match = re.search(r'"ID"\s*:\s*"(signInName|logonIdentifier|email)"', html)
            if field_match is None:
                field_match = re.search(r'<input[^>]+(?:id|name)=[\"\x27](signInName|logonIdentifier|email)[\"\x27]', html, re.I)
            if field_match is None:
                raise ValueError
            return cls(csrf, transaction, tenant_path, api, field_match.group(1))
        except (ValueError, KeyError, TypeError):
            raise ProtocolError("Die B2C-Anmeldeseite enthält nicht die erwarteten Formular-/Transaktionsfelder.") from None


class PortalAuthenticator:
    def __init__(self, transport: PortalTransport):
        self.transport = transport

    async def login(self, credentials: Credentials):
        portal = self.transport.endpoints.portal
        identity = self.transport.endpoints.identity
        await self.transport.request("GET", portal + "/?redirect2=true", follow=True)
        query = urlencode({"logonTargetUrl": portal + "/", "saml2idp": "B2C-Minol-Tenant"})
        reply = await self.transport.request("GET", portal + "/minol.com~kundenportal~login~saml/?" + query, follow=True)
        form = saml_form(reply.text)
        if form is None:
            if origin_of(reply.url) != origin_of(identity):
                raise ProtocolError("Die Portal-Anmeldung hat den erwarteten Identitätsdienst nicht erreicht.")
            page = LoginPage.parse(reply.text)
            policy = page.tenant_path.rsplit("/", 1)[-1]
            params = urlencode({"tx": page.transaction, "p": policy})
            reply = await self.transport.request(
                "POST", identity + page.tenant_path + "/SelfAsserted?" + params,
                data={"request_type": "RESPONSE", page.signin_field: credentials.email.strip(), "password": credentials.password},
                headers={"X-CSRF-TOKEN": page.csrf, "X-Requested-With": "XMLHttpRequest",
                         "Accept": "application/json", "Referer": reply.url.split("?", 1)[0]},
            )
            if 300 <= reply.status < 400:
                raise ProtocolError("Die Credential-Antwort wurde unerwartet weitergeleitet; es wurden keine Daten weitergesendet.")
            try:
                result = json.loads(reply.text) if reply.text.strip() else {"status": "200"}
            except ValueError:
                raise ProtocolError("Die Anmeldeantwort ist kein erwartetes JSON.") from None
            if reply.status != 200 or not isinstance(result, dict) or str(result.get("status")) != "200":
                message = str(result.get("message", "")) if isinstance(result, dict) else ""
                if "account could not be found" in message.lower():
                    raise AuthenticationError("Der Identitätsdienst findet die bereitgestellte Anmeldekennung nicht. Bitte die E-Mail-Adresse beziehungsweise Anmeldekennung in der Einrichtung prüfen.")
                raise AuthenticationError("Die bereitgestellte Anmeldung wurde abgewiesen. Zugangsdaten oder erforderliche Benutzerinteraktion prüfen.")
            params = urlencode({"rememberMe": "false", "csrf_token": page.csrf, "tx": page.transaction, "p": policy})
            reply = await self.transport.request("GET", identity + page.tenant_path + "/api/" + page.api + "/confirmed?" + params, follow=True)
            form = saml_form(reply.text)
            if form is None:
                raise AuthenticationError("Nach der Anmeldung wurde keine SAML-Antwort geliefert; möglicherweise ist Benutzerinteraktion erforderlich.")
        for _ in range(4):
            action = self.transport.validate_url(urljoin(reply.url, form.action), portal_only=True)
            if urlsplit(action).path not in {"/saml2/sp/acs", "/irj/portal", "/irj/portal/", "/minol.com~kundenportal~login~saml/"}:
                raise ProtocolError("Das SAML-Formularziel entspricht keinem unterstützten SAP-Anmeldepfad.")
            reply = await self.transport.request("POST", action, data=form.fields)
            if reply.status in {301, 302, 303}:
                location = reply.headers.get("Location")
                if not location:
                    raise ProtocolError("Im SAP-Anmeldeabschluss fehlt ein Weiterleitungsziel.")
                reply = await self.transport.request("GET", urljoin(reply.url, location), follow=True)
            elif reply.status != 200:
                raise AuthenticationError("Der SAP-Anmeldeabschluss ist fehlgeschlagen.")
            if self.transport.session.cookie_jar.filter_cookies(URL(portal)).get("MYSAPSSO2"):
                return
            forms = parse_forms(reply.text)
            if not forms:
                break
            form = forms[0]
        raise AuthenticationError("Der Anmeldeabschluss hat keine verwendbare SAP-Sitzung erstellt.")

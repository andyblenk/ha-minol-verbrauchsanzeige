"""Bounded HTTP requests; redirect locations are checked before following."""

from dataclasses import dataclass, field
from collections.abc import Mapping
from urllib.parse import urljoin

import aiohttp
from yarl import URL

from .errors import ConnectionError, ProtocolError


MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_REDIRECTS = 10
PORTAL_ORIGIN = "https://webservices.minol.com"
IDENTITY_ORIGIN = "https://minolauth.b2clogin.com"


def origin_of(url: str) -> tuple[str, str | None, int | None]:
    parsed = URL(url, encoded=True)
    return parsed.scheme, parsed.host.lower() if parsed.host else None, parsed.port


@dataclass(frozen=True)
class Endpoints:
    portal: str = PORTAL_ORIGIN
    identity: str = IDENTITY_ORIGIN

    def __post_init__(self):
        for origin in (self.portal, self.identity):
            url = URL(origin)
            local_test = url.host in {"127.0.0.1", "localhost", "::1"}
            if url.user or url.password or url.query_string or url.fragment or url.path != "/":
                raise ValueError("Endpunkte müssen reine Origins sein.")
            if url.scheme != "https" and not (local_test and url.scheme == "http"):
                raise ValueError("Portal-Endpunkte erfordern HTTPS.")


@dataclass(frozen=True)
class Reply:
    status: int
    url: str = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)
    text: str = field(repr=False)


class PortalTransport:
    def __init__(self, session: aiohttp.ClientSession, endpoints: Endpoints):
        self.session = session
        self.endpoints = endpoints
        self._origins = {origin_of(endpoints.portal), origin_of(endpoints.identity)}

    def validate_url(self, url: str, *, portal_only: bool = False) -> str:
        try:
            parsed = URL(url, encoded=True)
            allowed = {origin_of(self.endpoints.portal)} if portal_only else self._origins
            if "@" in parsed.raw_authority or origin_of(url) not in allowed:
                raise ValueError
        except (ValueError, TypeError):
            raise ProtocolError("Ein Anmelde- oder Redirectziel liegt außerhalb der freigegebenen Portal-Origins.") from None
        return url

    async def request(self, method: str, url: str, *, follow: bool = False, **kwargs) -> Reply:
        self.validate_url(url)
        for _ in range(MAX_REDIRECTS + 1):
            try:
                async with self.session.request(
                    method, URL(url, encoded=True), allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=90), **kwargs,
                ) as response:
                    chunks = []
                    size = 0
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise ProtocolError("Die Portalantwort überschreitet die erlaubte Größe.")
                        chunks.append(chunk)
                    text = b"".join(chunks).decode(response.charset or "utf-8", errors="replace")
                    reply = Reply(response.status, str(response.url), response.headers, text)
            except (aiohttp.ClientError, TimeoutError, LookupError):
                raise ConnectionError("Das Minol-Portal ist nicht erreichbar oder die TLS-/Netzwerkverbindung ist fehlgeschlagen.") from None
            location = response.headers.get("Location")
            if not follow or not location or response.status not in {301, 302, 303, 307, 308}:
                return reply
            if method != "GET":
                raise ProtocolError("POST-Anmeldedaten werden nicht automatisch weitergeleitet.")
            url = self.validate_url(urljoin(url, location))
        raise ProtocolError("Zu viele Weiterleitungen im Portal-Anmeldeweg.")

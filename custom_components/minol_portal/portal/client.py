"""Read-only portal API, with one bounded re-login after session expiration."""

import asyncio
import json
from collections.abc import Callable

import aiohttp

from .auth import PortalAuthenticator
from .errors import AuthenticationError, ProtocolError, SelectionError, SessionExpired
from .models import ConsumptionData, Credentials, METER_VIEW_FAMILIES, MonthRange, PortalSnapshot
from .transport import Endpoints, PortalTransport


EM_PATH = "/minol.com~kundenportal~em~web/rest/EMData"
USER_PATH = "/minol.com~util~framework~ui5~common~web/rest/UserInfo/getUserDetail"


class PortalClient:
    def __init__(self, session: aiohttp.ClientSession, credentials: Credentials, *, endpoints: Endpoints | None = None):
        self.transport = PortalTransport(session, endpoints or Endpoints())
        self.credentials = credentials
        self.authenticator = PortalAuthenticator(self.transport)
        self._authenticated = False
        self._lock = asyncio.Lock()

    async def _json(self, method: str, path: str, body=None):
        headers = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest",
                   "Referer": self.transport.endpoints.portal + "/irj/portal"}
        kwargs = {"headers": headers}
        if body is not None:
            kwargs["json"] = body
        reply = await self.transport.request(method, self.transport.endpoints.portal + path, **kwargs)
        if reply.status in {301, 302, 303, 401}:
            raise SessionExpired("Die Portal-Sitzung ist abgelaufen oder eine erneute Anmeldung wird verlangt.")
        if reply.status == 403:
            raise SelectionError("Das Portal hat diesen lesenden Datenabruf nicht freigegeben.")
        if reply.status != 200:
            raise ProtocolError(f"Der Portal-Datenabruf meldet HTTP {reply.status}.")
        content_type = reply.headers.get("Content-Type", "").partition(";")[0].strip().lower()
        if (content_type in {"text/html", "application/xhtml+xml"}
                or reply.text.lstrip().lower().startswith(("<!doctype html", "<html"))):
            raise SessionExpired("Die Portal-Sitzung ist abgelaufen oder eine erneute Anmeldung wird verlangt.")
        try:
            return json.loads(reply.text)
        except ValueError:
            raise ProtocolError("Der Portal-Datenabruf liefert kein gültiges JSON.") from None

    async def fetch_snapshot(self, period: MonthRange, tenant_number: str | None = None,
                             progress: Callable[[str], None] | None = None, *, monthly: bool = False) -> PortalSnapshot:
        notify = progress or (lambda message: None)
        async with self._lock:
            for attempt in range(2):
                try:
                    if not self._authenticated:
                        notify("Anmeldung am Portal")
                        await self.authenticator.login(self.credentials)
                        self._authenticated = True
                    return await self._fetch(period, tenant_number, notify, monthly=monthly)
                except SessionExpired:
                    self._authenticated = False
                    if attempt:
                        raise AuthenticationError("Die neu erstellte Portal-Sitzung wurde beim Datenabruf erneut abgewiesen.") from None
            raise AssertionError("Unreachable authentication state")

    async def _fetch(self, period: MonthRange, tenant_number: str | None, notify, *, monthly: bool) -> PortalSnapshot:
        notify("Eigene Konto- und Wohnungszuordnung lesen")
        tenants = await self._json("GET", EM_PATH + "/getUserTenants")
        account = await self._json("GET", USER_PATH)
        if not isinstance(account, dict) or not isinstance(tenants, list) or any(not isinstance(t, dict) for t in tenants):
            raise ProtocolError("Das Konto-/Nutzereinheitenschema ist unerwartet.")
        if not tenants or any(not isinstance(t.get("userNumber"), str) or not t["userNumber"] for t in tenants):
            raise SelectionError("Das Konto liefert keine verwendbare eigene Nutzereinheit.")
        warnings = []
        selected = next((t for t in tenants if t["userNumber"] == (tenant_number or self.credentials.user_num)), None)
        if selected is None:
            if tenant_number or len(tenants) != 1:
                raise SelectionError("Bitte eine der vom eigenen Konto gelieferten Nutzereinheiten auswählen.")
            selected = tenants[0]
            if self.credentials.user_num:
                warnings.append("Die konfigurierte user_num stimmt nicht mit der Kontoantwort überein; verwendet wird die einzige vom Konto freigegebene Nutzereinheit.")
        selection = period.selection(selected["userNumber"])
        notify("Freigegebene Ansichten und Zeiträume lesen")
        layer = await self._json("POST", EM_PATH + "/getLayerInfo", selection)
        if (not isinstance(layer, dict) or not isinstance(layer.get("views"), list)
                or any(not isinstance(view, dict)
                       or not isinstance(view.get("key"), str) or not view["key"]
                       for view in layer["views"])):
            raise ProtocolError("Das Portal liefert keine erwartete Ansichtsliste.")
        raw_scales = layer.get("scales", [])
        if not isinstance(raw_scales, list):
            raise ProtocolError("Das Portal liefert keine erwartete Liste von Zeitrastern.")
        scales = [scale.get("key") if isinstance(scale, dict) else scale for scale in raw_scales]
        if any(not isinstance(scale, str) or not scale for scale in scales):
            raise ProtocolError("Ein Portal-Zeitraster besitzt keinen gültigen Schlüssel.")
        if scales and "CALMONTH" not in scales:
            raise SelectionError("Für diese Nutzereinheit ist keine Monatsauswertung freigegeben.")
        views = [view for view in layer["views"]
                 if view.get("status") != "U" and view["key"] != "tableau"]
        by_key = {view["key"]: view for view in views}
        meter_views = []
        for candidates in METER_VIEW_FAMILIES.values():
            view = next((by_key[key] for key in candidates if key in by_key), None)
            if view is not None:
                meter_views.append(view)
        if not meter_views:
            # No readable views is not a successful set of empty monthly tables.
            raise ProtocolError("Das Portal bietet derzeit keine unterstützte Zähleransicht an.")
        monthly_results = {}
        if monthly:
            for month in period.months():
                month_selection = MonthRange(month, month).selection(selected["userNumber"])
                monthly_results[month] = await self._read_views(month_selection, meter_views, notify)
            results = monthly_results[period.end]
        else:
            results = await self._read_views(selection, views, notify)
        return PortalSnapshot(account, tenants, selected, layer, period, results, warnings,
                              monthly_results=monthly_results)

    async def _read_views(self, selection, views, notify):
        results = []
        for index, view in enumerate(views, 1):
            key = view.get("key")
            if not isinstance(key, str) or not key:
                raise ProtocolError("Eine freigegebene Portalansicht besitzt keinen verwendbaren Schlüssel.")
            notify(f"Verbrauchsansicht {index} von {len(views)} lesen")
            reference = "DIN_AVG" if key in {"100EH", "100KWH", "200", "dashboard"} else "UPPER_LEVEL"
            if "RAUM" in key:
                reference = "NOREF"
            request = {**selection, "dlgKey": key, "consType": view.get("consType") or "HEIZUNG",
                       "valuesInKWH": key.startswith("100"), "refObject": reference}
            raw = await self._json("POST", EM_PATH + "/readData", request)
            if any(key in candidates for candidates in METER_VIEW_FAMILIES.values()) and (
                not isinstance(raw, dict) or "table" not in raw
            ):
                raise ProtocolError("Die Zählerantwort enthält keine Monatstabelle.")
            results.append(ConsumptionData.parse(key, raw))
        return results

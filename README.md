# Minol Verbrauchsanzeige

<img src="custom_components/minol_portal/brand/icon.png" alt="Zähler-Symbol" width="96" align="right">

**Heizungs- und Wasserverbrauch aus dem Minol-Portal in Home Assistant.**

Die Integration erkennt die für deine Wohnung verfügbaren Messgeräte, zeigt ihre Werte an und baut eine dauerhafte Monatshistorie auf. Aus den gespeicherten Monaten entstehen die Sensoren **Gesamtverbrauch** und **Rohverbrauch gesamt**.

Die Daten stammen aus dem Minol-Portal. Ihre Aktualität richtet sich nach der Veröffentlichung durch Minol; die Integration liest die Zähler nicht direkt aus.

## Entwicklung unterstützen

Wenn dir die Integration gefällt oder sie dir im Alltag hilft, freue ich mich über deine Unterstützung.

[☕ Buy Me a Coffee](https://buymeacoffee.com/andyblenk) – vielen Dank!

## Funktionen

- Automatische Erkennung von Heizungs-, Warmwasser- und Kaltwasserzählern.
- Eigene Geräte und Sensoren je Messgerät, mit Raumzuordnung aus dem Portal.
- Dauerhafte Speicherung monatlicher Verbrauchswerte und Berücksichtigung nachträglicher Korrekturen.
- Letzte Ablesung, Bewertungsfaktor, Berichtsmonat und Abrufzeitpunkt je Gerät.
- Benutzer- und Wohnungsangaben in einem zusätzlichen Gerät **Stammdaten**.
- Separate Einrichtung mehrerer Wohnungen.
- Einstellbares Abrufintervall und erneute Anmeldung über Home Assistant.

## Voraussetzungen

- **Home Assistant ab 2026.9.4**.
- **[HACS](https://www.hacs.xyz/)**, bereits installiert und eingerichtet.
- Ein Minol-Portalkonto mit freigeschalteten Verbrauchsdaten für die eigene Wohnung.
- Eine Internetverbindung zum Minol-Portal.

## Installation über HACS

1. **HACS** öffnen.
2. Oben rechts im **Drei-Punkte-Menü** den Eintrag **Benutzerdefinierte Repositories** auswählen.
3. Diese Repository-URL eintragen:

   ```text
   https://github.com/andyblenk/ha-minol-verbrauchsanzeige
   ```

4. Als Kategorie **Integration** auswählen und auf **Hinzufügen** klicken.
5. In HACS nach **Minol Verbrauchsanzeige** suchen und die Integration **herunterladen**.
6. **Home Assistant neu starten.**

Weitere Hilfe: [Benutzerdefinierte Repositories in HACS](https://www.hacs.xyz/docs/faq/custom_repositories/).

## Einrichtung

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen** öffnen.
2. **Minol Verbrauchsanzeige** auswählen.
3. E-Mail-Adresse beziehungsweise Anmeldekennung und Passwort des Minol-Portals eingeben und absenden.

**Bei genau einer Wohnung bleibt die Nutzereinheiten-ID leer.** Bei mehreren Wohnungen ist die passende `userNumber` des Portals erforderlich. Sie kann von der Kundennummer und der sichtbaren Einheitsnummer abweichen. Nach der Einrichtung wird sie auch unter **Stammdaten** angezeigt.

Die Einrichtung erhält automatisch einen Namen im Format **Einheit <Nummer> - <Straße Hausnummer>, <Ort>**. Du kannst ihn in Home Assistant ändern, ohne die Zuordnung der Geräte oder ihrer Monatsdaten zu verändern. Weitere Wohnungen werden als zusätzliche Einträge eingerichtet.

Die Anmeldung und das erste Einlesen der Monatsdaten können einige Minuten dauern.

## Sensoren

Für jedes erkannte Messgerät werden folgende Sensoren angelegt:

| Sensor | Beschreibung | Kategorie |
|---|---|---|
| **Letzte Ablesung** | Neueste verfügbare Ablesung innerhalb der abgefragten Monate | Messwert |
| **Gesamtverbrauch** | Summe aller gespeicherten bewerteten Monatsverbräuche | Messwert |
| **Rohverbrauch gesamt** | Summe aller gespeicherten unbewerteten Monatsverbräuche | Messwert |
| **Bewertungsfaktor** | Vom Portal gelieferter Faktor | Messwert |
| Gerätenummer | Kennung des Messgeräts | Diagnose |
| Raum | Raumbezeichnung aus dem Portal | Diagnose |
| Verbrauchsart | Heizung, Warmwasser oder Kaltwasser | Diagnose |
| Letzter Berichtsmonat | Letzter vom Portal für die Nutzereinheit angebotener Monat | Diagnose |
| Letzter erfolgreicher Abruf | Zeitpunkt des letzten erfolgreichen Datenabrufs für dieses Gerät | Diagnose |

Die beiden Verbrauchssummen werden mit **zwei Nachkommastellen** ausgegeben. Für Rohverbrauch und Ablesung wird keine Einheit aus der bewerteten Verbrauchseinheit abgeleitet. Weitere Angaben wie Datenqualität und Abfragezeitraum stehen in den Sensorattributen.

Der Berichtsmonat gilt für die Nutzereinheit. Er bestätigt keinen individuellen Ablesestichtag jedes Zählers. Ein Zähler mit neuer Gerätenummer erhält ein eigenes Gerät mit eigenen Sensoren.

### Stammdaten

Das Gerät **Stammdaten** zeigt die verfügbaren Benutzer- und Wohnungsangaben:

- Name, E-Mail, Benutzerkennung, Sprache und Benutzertyp.
- Liegenschaft, Nutzeinheit und Nutzereinheiten-ID.
- Geschosslage, Straße mit Hausnummer, Ort mit Postleitzahl und Land.
- Einzug, Auszug und gegebenenfalls Kundenangaben.

Es werden nur Felder angelegt, die das Portal liefert.

## Daten und Sicherung

Die Integration aktualisiert bei jedem Abruf die letzten zwölf Monate und behält ältere Monate dauerhaft. Neue Werte und Korrekturen werden automatisch in die Verbrauchssummen übernommen. Die gelieferten Zahlen bleiben beim Speichern ungerundet; beide Summensensoren zeigen zwei Nachkommastellen.

**Sichere deine vollständige Home-Assistant-Konfiguration**, damit die gespeicherte Monatshistorie bei einem Umzug oder einer Neuinstallation erhalten bleibt.

Wichtig für die Auswertung:

- Beim ersten Abruf beginnt die Historie mit den letzten zwölf Monaten. Ältere Daten werden nicht automatisch nachgeladen.
- Korrekturen werden innerhalb des Zwölfmonatsfensters übernommen. Änderungen an älteren Monaten werden nicht automatisch erkannt.
- Fehlende Monatswerte tragen zunächst null zur Summe bei und werden bei späteren Abrufen aktualisiert. Nicht lesbare oder fehlerhafte Portalansichten überschreiben keine historischen Werte.
- **HA erfasst Änderungen zum Empfangszeitpunkt.** Verspätet veröffentlichte Werte werden nicht rückwirkend ihrem ursprünglichen Verbrauchsmonat zugeordnet.

## Einstellungen

Unter **Einstellungen → Geräte & Dienste → Minol Verbrauchsanzeige → Konfigurieren** kann das Abrufintervall geändert werden:

| Einstellung | Standard | Bereich |
|---|---|---|
| Abrufintervall | 6 Stunden | 1–168 Stunden |

Beim Neuladen bleibt der letzte verfügbare Stand sichtbar. Neue Daten werden im Hintergrund abgerufen; der Abrufzeitpunkt der Geräte ändert sich erst nach erfolgreicher Aktualisierung.

## Sprachen

Einrichtungs- und Optionsdialoge einschließlich ihrer Meldungen sind auf **Deutsch** und **Englisch** verfügbar. Home Assistant verwendet die eingestellte Oberflächensprache.

Sensor- und Gerätenamen sind derzeit deutsch. Angaben aus dem Minol-Portal, etwa Raumbezeichnungen, werden unverändert übernommen.

## Häufige Fragen

**Die Integration erscheint nach dem Herunterladen nicht.**  
Home Assistant neu starten und die Browserseite neu laden. Danach unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** suchen.

**Die Anmeldung schlägt fehl.**  
Prüfe zunächst, ob die Anmeldung mit denselben Zugangsdaten im Minol-Portal funktioniert und Verbrauchsdaten freigeschaltet sind. Bei mehreren Wohnungen ist die passende Nutzereinheiten-ID erforderlich. Verlangt HA eine erneute Anmeldung, verwende den dafür angezeigten Einrichtungsdialog.

**Warum ändert sich der Gesamtverbrauch noch nicht?**

Die Summen ändern sich, sobald Minol neue oder korrigierte Monatswerte veröffentlicht. Der letzte Berichtsmonat zeigt, bis zu welchem Monat das Portal Berichte anbietet. Weitere Qualitätsangaben stehen in den Sensorattributen.

**Eine Verbrauchssumme hat sich nachträglich geändert.**  
Minol kann bereits veröffentlichte Monate korrigieren. Die Integration übernimmt diese Änderungen innerhalb des Abruffensters; deshalb können sich die Summen auch verringern.

## Fehler melden und mitwirken

Fehlerberichte und Verbesserungsvorschläge sind unter [GitHub Issues](https://github.com/andyblenk/ha-minol-verbrauchsanzeige/issues) willkommen. Hilfreich sind die Home-Assistant- und Integrationsversion, eine Beschreibung des Problems und relevante, bereinigte Protokollauszüge.

Bitte keine Passwörter, Tokens oder persönlichen Konto-, Adress- und Verbrauchsdaten veröffentlichen.

Der Integrationscode liegt unter `custom_components/minol_portal/`, der API-Client im Unterordner `portal/`. Übersetzungsbeiträge sind ebenfalls willkommen: `strings.json` und `translations/en.json` enthalten die englischen Basistexte, `translations/de.json` die deutsche Übersetzung.

## Lizenz

Dieses Projekt steht unter der [MIT-Lizenz](LICENSE).

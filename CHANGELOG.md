# Changelog

Alle wesentlichen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.
Das Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

## [0.3.3] - 2026-11-19

### Hinzugefügt

- Automatische HACS- und Hassfest-Prüfungen über GitHub Actions.

### Behoben

- Manifest-Schlüssel in die von Hassfest geforderte Reihenfolge gebracht.

## [0.3.2] - 2026-11-18

### Behoben

- Abgelaufene Portal-Sitzungen auch erkennen, wenn die HTML-Anmeldeseite mit
  einem Skript beginnt. Der Datenabruf meldet sich dann automatisch erneut an.
- Bei Portalfehlern die konkrete, bereinigte Fehlerursache im HA-Protokoll anzeigen.

## [0.3.1] - 2026-11-17

### Hinzugefügt

- Erste öffentliche Version der Minol Verbrauchsanzeige zur Installation über
  HACS als benutzerdefiniertes Repository.
- Anmeldung am Minol-Portal und separate Einrichtung mehrerer Wohnungen.
- Automatische Erkennung der verfügbaren Heizungs-, Warmwasser- und
  Kaltwasserzähler mit Raumzuordnung.
- Sensoren für Gesamtverbrauch, Rohverbrauch gesamt, letzte Ablesung und
  Bewertungsfaktor sowie Diagnoseangaben je Messgerät.
- Benutzer- und Wohnungsangaben im zusätzlichen Gerät „Stammdaten“.
- Dauerhafte Monatshistorie mit Aktualisierung der letzten zwölf Monate und
  Übernahme nachträglicher Korrekturen innerhalb dieses Zeitraums.
- Einstellbares Abrufintervall und erneute Anmeldung über Home Assistant.
- Aktualisierung im Hintergrund beim Neuladen der Integration.
- Deutsche und englische Einrichtungs- und Optionsdialoge.
- Deutsche Dokumentation und MIT-Lizenz.

[Unreleased]: https://github.com/andyblenk/ha-minol-verbrauchsanzeige/compare/v0.3.3...HEAD
[0.3.3]: https://github.com/andyblenk/ha-minol-verbrauchsanzeige/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/andyblenk/ha-minol-verbrauchsanzeige/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/andyblenk/ha-minol-verbrauchsanzeige/releases/tag/v0.3.1

# Entwicklung

## Aufbau

- Eine Domain `buschfunk` in `custom_components/buschfunk/`; ein Sensor je
  Eintrag, keine zusätzlichen Abhängigkeiten (`camera`/`image` nur als
  `after_dependencies` für Raumbilder aus Entitäten).
- `api.py`: Client für `<URL>/api/integration/v1/` (`chats`, `nachrichten`,
  `entwuerfe`, `dienstraeume`) mit Bearer-Key, `allow_redirects=False` und
  festem Zeitlimit. 401 → `ApiAuthError`, 403 → `ApiForbiddenError`
  (Unterklasse, z. B. MCP-Key), 429 → `ApiRateLimitError` mit `Retry-After`
  in Sekunden (nie automatisch wiederholt). Genau ein identischer
  Wiederholversuch bei Netzwerkfehlern und HTTP 502/503/504 beim Schreiben,
  bei Diensträumen für PUT und POST nur 502/504 (503 heißt dort „nicht
  eingerichtet“), DELETE nie. Antworten werden vor der Rückgabe auf Form
  geprüft (`angenommen` bzw. gleiche `kennung` und `vorgang`).
- `services.py`: Aktionen `chats`, `senden`, `entwurf`, `dienstraum_senden`,
  `dienstraum_sicherstellen`, `dienstraum_entfernen`. Eingaben werden vor
  der Konvertierung validiert (keine Booleans oder Brüche als Chat-ID,
  Zeitangaben nur im Kernformat `JJJJ-MM-TTTHH:MM:SS[.mmm](Z|±HH:MM)`).
  Dienstraumfelder werden wie im Buschfunk-Kern geprüft (Kennungsmuster,
  Längen in Codepoints, Steuerzeichen, `trim()` nach JavaScript-Regeln, Bild
  ≤ 1 MiB an den Bytes erkannt), damit nichts mit 400 zurückkommt. Dateien
  werden im Executor gelesen, Symlinks vor der Prüfung gegen
  `allowlist_external_dirs` aufgelöst.
- `coordinator.py`, `sensor.py`: Sensor „Diensträume“ über
  `GET dienstraeume`, alle 5 Minuten und sofort nach Raumänderungen. Der
  erste Abruf blockiert die Einrichtung nicht: mit MCP-Key oder bei einem
  Kern ohne Diensträume (beides 403, der Wächter des Kerns sperrt unbekannte
  Wege) bleibt nur der Sensor nicht verfügbar. 403 startet keine Reauth,
  weil deren Prüfung (`chats`) mit demselben Key gelingen würde.
- `config_flow.py`: Einrichtung, Neu konfigurieren, Reauth, Optionen.
  Eindeutige ID ist die normalisierte URL. Keys werden nie in Formulare
  vorbelegt.
- Texte stehen in `strings.json` und `translations/{de,en}.json` (alle Felder
  mit Label und Hilfe in beiden Sprachen).
- `quality_scale.yaml` dokumentiert den lokalen Stand; das Manifest beansprucht
  keine offizielle Quality-Scale-Einstufung.

## Tests

```bash
pip install pytest-homeassistant-custom-component==0.13.365
python -m pytest -q
```

`tests/attrappe.py` ist eine Buschfunk-Attrappe (aiohttp-Server auf
127.0.0.1) mit den Regeln der Dienstraum-API inklusive 401/403/429 und
403 für unbekannte Wege wie der Wächter des Kerns; die
Tests geben dafür per `socket_enabled` nur lokale Sockets frei.

Der Workflow `.github/workflows/validate.yml` führt hassfest, die HACS-Prüfung
und die Tests aus. Die Tests laufen gegen Home Assistant 2026.7.0 und 2026.9.x.
Alle Adressen und Keys in den Tests sind erfunden.

Nativ im Home-Assistant-Frontend wurden die Formularschemata der Einrichtung,
der Optionen und der Aktionen bei 320 bis 1280 px, hell und dunkel, auf
Überlauf geprüft. Das Prüfskript benötigt Zugangsdaten zu einer laufenden
Instanz und wird deshalb nicht mit ausgeliefert.

## Geprüft

26.10.2026, Version 0.2.0 (Implementierung `eacba34`): 111 von 111 Tests
gegen Home Assistant 2026.9.2 mit Python 3.14.9 und
`pytest-homeassistant-custom-component` 0.13.365 bestanden, keine übersprungen.
Die statische UI-Regelprüfung meldet keine Verstöße. Der laufende
Buschfunk-Endpunkt für Diensträume antwortet ohne Schlüssel und mit einem
erfundenen Schlüssel jeweils korrekt mit HTTP 401.

Noch offen vor der Veröffentlichung: authentifizierter Live-Rundlauf mit
eigener Testkennung (Anlegen, identischer PUT, Senden mit identischer
Vorgangskennung, Liste, Entfernen und erneute Liste), native Formularabnahme
der neuen Aktionen und Prüfung des über HACS installierten Stands.
Die lokalen Tests ersetzen diese Nachweise nicht.

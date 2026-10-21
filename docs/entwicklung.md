# Entwicklung

## Aufbau

- Eine Domain `buschfunk` in `custom_components/buschfunk/`; keine Entitäten,
  kein Coordinator, keine zusätzlichen Abhängigkeiten.
- `api.py`: Client für `<URL>/api/integration/v1/` (`chats`, `nachrichten`,
  `entwuerfe`) mit Bearer-Key, `allow_redirects=False` und festem Zeitlimit.
  Genau ein identischer Wiederholversuch bei Netzwerkfehlern und HTTP
  502/503/504 beim Schreiben. Antworten werden vor der Rückgabe auf Form
  geprüft (`angenommen` und gleiche `vorgang`).
- `services.py`: Aktionen `chats`, `senden`, `entwurf`; Eingaben werden vor
  der Konvertierung validiert (keine Booleans oder Brüche als Chat-ID,
  Zeitangaben nur mit Zeitzone). Dateien werden im Executor gelesen, Symlinks
  vor der Prüfung gegen `allowlist_external_dirs` aufgelöst.
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

Der Workflow `.github/workflows/validate.yml` führt hassfest, die HACS-Prüfung
und die Tests aus. Die Tests laufen gegen Home Assistant 2026.7.0 und 2026.9.x.
Alle Adressen und Keys in den Tests sind erfunden.

Nativ im Home-Assistant-Frontend wurden die Formularschemata der Einrichtung,
der Optionen und der Aktionen bei 320 bis 1280 px, hell und dunkel, auf
Überlauf geprüft. Das Prüfskript benötigt Zugangsdaten zu einer laufenden
Instanz und wird deshalb nicht mit ausgeliefert.

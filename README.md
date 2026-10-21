# Buschfunk für Home Assistant

Mit dieser Integration sendest du aus Home Assistant Nachrichten über deine
selbst betriebene Buschfunk-Installation oder bereitest dort Entwürfe vor, die
du anschließend in Buschfunk bestätigst. Unterstützt werden Text,
Bilder/Videos/Dateien, Abstimmungen, Standorte, Kontakte und Termine. Gelesen
wird nur ein begrenztes Chatverzeichnis (Kennung, Name, Messenger, Chattyp),
keine Nachrichtenverläufe.

Die Integration legt **keine Entitäten und keine Dashboardkarte** an; sie stellt
drei Aktionen bereit, die du in Automationen, Skripten und unter Entwicklerwerkzeuge
→ Aktionen verwendest.

## Voraussetzungen

- Home Assistant 2026.7.0 oder neuer.
- Eine erreichbare Buschfunk-Installation mit API-Key-Verwaltung. Die Adresse
  ist die Wurzel-Adresse ohne Pfad, z. B. `https://chat.example.com`
  (HTTPS empfohlen; HTTP und HTTPS sind zulässig, Weiterleitungen werden nicht
  verfolgt).
- Ein API-Key: in der Buschfunk-Weboberfläche oder App unter
  **Einstellungen → Sicherheit** den Eintrag **API-Key erzeugen** wählen. Der
  Key wird nur einmal angezeigt.

## Installation

1. HACS → Menü (drei Punkte) → **Benutzerdefinierte Repositories** →
   `https://github.com/luukkii123/ha-buschfunk-integrations`, Kategorie
   **Integration**.
2. **Buschfunk** herunterladen und Home Assistant neu starten.

## Einrichtung

**Einstellungen → Geräte & Dienste → Integration hinzufügen → Buschfunk**

| Feld | Bedeutung |
| --- | --- |
| Buschfunk-URL | Adresse deiner Installation, nur Schema, Host und optional Port (kein Pfad, keine Zugangsdaten, keine Parameter). |
| API-Key | Der unter Einstellungen → Sicherheit erzeugte Key. Gespeicherte Keys werden nie wieder angezeigt. |

Beim Speichern wird der Zugang geprüft (ein Chatverzeichnis-Abruf), ohne eine
Nachricht zu senden. Dieselbe Installation lässt sich nicht doppelt anlegen.
Der Key liegt im geschützten Konfigurationseintrag von Home Assistant; trage ihn
nicht in Automations-YAML ein.

**Neu konfigurieren** (Menü des Eintrags) ändert URL und Key. Wird ein Key
widerrufen oder ist er ungültig, öffnet Home Assistant automatisch den
Reauth-Dialog, in dem du nur den neuen Key eingibst.

### Optionen

| Option | Bereich | Vorgabe | Bedeutung |
| --- | --- | --- | --- |
| Zeitlimit | 10–120 Sekunden | 45 | Zeitlimit je Anfrage. Beim Senden gibt es bei Netzwerkfehlern (und HTTP 502/503/504) genau einen identischen Wiederholversuch. |

## Aktionen

Alle Aktionen haben die Auswahl **Instanz** (`entry_id`). Bei genau einer
eingerichteten Installation kann sie leer bleiben. Von Nutzern manuell
ausgelöste Aktionen erfordern Administratorrechte.

### `buschfunk.chats`: Chatverzeichnis

Liefert die erlaubten Chatziele ohne Inhalte; eine Antwortvariable ist
erforderlich. Antwort: `{chats: [...], naechste: ...}`. `naechste` ist `null`
am Ende, sonst der Offset für die nächste Seite.

| Feld | Bedeutung |
| --- | --- |
| `suche` | Filtert Chatnamen nach diesem Text. |
| `dienst` | Messenger-ID, z. B. `telegram`. Leer: alle Dienste. |
| `nach` | Offset für Folgeseiten, Vorgabe 0. |
| `limit` | 1–100, Vorgabe 50. |

### `buschfunk.senden` und `buschfunk.entwurf`

`senden` verschickt sofort, `entwurf` legt einen Entwurf an, den du in
Buschfunk bestätigst. Beide haben dieselben Felder; nur die zur **Inhaltsart**
passenden Felder ausfüllen.

| Feld | Gilt für | Bedeutung |
| --- | --- | --- |
| `chat_id` | alle (Pflicht) | Chatkennung aus `buschfunk.chats` (ganze Zahl ≥ 1). |
| `art` | alle | `text` (Vorgabe), `medien`, `abstimmung`, `standort`, `kontakt` oder `ereignis`. |
| `text` | Text, Medien | Nachrichtentext bzw. Beschriftung der Medien (bei Medien optional). |
| `dateien` | Medien | Liste lokaler Dateipfade, 1–20 Dateien, zusammen höchstens 100 MiB. |
| `medienmodus` | Medien | `bild`, `video` oder `datei` (Vorgabe) für alle Dateien. |
| `frage` | Abstimmung | Frage, bis 255 Zeichen. |
| `antworten` | Abstimmung | 2–12 verschiedene Antworten, je bis 100 Zeichen. |
| `mehrfach` | Abstimmung | Mehrfachauswahl, Vorgabe aus. |
| `breite`, `laenge` | Standort | Breitengrad (−90 bis 90), Längengrad (−180 bis 180). |
| `name` | Kontakt, Termin (Pflicht), Standort (optional) | Name. |
| `telefon` | Kontakt | Telefonnummer. |
| `beginn` | Termin | Beginn als ISO-Zeitpunkt mit Zeitzone, z. B. `2026-10-10T12:00:00+02:00`. |
| `ende` | Termin | Optionales Ende, nicht vor dem Beginn. |
| `beschreibung`, `ort` | Termin | Optional. |
| `vorgang` | alle | Optionale UUID für sichere Wiederholungen (siehe unten). |

Zusätzlich nur bei `buschfunk.entwurf`:

| Feld | Bedeutung |
| --- | --- |
| `ablauf_in_sekunden` | Entwurf läuft nach so vielen Sekunden ab. |
| `verfaellt_um` | Alternativ ein ISO-Zeitpunkt mit Zeitzone. Nie zusammen mit `ablauf_in_sekunden`. Beide leer: kein automatischer Ablauf. |
| `benachrichtigen` | Weist registrierte Buschfunk-Geräte auf den neuen Entwurf hin (Vorgabe aus). |

Beispiel:

```yaml
action: buschfunk.senden
data:
  chat_id: 12
  art: text
  text: "Waschmaschine ist fertig."
```

Medien-Dateien müssen in `allowlist_external_dirs` von Home Assistant liegen;
URLs werden nicht heruntergeladen, Symlinks werden vor dem Zugriff aufgelöst
und geprüft. Welche Inhalte ein Messenger annimmt, entscheidet Buschfunk;
nicht unterstützte Kombinationen werden abgelehnt.

### Antwort, Wiederholung und Fehler

`senden` und `entwurf` liefern bei Erfolg `{vorgang: <UUID>, angenommen: true}`.
Das bestätigt die Annahme durch Buschfunk, nicht den Empfang oder das Lesen beim
Kontakt. Ohne eigene `vorgang`-Angabe wird eine UUID erzeugt. Für wiederholbare
Automationen eine UUID selbst erzeugen und für denselben Auftrag beibehalten;
geänderte Inhalte brauchen eine neue UUID. Ist das Ergebnis unklar, nennt die
Fehlermeldung die Vorgangskennung: nur mit derselben Kennung und denselben
Inhalten wiederholen. Ein Aufruf ohne Kennung ist ein neuer Auftrag und kann
erneut senden.

## Entfernen

1. **Einstellungen → Geräte & Dienste → Buschfunk** → Menü → **Löschen**.
2. Den API-Key in Buschfunk widerrufen.
3. Bei Bedarf das Repository aus HACS entfernen und Home Assistant neu starten.
4. Automationen, die `buschfunk.*`-Aktionen nutzen, anpassen oder deaktivieren.

Bereits gesendete Nachrichten, Entwürfe und geplante Aufträge in Buschfunk
bleiben bestehen.

## Entwicklung

Siehe [docs/entwicklung.md](docs/entwicklung.md).

## Lizenz

MIT, siehe [LICENSE](LICENSE).

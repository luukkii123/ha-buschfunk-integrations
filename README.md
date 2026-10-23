# Buschfunk für Home Assistant

Mit dieser Integration sendest du aus Home Assistant Nachrichten über deine
selbst betriebene Buschfunk-Installation oder bereitest dort Entwürfe vor, die
du anschließend in Buschfunk bestätigst. Unterstützt werden Text,
Bilder/Videos/Dateien, Abstimmungen, Standorte, Kontakte und Termine. Gelesen
wird nur ein begrenztes Chatverzeichnis (Kennung, Name, Messenger, Chattyp),
keine Nachrichtenverläufe.

Außerdem schreibt Home Assistant in eigene **Diensträume**: Räume, die in
Buschfunk unter **Diensträume** stehen (nicht unter Chats) und deren Absender
wie der Raum heißt, z. B. „Waschmaschine“ oder „Haustür“.

Die Integration stellt sechs Aktionen bereit, die du in Automationen, Skripten
und unter Entwicklerwerkzeuge → Aktionen verwendest, und einen Sensor mit den
aktiven Diensträumen. Eine Dashboardkarte gibt es nicht.

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
| `beginn` | Termin | Beginn als ISO-Zeitpunkt mit Datum, Uhrzeit inklusive Sekunden und Zeitzone, z. B. `2026-10-10T12:00:00+02:00` oder `2026-10-10T10:00:00Z`. |
| `ende` | Termin | Optionales Ende, nicht vor dem Beginn. |
| `beschreibung`, `ort` | Termin | Optional. |
| `vorgang` | alle | Optionale UUID für sichere Wiederholungen (siehe unten). |

Zusätzlich nur bei `buschfunk.entwurf`:

| Feld | Bedeutung |
| --- | --- |
| `ablauf_in_sekunden` | Entwurf läuft nach so vielen Sekunden ab. |
| `verfaellt_um` | Alternativ ein ISO-Zeitpunkt wie bei `beginn`. Nie zusammen mit `ablauf_in_sekunden`. Beide leer: kein automatischer Ablauf. |
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

### Diensträume

Diensträume brauchen eine Buschfunk-Version mit Smart-Home-Diensträumen und den
API-Key aus **Einstellungen → Sicherheit**; ein MCP-Key hat dafür kein Recht.
Ein Raum wird nur über seine **Raumkennung** angesprochen, nie über eine
Chatkennung, und erreicht damit keine anderen Chats.

#### `buschfunk.dienstraum_senden`: An Dienstraum senden

Sendet eine Nachricht als Absender des Dienstraums. Mit `name` wird der Raum
vorher hinzugefügt oder umbenannt; ist er schon so eingerichtet, kostet das
nichts. Ohne `name` muss der Raum bereits bestehen.

| Feld | Bedeutung |
| --- | --- |
| `kennung` | Pflicht. `a–z`, `0–9`, `-`, `_`, 1–32 Zeichen, Anfang und Ende Buchstabe oder Ziffer, z. B. `waschmaschine`. |
| `name` | Optional, 1–64 Zeichen ohne Steuerzeichen; wird Raum- und Absendername. |
| `titel` | Optional, einzeilig, bis 120 Zeichen; steht fett über dem Text. |
| `text` | Pflicht, 1–4000 Zeichen. |
| `wichtig` | Erwähnt dein Konto, damit die Nachricht auch bei „nur Erwähnungen“ klingelt (Vorgabe aus). Stumm, Zurückstellen und die Dienststille „Smart Home“ gelten trotzdem. |
| `bild` | Optional, nur zusammen mit `name`: lokaler Dateipfad (in `allowlist_external_dirs`), PNG, JPEG, WebP oder GIF bis 1 MiB. Wird Raum- und Absenderbild, kein Nachrichtenbild. |
| `bild_entitaet` | Alternativ zu `bild`: eine `image.*`- oder `camera.*`-Entität; ihr aktuelles Bild wird verwendet (höchstens 1 MiB, Kamerabilder werden auf 512 px Breite verkleinert, soweit die Kamera das zulässt). |
| `vorgang` | Optionale UUID; dieselbe UUID erneut gesendet erzeugt keine zweite Nachricht. |

Antwort: `{kennung, vorgang, ereignisId}`, mit `name` zusätzlich `neu`
(`true`, wenn der Raum gerade angelegt wurde).

Ein Raumbild ändert man selten: Jedes neue Bild zählt gegen die 60 Änderungen
je Stunde. Ein Kamera-Schnappschuss ist jedes Mal ein neues Bild; setze ihn
deshalb nicht bei jeder Nachricht, sondern einmal mit
`buschfunk.dienstraum_sicherstellen`. Scheitert das Hinzufügen an der Drossel,
wird auch die Nachricht nicht gesendet.

```yaml
- alias: "Waschmaschine fertig → Buschfunk"
  triggers:
    - trigger: state
      entity_id: sensor.waschmaschine_status
      to: "fertig"
  actions:
    - action: buschfunk.dienstraum_senden
      data:
        kennung: waschmaschine
        name: Waschmaschine
        titel: Waschmaschine
        text: "Die Wäsche ist fertig."
        wichtig: true
```

#### `buschfunk.dienstraum_sicherstellen`: Dienstraum hinzufügen oder ändern

Legt den Raum mit `kennung` und `name` (Pflicht) an oder ändert Name und Bild
(`bild` bzw. `bild_entitaet` wie oben). Ein Aufruf ohne Änderung bewirkt
nichts und zählt nicht gegen die Grenzen. Antwort:
`{kennung, name, chatId, archiviert, erstelltUm, neu}`.

#### `buschfunk.dienstraum_entfernen`: Dienstraum entfernen

Der Absender verlässt den Raum, der Raum wandert in Buschfunk ins Archiv, der
Verlauf bleibt. Die Kennung ist danach wieder frei; ein späteres Hinzufügen
legt einen neuen Raum an.

#### Grenzen und Fehler

Buschfunk erlaubt höchstens 20 aktive Diensträume, 30 Nachrichten je Raum und
Minute, 120 Nachrichten insgesamt je Minute und 60 Änderungen (Anlegen,
Umbenennen, neues Bild) je Stunde. Feldgrenzen, Raumkennung und Bild prüft
schon Home Assistant, bevor eine Anfrage gesendet wird.

| Meldung | Bedeutung |
| --- | --- |
| Buschfunk drosselt Anfragen | Grenze erreicht; die Meldung nennt die Wartezeit aus `Retry-After`. Home Assistant wiederholt nicht von selbst. |
| Key hat kein Recht | Ein MCP-Key ist eingetragen (unter **Neu konfigurieren** den API-Key aus Einstellungen → Sicherheit eintragen) oder die Buschfunk-Version kennt noch keine Diensträume. |
| Dienstraum nicht aktiv | Raum erst hinzufügen oder mit `name` senden. |
| Höchstens 20 Diensträume | Einen Raum entfernen. |
| Auftrag nicht bestätigt | Nachricht: mit derselben `vorgang` wiederholen. Hinzufügen/Entfernen: einfach erneut aufrufen. |

Bei Netzwerkfehlern und HTTP 502/504 wird Hinzufügen und Senden genau einmal
identisch wiederholt (beim Senden mit derselben `vorgang`), Entfernen nicht.

## Sensor

Je Installation ein Sensor **Diensträume**: Zustand ist die Zahl der aktiven
Diensträume, das Attribut `dienstraeume` listet `kennung`, `name`, `chat_id`
und `archiviert`, `grenze` die Höchstzahl. Er fragt alle 5 Minuten und sofort
nach Hinzufügen, Ändern oder Entfernen. Kennt die Buschfunk-Installation keine
Diensträume oder fehlt das Recht, ist der Sensor nicht verfügbar; Nachrichten
und Entwürfe funktionieren weiter.

## Entfernen

1. **Einstellungen → Geräte & Dienste → Buschfunk** → Menü → **Löschen**.
2. Den API-Key in Buschfunk widerrufen.
3. Bei Bedarf das Repository aus HACS entfernen und Home Assistant neu starten.
4. Automationen, die `buschfunk.*`-Aktionen nutzen, anpassen oder deaktivieren.

Bereits gesendete Nachrichten, Entwürfe, geplante Aufträge und Diensträume in
Buschfunk bleiben bestehen; nicht mehr gebrauchte Diensträume vorher mit
`buschfunk.dienstraum_entfernen` ins Archiv verschieben.

## Entwicklung

Siehe [docs/entwicklung.md](docs/entwicklung.md).

## Lizenz

MIT, siehe [LICENSE](LICENSE).

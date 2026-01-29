
# Plex Downloader CLI

Ein modernes und interaktives Kommandozeilen-Tool (CLI), um Filme und TV Shows von einem Plex-Server in **Originalqualität** (Direct Stream) herunterzuladen.

Entwickelt von Patrick Kurmann mit Python, [Typer](https://typer.tiangolo.com/) und [Rich](https://rich.readthedocs.io/).

![Demo Screenshot](assets/demo.png)

## Features

* **Interaktive Suche:** Suche blitzschnell nach Filmen und TV Shows in deinen Plex-Bibliotheken.
* **TV Show Support:** Lade ganze Serien oder einzelne Episoden herunter.
* **Geplanter Download:** Plane Downloads für 2 Uhr morgens mit dem `--at-night` Flag.
* **Medienserver-Integration:** Automatisches Verschieben von Downloads zum Medienserver (lokal oder per rclone zu NAS/Cloud).
* **Originalqualität:** Lädt die rohe Videodatei (z. B. MKV, MP4) herunter, ohne Transcodierung oder Qualitätsverlust.
* **Schicke UI:** Fortschrittsbalken, farbige Ausgaben und formatierte Tabellen.
* **Sicherer Login:** Verbindet sich mit deinen Plex-Zugangsdaten und nutzt Tokens zur Authentifizierung.
* **Konfigurierbar:** Speichert deine Einstellungen (Server, Token, Pfad) lokal ab.

## Installation

### Option 1: Installation via pipx (Empfohlen)
Um das Tool sauber isoliert von deinem System-Python zu nutzen, ist `pipx` der beste Weg.

```bash
# Direkt von GitHub installieren
pipx install git+[https://github.com/kurmann/plex-downloader.git](https://github.com/kurmann/plex-downloader.git)

```

### Option 2: Lokale Entwicklung

Wenn du den Code verändern oder erweitern möchtest:

1. Repository klonen:
```bash
git clone [https://github.com/kurmann/plex-downloader.git](https://github.com/kurmann/plex-downloader.git)
cd plex-downloader

```


2. Virtuelle Umgebung erstellen:
```bash
python3 -m venv .venv
source .venv/bin/activate

```


3. Abhängigkeiten installieren:
```bash
pip install -e .

```

## Benutzung

Sobald das Tool installiert ist, steht dir der Befehl `plex-dl` systemweit zur Verfügung.

### 1. Ersteinrichtung (Konfiguration)

Bevor du starten kannst, musst du dich einmalig einloggen und den gewünschten Server auswählen.

```bash
plex-dl config

```

*Folge den Anweisungen im Terminal, um dich bei plex.tv einzuloggen und deinen Server zu wählen.*

Du kannst `config` auch später nutzen, um einzelne Einstellungen (Server, Download-Pfad, Medienserver-Pfad) anzupassen, ohne alles neu eingeben zu müssen.

### 2. Suchen & Herunterladen

Suche nach einem Film- oder Serientitel. Das Tool zeigt dir alle Treffer an und lässt dich auswählen, welchen du laden möchtest.

```bash
plex-dl search "Inception"

```

Für TV Shows wirst du gefragt, ob du die ganze Serie oder nur eine bestimmte Episode herunterladen möchtest.

#### Geplanter Download (Nachtmodus)

Du kannst Downloads für 2 Uhr morgens (lokale Zeit) planen:

```bash
plex-dl search "Inception" --at-night

```

Im Nachtmodus:
- Wartet die Anwendung aktiv bis 2 Uhr morgens
- Zeigt die verbleibende Wartezeit alle 60 Sekunden an
- Führt den Download automatisch um 2 Uhr aus
- Beendet sich automatisch nach dem Download (auch bei Fehlern)
- Fehler werden in der Konsole angezeigt und bleiben lesbar

**Beispiel:**
```bash
# Normale Download (sofort)
plex-dl search "The Matrix"

# Geplanter Download um 2 Uhr morgens
plex-dl search "The Matrix" --at-night
```

### 3. Medienserver-Integration

Bei der Erstkonfiguration (`plex-dl config`) kannst du optional ein Medienserver-Verzeichnis konfigurieren. Nach jedem erfolgreichen Download werden die Dateien automatisch dorthin verschoben.

**Beispiele:**
- Lokaler Pfad: `/mnt/media` oder `~/Media`
- rclone Remote: `mynas:media/plex` (für NAS oder Cloud-Speicher)

**Vorteile:**
- Automatische Organisation der Medienbibliothek
- Bei Serien wird jede Episode sofort nach Download verschoben → Platz wird für die nächste Episode frei
- Unterstützt sowohl lokale als auch Remote-Ziele via rclone

**Hinweis:** Falls rclone nicht installiert ist, erfolgt bei lokalen Pfaden ein automatischer Fallback auf Python's Standardmethoden.

### Konfiguration

Die Konfigurationsdatei wird standardmäßig hier gespeichert:
`~/.config/plex-downloader/config.yaml`

Dort kannst du bei Bedarf den Standard-Downloadpfad und Medienserver-Pfad manuell anpassen.

**Konfigurationsoptionen:**
- `download_path`: Temporäres Verzeichnis für Downloads
- `media_server_path`: Zielverzeichnis für fertige Downloads (optional, lokal oder rclone remote)
- `token`: Plex Authentifizierungs-Token
- `server_name`: Name deines Plex-Servers

## Projektstruktur

Dieses Projekt nutzt das moderne `src`-Layout für Python-Pakete:

```text
plex-downloader/
├── pyproject.toml       # Abhängigkeiten & Entry Point
├── src/
│   └── plex_downloader/
│       ├── __init__.py
│       ├── main.py      # Die Hauptlogik der Applikation
│       └── modules/
│           ├── downloader.py     # Download-Logik
│           ├── rclone_mover.py   # Medienserver-Integration
│           └── cleanup.py        # Temporäre Dateien bereinigen

```

## Lizenz

Dieses Projekt ist unter der MIT Lizenz veröffentlicht.

## Haftungsausschluss

Dieses Tool ist nur für den persönlichen Gebrauch gedacht. Bitte respektiere das Urheberrecht und lade nur Inhalte herunter, an denen du die Rechte besitzt oder auf die du legitimen Zugriff hast.

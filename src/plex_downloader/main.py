import typer
import yaml
import sys
import os
from pathlib import Path
from datetime import datetime, time, timedelta
import time as time_module
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer
from plexapi.exceptions import Unauthorized
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm

from plex_downloader.modules.downloader import download_video, download_episode, sanitize_filename
from plex_downloader.modules.cleanup import cleanup_temp_files

# --- KONFIGURATION ---
APP_NAME = "plex-downloader"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.yaml"

app = typer.Typer(help="CLI zum Herunterladen von Plex-Filmen und TV Shows in Originalqualität.")
console = Console()

def load_config():
    """Lädt die Konfiguration oder gibt ein leeres Dict zurück."""
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE, "r") as f:
        return yaml.safe_load(f) or {}

def save_config(data):
    """Speichert die Konfiguration in die YAML-Datei."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(data, f)

def calculate_wait_until_2am():
    """Berechnet die Wartezeit bis 2 Uhr morgens in Sekunden."""
    now = datetime.now()
    target_time = time(2, 0)  # 2:00 AM
    
    # Erstelle datetime für heute um 2 Uhr
    today_target = datetime.combine(now.date(), target_time)
    
    # Wenn es bereits nach 2 Uhr ist, nimm morgen 2 Uhr
    if now.time() >= target_time:
        tomorrow = now.date() + timedelta(days=1)
        target_datetime = datetime.combine(tomorrow, target_time)
    else:
        target_datetime = today_target
    
    # Berechne die Differenz in Sekunden
    wait_seconds = (target_datetime - now).total_seconds()
    return wait_seconds, target_datetime

def wait_until_2am():
    """Wartet bis 2 Uhr morgens und zeigt die Restzeit an."""
    wait_seconds, target_datetime = calculate_wait_until_2am()
    
    console.print(f"\n[bold cyan]Geplanter Download um 2:00 Uhr[/bold cyan]")
    console.print(f"Aktuelle Zeit: {datetime.now().strftime('%H:%M:%S')}")
    console.print(f"Zielzeit: {target_datetime.strftime('%d.%m.%Y %H:%M:%S')}")
    console.print(f"Wartezeit: {int(wait_seconds // 3600)} Stunden, {int((wait_seconds % 3600) // 60)} Minuten\n")
    console.print("[yellow]Die Anwendung wartet nun bis 2 Uhr morgens...[/yellow]")
    console.print("[dim]Drücke Ctrl+C zum Abbrechen[/dim]\n")
    
    try:
        # Warte in Intervallen und zeige Fortschritt
        interval = 60  # Alle 60 Sekunden aktualisieren
        elapsed = 0
        
        while elapsed < wait_seconds:
            time_to_wait = min(interval, wait_seconds - elapsed)
            time_module.sleep(time_to_wait)
            elapsed += time_to_wait
            
            remaining = wait_seconds - elapsed
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            
            if remaining > 0:
                console.print(f"[dim]Verbleibende Zeit: {hours:02d}:{minutes:02d} Stunden[/dim]")
        
        console.print("\n[bold green]2 Uhr erreicht! Starte Download...[/bold green]\n")
        return True
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Warten abgebrochen. Anwendung wird beendet.[/yellow]")
        sys.exit(0)

def configure_plex_account(existing_config):
    """Konfiguriert nur Plex Account und Server."""
    console.print("\n[bold cyan]Plex Account Konfiguration[/bold cyan]")
    
    result = get_plex_credentials_and_server()
    if result:
        token, server_name = result
        existing_config["token"] = token
        existing_config["server_name"] = server_name
        save_config(existing_config)
        console.print(f"[bold green]Plex Account Konfiguration gespeichert![/bold green]")
        return True
    return False

def get_plex_credentials_and_server():
    """Fragt Plex Credentials ab und lässt Server auswählen. Gibt (token, server_name) zurück oder None bei Fehler."""
    username = Prompt.ask("Plex Benutzername/Email")
    password = Prompt.ask("Plex Passwort", password=True)
    
    try:
        with console.status("[green]Logge ein bei plex.tv..."):
            account = MyPlexAccount(username, password)
        
        console.print(f"[green]Erfolgreich eingeloggt als {account.username}![/green]")
        
        # Server auflisten
        resources = [r for r in account.resources() if r.product == 'Plex Media Server']
        
        if not resources:
            console.print("[red]Keine Server gefunden![/red]")
            return None
        
        console.print("\nVerfügbare Server:")
        for idx, res in enumerate(resources, 1):
            console.print(f"{idx}. [bold]{res.name}[/bold] - {res.productVersion}")
        
        choice = int(Prompt.ask("Wähle einen Server (Nummer)", choices=[str(i) for i in range(1, len(resources)+1)]))
        selected_server = resources[choice-1]
        
        return (account.authenticationToken, selected_server.name)
        
    except Unauthorized:
        console.print("[bold red]Login fehlgeschlagen. Falsches Passwort?[/bold red]")
        return None
    except Exception as e:
        console.print(f"[bold red]Fehler:[/bold red] {e}")
        return None

def configure_download_path(existing_config):
    """Konfiguriert nur Download-Verzeichnis."""
    console.print("\n[bold cyan]Download-Verzeichnis Konfiguration[/bold cyan]")
    
    default_download_path = existing_config.get("download_path", str(Path.home() / "Downloads"))
    download_path = Prompt.ask(
        "Download-Verzeichnis (temporär)", 
        default=default_download_path
    )
    
    result = validate_and_create_directory(download_path, "Download-Verzeichnis")
    if result:
        existing_config["download_path"] = result
        save_config(existing_config)
        console.print(f"[bold green]Download-Verzeichnis gespeichert![/bold green]")
        return True
    return False

def configure_media_path(existing_config):
    """Konfiguriert nur Medienserver-Verzeichnis."""
    console.print("\n[bold cyan]Medienserver-Verzeichnis Konfiguration[/bold cyan]")
    
    default_media_path = existing_config.get("media_server_path", str(Path.home() / "Media"))
    media_path = Prompt.ask(
        "Medienserver-Verzeichnis (Ziel für fertige Downloads, z.B. lokaler Pfad oder rclone remote wie 'mynas:media') (ohne Quotes eingeben)",
        default=default_media_path
    )
    
    result = validate_media_path(media_path)
    if result:
        existing_config["media_server_path"] = result
        save_config(existing_config)
        console.print(f"[bold green]Medienserver-Verzeichnis gespeichert![/bold green]")
        return True
    return False

def validate_and_create_directory(path_str, path_description="Verzeichnis"):
    """Validiert und erstellt ein lokales Verzeichnis. Gibt den Pfad als String zurück oder None."""
    directory = Path(path_str).expanduser().resolve()
    if not directory.exists():
        if Confirm.ask(f"Das Verzeichnis existiert nicht. Soll es erstellt werden?"):
            try:
                directory.mkdir(parents=True, exist_ok=True)
                console.print(f"[green]Verzeichnis erstellt: {directory}[/green]")
                return str(directory)
            except Exception as e:
                console.print(f"[red]Fehler beim Erstellen des Verzeichnisses: {e}[/red]")
                return None
        else:
            console.print(f"[yellow]{path_description} wurde nicht konfiguriert[/yellow]")
            return None
    return str(directory)

def validate_media_path(media_path):
    """Validiert einen Medienserver-Pfad (lokal oder rclone remote). Gibt den Pfad als String zurück oder None."""
    # Prüfe ob es sich um einen rclone remote handelt (enthält ":")
    # Sichere Prüfung für Windows Laufwerksbuchstaben
    is_remote = ":" in media_path and not media_path.startswith("/") and not (len(media_path) >= 2 and media_path[1] == ":")
    
    if is_remote:
        # Für rclone remotes speichern wir den Pfad direkt als String
        console.print(f"[cyan]Erkannte rclone remote: {media_path}[/cyan]")
        return media_path
    else:
        # Für lokale Pfade validieren und ggf. erstellen
        return validate_and_create_directory(media_path, "Medienserver-Verzeichnis")



def get_plex_server() -> PlexServer:
    """Verbindet sich mit dem Plex Server basierend auf der Config."""
    config_data = load_config()
    
    # Check ob wir bereits configuriert sind
    if not config_data.get("token") or not config_data.get("server_name"):
        console.print("[yellow]Keine Konfiguration gefunden. Starte Konfiguration...[/yellow]")
        config()
        config_data = load_config() # Reload nach Config

    token = config_data.get("token")
    server_name = config_data.get("server_name")
    
    # Spinner starten während Verbindung
    with console.status(f"[bold green]Verbinde mit Server '{server_name}'..."):
        try:
            # Wir nutzen MyPlex, um die Ressource zu finden (funktioniert remote & lokal)
            account = MyPlexAccount(token=token)
            resource = account.resource(server_name)
            plex = resource.connect()
            return plex
        except Exception as e:
            console.print(f"[bold red]Fehler bei der Verbindung:[/bold red] {e}")
            # Falls Token ungültig, Config anbieten
            if Confirm.ask("Möchtest du die Konfiguration erneut ausführen?"):
                config()
                return get_plex_server()
            else:
                sys.exit(1)

@app.command()
def config():
    """Interaktive Konfiguration für Account, Server-Wahl und Pfade."""
    console.print("[bold blue]--- Plex Downloader Konfiguration ---[/bold blue]")
    
    # Lade existierende Konfiguration
    existing_config = load_config()
    has_config = bool(existing_config.get("token"))
    
    # Wenn bereits konfiguriert, zeige Menü zur Auswahl
    if has_config:
        console.print("\n[green]Bestehende Konfiguration gefunden.[/green]")
        console.print("\nWas möchtest du konfigurieren?")
        console.print("1. Plex Account (Server & Token)")
        console.print("2. Download-Verzeichnis")
        console.print("3. Medienserver-Verzeichnis")
        console.print("4. Alles neu konfigurieren")
        console.print("q. Abbruch")
        
        choice = Prompt.ask(
            "Wähle eine Option",
            choices=["1", "2", "3", "4", "q"],
            default="q"
        )
        
        if choice == "q":
            return
        elif choice == "1":
            configure_plex_account(existing_config)
            return
        elif choice == "2":
            configure_download_path(existing_config)
            return
        elif choice == "3":
            configure_media_path(existing_config)
            return
        # choice == "4" falls through to full configuration
    
    # Volle Konfiguration (Ersteinrichtung oder Option 4)
    result = get_plex_credentials_and_server()
    if not result:
        return
    
    token, server_name = result
    
    # Download-Pfad abfragen
    default_download_path = str(Path.home() / "Downloads")
    download_path = Prompt.ask(
        "Download-Verzeichnis (temporär)", 
        default=default_download_path
    )
    
    # Pfad validieren und ggf. erstellen
    download_dir_str = validate_and_create_directory(download_path, "Download-Verzeichnis")
    if not download_dir_str:
        # Fallback zum Standard-Verzeichnis
        console.print("[yellow]Verwende Standard-Verzeichnis[/yellow]")
        download_dir = Path(default_download_path)
        download_dir.mkdir(parents=True, exist_ok=True)
        download_dir_str = str(download_dir)
    
    # Medienserver-Pfad abfragen
    default_media_path = str(Path.home() / "Media")
    media_path = Prompt.ask(
        "Medienserver-Verzeichnis (Ziel für fertige Downloads, z.B. lokaler Pfad oder rclone remote wie 'mynas:media')",
        default=default_media_path
    )
    
    media_dir_str = validate_media_path(media_path)
    if not media_dir_str:
        # Fallback zum Standard-Verzeichnis
        console.print("[yellow]Verwende Standard-Verzeichnis[/yellow]")
        media_dir = Path(default_media_path)
        media_dir.mkdir(parents=True, exist_ok=True)
        media_dir_str = str(media_dir)
    
    # Config speichern
    config_data = {
        "token": token,
        "server_name": server_name,
        "download_path": download_dir_str,
        "media_server_path": media_dir_str
    }
    save_config(config_data)
    console.print(f"[bold green]Konfiguration gespeichert unter {CONFIG_FILE}![/bold green]")

@app.command()
def setup():
    """Alias für 'config' - wird aus Kompatibilitätsgründen beibehalten."""
    console.print("[yellow]Hinweis: 'setup' wurde umbenannt zu 'config'. Bitte verwende zukünftig 'plex-dl config'.[/yellow]\n")
    config()

@app.command()
def search(
    query: str,
    at_night: bool = typer.Option(False, "--at-night", help="Plant den Download für 2 Uhr morgens")
):
    """Sucht nach Filmen und TV Shows und bietet Download an."""
    # Prüfe ob Konfiguration existiert
    config_data = load_config()
    if not config_data.get("token") or not config_data.get("server_name"):
        console.print("[yellow]Keine Konfiguration gefunden. Starte Konfiguration...[/yellow]")
        config()
        config_data = load_config()
        # Prüfe erneut ob Konfiguration nun vorhanden ist
        if not config_data.get("token") or not config_data.get("server_name"):
            console.print("[red]Konfiguration unvollständig. Bitte führe 'plex-dl config' aus.[/red]")
            sys.exit(1)
    
    # Wenn geplanter Download, warte bis 2 Uhr
    if at_night:
        wait_until_2am()
    
    # Cleanup alte temp Dateien vor der Suche
    cleanup_temp_files(config_data.get("download_path"))
    
    plex = get_plex_server()
    
    with console.status(f"Suche nach '{query}'..."):
        # Suche über alle Bibliotheken (Filme und TV Shows)
        movie_results = plex.search(query, mediatype='movie')
        show_results = plex.search(query, mediatype='show')
        results = movie_results + show_results
    
    if not results:
        console.print(f"[yellow]Keine Ergebnisse gefunden für '{query}'.[/yellow]")
        # Beende die Anwendung automatisch wenn --at-night verwendet wurde
        if at_night:
            console.print("[yellow]Anwendung wird beendet.[/yellow]")
            sys.exit(0)
        return

    # Tabelle zur Anzeige
    table = Table(title=f"Suchergebnisse für '{query}'")
    table.add_column("Nr.", style="cyan", justify="right")
    table.add_column("Typ", style="yellow")
    table.add_column("Titel", style="magenta")
    table.add_column("Jahr", style="green")
    table.add_column("Info", style="blue")

    for idx, item in enumerate(results, 1):
        # Bestimme Typ und Info
        if item.type == 'movie':
            item_type = "Film"
            info = item.media[0].videoResolution if item.media else "Unbekannt"
        else:  # show
            item_type = "Serie"
            # Anzahl Staffeln
            info = f"{len(item.seasons())} Staffel(n)"
        
        year = getattr(item, 'year', 'N/A')
        table.add_row(str(idx), item_type, item.title, str(year), str(info))

    console.print(table)
    
    # Interaktive Auswahl
    choice = Prompt.ask(
        "Welchen Inhalt herunterladen? (Nummer eingeben, 'q' für Abbruch)", 
        default="q"
    )
    
    if choice.lower() == 'q':
        # Beende die Anwendung automatisch wenn --at-night verwendet wurde
        if at_night:
            console.print("[yellow]Anwendung wird beendet.[/yellow]")
            sys.exit(0)
        return

    try:
        selection_idx = int(choice) - 1
        if 0 <= selection_idx < len(results):
            selected_item = results[selection_idx]
            try:
                if selected_item.type == 'movie':
                    config_data = load_config()
                    download_dir = Path(config_data.get("download_path", Path.home() / "Downloads"))
                    # Keep media_server_path as string to support both local and remote paths
                    media_server_path = config_data.get("media_server_path")
                    download_video(selected_item, plex, download_dir, media_server_path)
                else:  # show
                    handle_show_download(selected_item, plex, at_night)
                
                # Erfolgreicher Download - beende die Anwendung wenn --at-night verwendet wurde
                if at_night:
                    console.print("\n[bold green]Download abgeschlossen. Anwendung wird beendet.[/bold green]")
                    sys.exit(0)
                    
            except Exception as e:
                console.print(f"[bold red]Fehler beim Download:[/bold red] {e}")
                # Beende die Anwendung auch bei Fehler wenn --at-night verwendet wurde
                if at_night:
                    console.print("[red]Anwendung wird aufgrund eines Fehlers beendet.[/red]")
                    sys.exit(1)
                else:
                    raise
        else:
            console.print("[red]Ungültige Auswahl.[/red]")
            # Beende die Anwendung automatisch wenn --at-night verwendet wurde
            if at_night:
                console.print("[yellow]Anwendung wird beendet.[/yellow]")
                sys.exit(0)
    except ValueError:
        console.print("[red]Bitte eine Zahl eingeben.[/red]")
        # Beende die Anwendung automatisch wenn --at-night verwendet wurde
        if at_night:
            console.print("[yellow]Anwendung wird beendet.[/yellow]")
            sys.exit(0)

def handle_show_download(show, plex, at_night: bool = False):
    """Behandelt den Download einer TV-Show."""
    console.print(f"\n[bold magenta]{show.title}[/bold magenta]")
    console.print("\nWas möchtest du herunterladen?")
    console.print("1. Ganze Serie")
    console.print("2. Bestimmte Episode")
    console.print("3. Ab bestimmter Episode bis Ende der Staffel")
    console.print("q. Abbruch")
    
    choice = Prompt.ask(
        "Wähle eine Option",
        choices=["1", "2", "3", "q"],
        default="q"
    )
    
    if choice == "q":
        # Beende die Anwendung automatisch wenn --at-night verwendet wurde
        if at_night:
            console.print("[yellow]Anwendung wird beendet.[/yellow]")
            sys.exit(0)
        return
    elif choice == "1":
        # Ganze Serie herunterladen
        if Confirm.ask(f"Möchtest du wirklich die ganze Serie '{show.title}' herunterladen?"):
            download_entire_show(show, plex, at_night)
            # Erfolgreicher Download - beende die Anwendung wenn --at-night verwendet wurde
            if at_night:
                console.print("\n[bold green]Download abgeschlossen. Anwendung wird beendet.[/bold green]")
                sys.exit(0)
        else:
            # Benutzer hat abgebrochen
            if at_night:
                console.print("[yellow]Download abgebrochen. Anwendung wird beendet.[/yellow]")
                sys.exit(0)
    elif choice == "2":
        # Bestimmte Episode auswählen
        select_and_download_episode(show, plex, at_night)
    elif choice == "3":
        # Ab bestimmter Episode bis Ende der Staffel
        download_from_episode_onwards(show, plex, at_night)

def select_and_download_episode(show, plex, at_night: bool = False):
    """Lässt den Benutzer eine bestimmte Episode auswählen und lädt sie herunter."""
    seasons = show.seasons()
    
    # Staffel auswählen
    console.print("\n[bold]Verfügbare Staffeln:[/bold]")
    for idx, season in enumerate(seasons, 1):
        console.print(f"{idx}. {season.title} ({len(season.episodes())} Episoden)")
    
    season_choice = Prompt.ask(
        "Welche Staffel? (Nummer eingeben, 'q' für Abbruch)",
        default="q"
    )
    
    if season_choice.lower() == "q":
        # Beende die Anwendung automatisch wenn --at-night verwendet wurde
        if at_night:
            console.print("[yellow]Anwendung wird beendet.[/yellow]")
            sys.exit(0)
        return
    
    try:
        season_idx = int(season_choice) - 1
        if 0 <= season_idx < len(seasons):
            selected_season = seasons[season_idx]
        else:
            console.print("[red]Ungültige Auswahl.[/red]")
            # Beende die Anwendung automatisch wenn --at-night verwendet wurde
            if at_night:
                console.print("[yellow]Anwendung wird beendet.[/yellow]")
                sys.exit(0)
            return
    except ValueError:
        console.print("[red]Bitte eine Zahl eingeben.[/red]")
        # Beende die Anwendung automatisch wenn --at-night verwendet wurde
        if at_night:
            console.print("[yellow]Anwendung wird beendet.[/yellow]")
            sys.exit(0)
        return
    
    # Episode auswählen
    episodes = selected_season.episodes()
    console.print(f"\n[bold]Episoden in {selected_season.title}:[/bold]")
    
    table = Table()
    table.add_column("Nr.", style="cyan", justify="right")
    table.add_column("Episode", style="magenta")
    table.add_column("Titel", style="green")
    
    for idx, episode in enumerate(episodes, 1):
        episode_num = f"S{episode.seasonNumber:02d}E{episode.index:02d}"
        table.add_row(str(idx), episode_num, episode.title)
    
    console.print(table)
    
    episode_choice = Prompt.ask(
        "Welche Episode herunterladen? (Nummer eingeben, 'q' für Abbruch)",
        default="q"
    )
    
    if episode_choice.lower() == "q":
        # Beende die Anwendung automatisch wenn --at-night verwendet wurde
        if at_night:
            console.print("[yellow]Anwendung wird beendet.[/yellow]")
            sys.exit(0)
        return
    
    try:
        episode_idx = int(episode_choice) - 1
        if 0 <= episode_idx < len(episodes):
            # Erstelle einen Ordner für die Show (Konsistenz mit vollständigem Download)
            config_data = load_config()
            download_dir = Path(config_data.get("download_path", Path.home() / "Downloads"))
            # Keep media_server_path as string to support both local and remote paths
            media_server_path = config_data.get("media_server_path")
            show_dir = download_dir / sanitize_filename(show.title)
            show_dir.mkdir(parents=True, exist_ok=True)
            
            download_episode(episodes[episode_idx], show, plex, show_dir, skip_existing_check=False, media_server_path=media_server_path)
            
            # Erfolgreicher Download - beende die Anwendung wenn --at-night verwendet wurde
            if at_night:
                console.print("\n[bold green]Download abgeschlossen. Anwendung wird beendet.[/bold green]")
                sys.exit(0)
        else:
            console.print("[red]Ungültige Auswahl.[/red]")
            # Beende die Anwendung automatisch wenn --at-night verwendet wurde
            if at_night:
                console.print("[yellow]Anwendung wird beendet.[/yellow]")
                sys.exit(0)
    except ValueError:
        console.print("[red]Bitte eine Zahl eingeben.[/red]")
        # Beende die Anwendung automatisch wenn --at-night verwendet wurde
        if at_night:
            console.print("[yellow]Anwendung wird beendet.[/yellow]")
            sys.exit(0)

def download_from_episode_onwards(show, plex, at_night: bool = False):
    """Lädt alle Episoden ab einer bestimmten Episode bis zum Ende der Staffel herunter."""
    seasons = show.seasons()
    
    # Staffel auswählen
    console.print("\n[bold]Verfügbare Staffeln:[/bold]")
    for idx, season in enumerate(seasons, 1):
        console.print(f"{idx}. {season.title} ({len(season.episodes())} Episoden)")
    
    season_choice = Prompt.ask(
        "Welche Staffel? (Nummer eingeben, 'q' für Abbruch)",
        default="q"
    )
    
    if season_choice.lower() == "q":
        # Beende die Anwendung automatisch wenn --at-night verwendet wurde
        if at_night:
            console.print("[yellow]Anwendung wird beendet.[/yellow]")
            sys.exit(0)
        return
    
    try:
        season_idx = int(season_choice) - 1
        if 0 <= season_idx < len(seasons):
            selected_season = seasons[season_idx]
        else:
            console.print("[red]Ungültige Auswahl.[/red]")
            # Beende die Anwendung automatisch wenn --at-night verwendet wurde
            if at_night:
                console.print("[yellow]Anwendung wird beendet.[/yellow]")
                sys.exit(0)
            return
    except ValueError:
        console.print("[red]Bitte eine Zahl eingeben.[/red]")
        # Beende die Anwendung automatisch wenn --at-night verwendet wurde
        if at_night:
            console.print("[yellow]Anwendung wird beendet.[/yellow]")
            sys.exit(0)
        return
    
    # Start-Episode auswählen
    episodes = selected_season.episodes()
    console.print(f"\n[bold]Episoden in {selected_season.title}:[/bold]")
    
    table = Table()
    table.add_column("Nr.", style="cyan", justify="right")
    table.add_column("Episode", style="magenta")
    table.add_column("Titel", style="green")
    
    for idx, episode in enumerate(episodes, 1):
        episode_num = f"S{episode.seasonNumber:02d}E{episode.index:02d}"
        table.add_row(str(idx), episode_num, episode.title)
    
    console.print(table)
    
    start_episode_choice = Prompt.ask(
        "Ab welcher Episode herunterladen? (Nummer eingeben, 'q' für Abbruch)",
        default="q"
    )
    
    if start_episode_choice.lower() == "q":
        # Beende die Anwendung automatisch wenn --at-night verwendet wurde
        if at_night:
            console.print("[yellow]Anwendung wird beendet.[/yellow]")
            sys.exit(0)
        return
    
    try:
        start_episode_idx = int(start_episode_choice) - 1
        if 0 <= start_episode_idx < len(episodes):
            # Bestätigung
            episodes_to_download = len(episodes) - start_episode_idx
            start_ep_num = f"S{episodes[start_episode_idx].seasonNumber:02d}E{episodes[start_episode_idx].index:02d}"
            if not Confirm.ask(f"Möchtest du {episodes_to_download} Episode(n) ab {start_ep_num} herunterladen?"):
                console.print("[yellow]Download abgebrochen.[/yellow]")
                if at_night:
                    console.print("[yellow]Anwendung wird beendet.[/yellow]")
                    sys.exit(0)
                return
            
            # Download-Verzeichnis vorbereiten
            config_data = load_config()
            download_dir = Path(config_data.get("download_path", Path.home() / "Downloads"))
            # Keep media_server_path as string to support both local and remote paths
            media_server_path = config_data.get("media_server_path")
            show_dir = download_dir / sanitize_filename(show.title)
            show_dir.mkdir(parents=True, exist_ok=True)
            
            console.print(f"\n[bold cyan]Lade Episoden ab {start_ep_num} herunter...[/bold cyan]")
            
            # Download-Statistik
            downloaded_count = 0
            skipped_count = 0
            
            # Lade alle Episoden ab der ausgewählten bis zum Ende
            for episode_idx in range(start_episode_idx, len(episodes)):
                episode = episodes[episode_idx]
                episode_num = f"S{episode.seasonNumber:02d}E{episode.index:02d}"
                
                console.print(f"\n[cyan]Episode {episode_idx - start_episode_idx + 1}/{episodes_to_download}: {episode_num}[/cyan]")
                
                # Prüfe ob Episode bereits existiert
                if not episode.media or not episode.media[0].parts:
                    console.print(f"[yellow]Keine Mediendatei für {episode.title}[/yellow]")
                    continue
                    
                part = episode.media[0].parts[0]
                filename = f"{show.title} - {episode_num} - {episode.title}.{part.container}"
                filename = sanitize_filename(filename)
                filepath = show_dir / filename
                
                if filepath.exists():
                    console.print(f"[yellow]Bereits vorhanden, überspringe: {filename}[/yellow]")
                    skipped_count += 1
                    continue
                
                if download_episode(episode, show, plex, show_dir, skip_existing_check=True, media_server_path=media_server_path):
                    downloaded_count += 1
            
            console.print(f"\n[bold green]Fertig! {downloaded_count} Episode(n) heruntergeladen, {skipped_count} übersprungen. 🎉[/bold green]")
            
            # Erfolgreicher Download - beende die Anwendung wenn --at-night verwendet wurde
            if at_night:
                console.print("\n[bold green]Download abgeschlossen. Anwendung wird beendet.[/bold green]")
                sys.exit(0)
        else:
            console.print("[red]Ungültige Auswahl.[/red]")
            # Beende die Anwendung automatisch wenn --at-night verwendet wurde
            if at_night:
                console.print("[yellow]Anwendung wird beendet.[/yellow]")
                sys.exit(0)
    except ValueError:
        console.print("[red]Bitte eine Zahl eingeben.[/red]")
        # Beende die Anwendung automatisch wenn --at-night verwendet wurde
        if at_night:
            console.print("[yellow]Anwendung wird beendet.[/yellow]")
            sys.exit(0)

def download_entire_show(show, plex, at_night: bool = False):
    """Lädt alle Episoden einer TV-Show herunter."""
    config_data = load_config()
    download_dir = Path(config_data.get("download_path", Path.home() / "Downloads"))
    # Keep media_server_path as string to support both local and remote paths
    media_server_path = config_data.get("media_server_path")
    
    # Erstelle einen Ordner für die Show
    show_dir = download_dir / sanitize_filename(show.title)
    show_dir.mkdir(parents=True, exist_ok=True)
    
    console.print(f"\n[bold cyan]Lade alle Episoden von '{show.title}' herunter...[/bold cyan]")
    
    seasons = show.seasons()
    total_episodes = sum(len(season.episodes()) for season in seasons)
    
    console.print(f"Insgesamt {total_episodes} Episode(n) in {len(seasons)} Staffel(n)")
    
    episode_count = 0
    skipped_count = 0
    for season in seasons:
        for episode in season.episodes():
            episode_count += 1
            console.print(f"\n[cyan]Episode {episode_count}/{total_episodes}[/cyan]")
            
            # Prüfe ob Episode bereits existiert
            if not episode.media or not episode.media[0].parts:
                console.print(f"[yellow]Keine Mediendatei für {episode.title}[/yellow]")
                continue
                
            part = episode.media[0].parts[0]
            episode_num = f"S{episode.seasonNumber:02d}E{episode.index:02d}"
            filename = f"{show.title} - {episode_num} - {episode.title}.{part.container}"
            filename = sanitize_filename(filename)
            filepath = show_dir / filename
            
            if filepath.exists():
                console.print(f"[yellow]Bereits vorhanden, überspringe: {filename}[/yellow]")
                skipped_count += 1
                continue
                
            download_episode(episode, show, plex, show_dir, skip_existing_check=True, media_server_path=media_server_path)
    
    console.print(f"\n[bold green]Fertig! {episode_count - skipped_count} Episode(n) heruntergeladen, {skipped_count} übersprungen. 🎉[/bold green]")



def start():
    app()

if __name__ == "__main__":
    start()
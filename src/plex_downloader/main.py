import typer
import yaml
import sys
import os
from pathlib import Path
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



def get_plex_server() -> PlexServer:
    """Verbindet sich mit dem Plex Server basierend auf der Config."""
    config = load_config()
    
    # Check ob wir bereits configuriert sind
    if not config.get("token") or not config.get("server_name"):
        console.print("[yellow]Keine Konfiguration gefunden. Starten Setup...[/yellow]")
        setup()
        config = load_config() # Reload nach Setup

    token = config.get("token")
    server_name = config.get("server_name")
    
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
            # Falls Token ungültig, Setup anbieten
            if Confirm.ask("Möchtest du das Setup erneut ausführen?"):
                setup()
                return get_plex_server()
            else:
                sys.exit(1)

@app.command()
def setup():
    """Interaktives Setup für Account und Server-Wahl."""
    console.print("[bold blue]--- Plex Downloader Setup ---[/bold blue]")
    
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
            return

        console.print("\nVerfügbare Server:")
        for idx, res in enumerate(resources, 1):
            # Wir zeigen einfach nur den Namen an, das ist sicherer
            console.print(f"{idx}. [bold]{res.name}[/bold] - {res.productVersion}")
            
        choice = int(Prompt.ask("Wähle einen Server (Nummer)", choices=[str(i) for i in range(1, len(resources)+1)]))
        selected_server = resources[choice-1]
        
        # Download-Pfad abfragen
        default_download_path = str(Path.home() / "Downloads")
        download_path = Prompt.ask(
            "Download-Verzeichnis (temporär)", 
            default=default_download_path
        )
        
        # Pfad validieren und ggf. erstellen
        download_dir = Path(download_path).expanduser().resolve()
        if not download_dir.exists():
            if Confirm.ask(f"Das Verzeichnis existiert nicht. Soll es erstellt werden?"):
                download_dir.mkdir(parents=True, exist_ok=True)
                console.print(f"[green]Verzeichnis erstellt: {download_dir}[/green]")
            else:
                console.print("[yellow]Verwende Standard-Verzeichnis[/yellow]")
                download_dir = Path(default_download_path)
                download_dir.mkdir(parents=True, exist_ok=True)
        
        # Medienserver-Pfad abfragen
        default_media_path = str(Path.home() / "Media")
        media_path = Prompt.ask(
            "Medienserver-Verzeichnis (Ziel für fertige Downloads, z.B. lokaler Pfad oder rclone remote wie 'mynas:media')",
            default=default_media_path
        )
        
        # Prüfe ob es sich um einen rclone remote handelt (enthält ":")
        is_remote = ":" in media_path and not media_path.startswith("/") and not (len(media_path) > 1 and media_path[1] == ":")
        
        if is_remote:
            # Für rclone remotes speichern wir den Pfad direkt als String
            console.print(f"[cyan]Erkannte rclone remote: {media_path}[/cyan]")
            media_dir_str = media_path
        else:
            # Für lokale Pfade validieren und ggf. erstellen
            media_dir = Path(media_path).expanduser().resolve()
            if not media_dir.exists():
                if Confirm.ask(f"Das Verzeichnis existiert nicht. Soll es erstellt werden?"):
                    media_dir.mkdir(parents=True, exist_ok=True)
                    console.print(f"[green]Verzeichnis erstellt: {media_dir}[/green]")
                else:
                    console.print("[yellow]Verwende Standard-Verzeichnis[/yellow]")
                    media_dir = Path(default_media_path)
                    media_dir.mkdir(parents=True, exist_ok=True)
            media_dir_str = str(media_dir)
        
        # Config speichern
        config = {
            "token": account.authenticationToken,
            "server_name": selected_server.name,
            "download_path": str(download_dir),
            "media_server_path": media_dir_str
        }
        save_config(config)
        console.print(f"[bold green]Konfiguration gespeichert unter {CONFIG_FILE}![/bold green]")
        
    except Unauthorized:
        console.print("[bold red]Login fehlgeschlagen. Falsches Passwort?[/bold red]")
    except Exception as e:
        console.print(f"[bold red]Fehler:[/bold red] {e}")

@app.command()
def search(query: str):
    """Sucht nach Filmen und TV Shows und bietet Download an."""
    # Cleanup alte temp Dateien vor der Suche
    config = load_config()
    cleanup_temp_files(config.get("download_path"))
    
    plex = get_plex_server()
    
    with console.status(f"Suche nach '{query}'..."):
        # Suche über alle Bibliotheken (Filme und TV Shows)
        movie_results = plex.search(query, mediatype='movie')
        show_results = plex.search(query, mediatype='show')
        results = movie_results + show_results
    
    if not results:
        console.print(f"[yellow]Keine Ergebnisse gefunden für '{query}'.[/yellow]")
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
        return

    try:
        selection_idx = int(choice) - 1
        if 0 <= selection_idx < len(results):
            selected_item = results[selection_idx]
            if selected_item.type == 'movie':
                config = load_config()
                download_dir = Path(config.get("download_path", Path.home() / "Downloads"))
                # Keep media_server_path as string to support both local and remote paths
                media_server_path = config.get("media_server_path")
                download_video(selected_item, plex, download_dir, media_server_path)
            else:  # show
                handle_show_download(selected_item, plex)
        else:
            console.print("[red]Ungültige Auswahl.[/red]")
    except ValueError:
        console.print("[red]Bitte eine Zahl eingeben.[/red]")

def handle_show_download(show, plex):
    """Behandelt den Download einer TV-Show."""
    console.print(f"\n[bold magenta]{show.title}[/bold magenta]")
    console.print("\nWas möchtest du herunterladen?")
    console.print("1. Ganze Serie")
    console.print("2. Bestimmte Episode")
    console.print("q. Abbruch")
    
    choice = Prompt.ask(
        "Wähle eine Option",
        choices=["1", "2", "q"],
        default="q"
    )
    
    if choice == "q":
        return
    elif choice == "1":
        # Ganze Serie herunterladen
        if Confirm.ask(f"Möchtest du wirklich die ganze Serie '{show.title}' herunterladen?"):
            download_entire_show(show, plex)
    elif choice == "2":
        # Bestimmte Episode auswählen
        select_and_download_episode(show, plex)

def select_and_download_episode(show, plex):
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
        return
    
    try:
        season_idx = int(season_choice) - 1
        if 0 <= season_idx < len(seasons):
            selected_season = seasons[season_idx]
        else:
            console.print("[red]Ungültige Auswahl.[/red]")
            return
    except ValueError:
        console.print("[red]Bitte eine Zahl eingeben.[/red]")
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
        return
    
    try:
        episode_idx = int(episode_choice) - 1
        if 0 <= episode_idx < len(episodes):
            # Erstelle einen Ordner für die Show (Konsistenz mit vollständigem Download)
            config = load_config()
            download_dir = Path(config.get("download_path", Path.home() / "Downloads"))
            # Keep media_server_path as string to support both local and remote paths
            media_server_path = config.get("media_server_path")
            show_dir = download_dir / sanitize_filename(show.title)
            show_dir.mkdir(parents=True, exist_ok=True)
            
            download_episode(episodes[episode_idx], show, plex, show_dir, skip_existing_check=False, media_server_path=media_server_path)
        else:
            console.print("[red]Ungültige Auswahl.[/red]")
    except ValueError:
        console.print("[red]Bitte eine Zahl eingeben.[/red]")

def download_entire_show(show, plex):
    """Lädt alle Episoden einer TV-Show herunter."""
    config = load_config()
    download_dir = Path(config.get("download_path", Path.home() / "Downloads"))
    # Keep media_server_path as string to support both local and remote paths
    media_server_path = config.get("media_server_path")
    
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
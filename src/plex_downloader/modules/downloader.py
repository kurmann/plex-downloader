"""Download-Modul für Plex-Medien."""

import requests
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TransferSpeedColumn, TimeRemainingColumn
from rich.prompt import Confirm

console = Console()


def sanitize_filename(filename: str) -> str:
    """Entfernt ungültige Zeichen aus Dateinamen."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '-')
    # Mehrfache Bindestriche durch einen ersetzen
    while '--' in filename:
        filename = filename.replace('--', '-')
    # Bindestriche am Anfang und Ende entfernen
    filename = filename.strip('-').strip()
    # Maximale Länge begrenzen (255 ist typisches Filesystem-Limit)
    if len(filename) > 200:  # Etwas Puffer für Erweiterung
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:200] + ('.' + ext if ext else '')
    return filename


def download_file(download_url: str, filepath: Path, temp_filepath: Path, filename: str) -> bool:
    """
    Lädt eine Datei von einer URL mit Fortschrittsbalken herunter.
    
    Args:
        download_url: Die URL der Datei
        filepath: Der finale Zielpfad
        temp_filepath: Der temporäre Pfad während des Downloads
        filename: Der Dateiname für die Anzeige
        
    Returns:
        True wenn der Download erfolgreich war, False sonst
    """
    console.print(f"Starte Download: [bold cyan]{filename}[/bold cyan]")
    console.print(f"Ziel: {filepath}")
    
    try:
        response = requests.get(download_url, stream=True)
        response.raise_for_status()  # Prüfe HTTP Status
        total_size = int(response.headers.get('content-length', 0))
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("[cyan]Downloading...", total=total_size)
            
            with open(temp_filepath, "wb") as file:
                for data in response.iter_content(chunk_size=1024*1024):  # 1MB Chunks
                    file.write(data)
                    progress.update(task, advance=len(data))
        
        # Download erfolgreich, Datei umbenennen (replace überschreibt atomisch)
        temp_filepath.replace(filepath)
        console.print(f"[green]Download abgeschlossen![/green]")
        return True
        
    except KeyboardInterrupt:
        console.print(f"\n[yellow]Download abgebrochen.[/yellow]")
        # Lösche unvollständige temp Datei
        if temp_filepath.exists():
            temp_filepath.unlink()
        raise  # Re-raise um das Programm zu beenden
    except requests.exceptions.RequestException as e:
        console.print(f"[bold red]Netzwerk-Fehler beim Download:[/bold red] {e}")
        if temp_filepath.exists():
            temp_filepath.unlink()
        return False
    except IOError as e:
        console.print(f"[bold red]Dateisystem-Fehler:[/bold red] {e}")
        if temp_filepath.exists():
            temp_filepath.unlink()
        return False
    except Exception as e:
        console.print(f"[bold red]Download Fehler:[/bold red] {e}")
        if temp_filepath.exists():
            temp_filepath.unlink()
        return False


def download_video(video, plex, download_dir: Path) -> bool:
    """
    Lädt ein Video herunter.
    
    Args:
        video: Das Plex Video-Objekt
        plex: Die Plex Server-Verbindung
        download_dir: Das Zielverzeichnis
        
    Returns:
        True wenn der Download erfolgreich war, False sonst
    """
    # Prüfen, ob Mediendatei vorhanden ist
    if not video.media or not video.media[0].parts:
        console.print(f"[red]Keine Mediendatei gefunden für {video.title}[/red]")
        return False
    
    # Wir nehmen den ersten Teil (Part) der ersten Mediendatei (normalerweise der Hauptfilm)
    part = video.media[0].parts[0]
    
    # Dateiname bereinigen und Pfad bauen
    filename = f"{video.title} ({video.year}).{part.container}"
    filename = sanitize_filename(filename)
    filepath = download_dir / filename
    temp_filepath = download_dir / f"{filename}.temp"
    
    # Prüfen, ob Datei bereits existiert
    if filepath.exists():
        if not Confirm.ask(f"[yellow]Datei existiert bereits: {filename}. Überschreiben?[/yellow]"):
            console.print("[yellow]Download übersprungen.[/yellow]")
            return False
    
    # Download URL generieren (Direct Stream / Original)
    download_url = plex.url(part.key) + f"?download=1&X-Plex-Token={plex._token}"
    
    success = download_file(download_url, filepath, temp_filepath, filename)
    if success:
        console.print(f"[bold green]Download abgeschlossen![/bold green] 🎉")
    return success


def download_episode(episode, show, plex, download_dir: Path, skip_existing_check: bool = False) -> bool:
    """
    Lädt eine einzelne Episode herunter.
    
    Args:
        episode: Das Plex Episode-Objekt
        show: Das Plex Show-Objekt
        plex: Die Plex Server-Verbindung
        download_dir: Das Zielverzeichnis
        skip_existing_check: Ob die Prüfung auf existierende Dateien übersprungen werden soll
        
    Returns:
        True wenn der Download erfolgreich war, False sonst
    """
    # Hole die Mediendatei
    if not episode.media or not episode.media[0].parts:
        console.print(f"[red]Keine Mediendatei gefunden für {episode.title}[/red]")
        return False
    
    part = episode.media[0].parts[0]
    
    # Dateiname: "ShowName - S01E01 - Episode Title.mkv"
    episode_num = f"S{episode.seasonNumber:02d}E{episode.index:02d}"
    filename = f"{show.title} - {episode_num} - {episode.title}.{part.container}"
    filename = sanitize_filename(filename)
    
    filepath = download_dir / filename
    temp_filepath = download_dir / f"{filename}.temp"
    
    # Prüfen, ob Datei bereits existiert (nur wenn nicht schon im Batch-Modus übersprungen)
    if not skip_existing_check and filepath.exists():
        if not Confirm.ask(f"[yellow]Datei existiert bereits: {filename}. Überschreiben?[/yellow]"):
            console.print("[yellow]Download übersprungen.[/yellow]")
            return False
    
    # Download URL generieren
    download_url = plex.url(part.key) + f"?download=1&X-Plex-Token={plex._token}"
    
    return download_file(download_url, filepath, temp_filepath, filename)

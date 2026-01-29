"""Modul für das Verschieben von Dateien mit rclone."""

import subprocess
from pathlib import Path
from typing import Union
from rich.console import Console

console = Console()


def move_to_media_server(source_path: Path, media_server_path: Union[str, Path]) -> bool:
    """
    Verschiebt eine Datei oder ein Verzeichnis zum Medienserver mit rclone.
    
    Args:
        source_path: Pfad zur Quelldatei oder zum Quellverzeichnis
        media_server_path: Pfad zum Medienserver-Zielverzeichnis (kann lokaler Pfad oder rclone remote sein)
        
    Returns:
        True wenn das Verschieben erfolgreich war, False sonst
    """
    if not source_path.exists():
        console.print(f"[red]Quelldatei nicht gefunden: {source_path}[/red]")
        return False
    
    # Prüfe ob es sich um einen rclone remote path handelt (enthält ":")
    is_remote = isinstance(media_server_path, str) and ":" in media_server_path
    
    # Erstelle Zielverzeichnis nur für lokale Pfade
    if not is_remote:
        media_server_path = Path(media_server_path)
        media_server_path.mkdir(parents=True, exist_ok=True)
    
    console.print(f"[cyan]Verschiebe nach Medienserver...[/cyan]")
    console.print(f"Quelle: {source_path}")
    console.print(f"Ziel: {media_server_path}")
    
    try:
        # Nutze rclone move mit --progress für Fortschrittsanzeige
        subprocess.run(
            ["rclone", "move", "--progress", str(source_path), str(media_server_path)],
            check=True,
            capture_output=False,  # Zeige Fortschritt in Echtzeit
            text=True
        )
        
        console.print(f"[green]Erfolgreich zum Medienserver verschoben![/green]")
        return True
        
    except FileNotFoundError:
        console.print("[yellow]rclone nicht gefunden. Verwende normales Verschieben...[/yellow]")
        # Fallback: Nutze Python's shutil für lokale Verschiebung
        if is_remote:
            console.print("[red]Kann nicht zu Remote-Ziel verschieben ohne rclone.[/red]")
            return False
            
        import shutil
        try:
            media_server_path = Path(media_server_path)
            if source_path.is_file():
                # Verschiebe Datei
                dest_file = media_server_path / source_path.name
                shutil.move(str(source_path), str(dest_file))
            else:
                # Verschiebe Verzeichnis
                dest_dir = media_server_path / source_path.name
                shutil.move(str(source_path), str(dest_dir))
            
            console.print(f"[green]Erfolgreich zum Medienserver verschoben![/green]")
            return True
        except Exception as e:
            console.print(f"[red]Fehler beim Verschieben: {e}[/red]")
            return False
            
    except subprocess.CalledProcessError as e:
        console.print(f"[red]rclone Fehler beim Verschieben: {e}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Unerwarteter Fehler beim Verschieben: {e}[/red]")
        return False

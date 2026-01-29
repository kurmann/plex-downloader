"""Cleanup-Modul für temporäre Dateien."""

from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm

console = Console()


def cleanup_temp_files(download_path: str) -> None:
    """
    Prüft auf alte .temp Dateien und bietet deren Löschung an.
    
    Args:
        download_path: Der Pfad zum Download-Verzeichnis
    """
    if not download_path:
        return  # Keine Konfiguration vorhanden
    
    download_dir = Path(download_path)
    if not download_dir.exists():
        return
    
    # Suche nach .temp Dateien (rekursiv)
    temp_files = list(download_dir.rglob("*.temp"))
    
    if not temp_files:
        return  # Keine temp Dateien gefunden
    
    console.print(f"\n[yellow]Es wurden {len(temp_files)} alte .temp Datei(en) gefunden:[/yellow]")
    for temp_file in temp_files:
        file_size = temp_file.stat().st_size / (1024 * 1024)  # In MB
        console.print(f"  - {temp_file.name} ({file_size:.2f} MB)")
    
    if Confirm.ask("\n[yellow]Möchtest du diese Dateien löschen?[/yellow]", default=True):
        deleted_count = 0
        failed_count = 0
        for temp_file in temp_files:
            try:
                temp_file.unlink()
                console.print(f"[green]Gelöscht: {temp_file.name}[/green]")
                deleted_count += 1
            except Exception as e:
                console.print(f"[red]Fehler beim Löschen von {temp_file.name}: {e}[/red]")
                failed_count += 1
        
        if failed_count == 0:
            console.print(f"[bold green]Alle .temp Dateien wurden gelöscht.[/bold green]")
        else:
            console.print(f"[bold yellow]{deleted_count} Datei(en) gelöscht, {failed_count} Fehler.[/bold yellow]")
    else:
        console.print("[yellow]Übersprungen. Die .temp Dateien bleiben erhalten.[/yellow]")

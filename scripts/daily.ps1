# Rutina diaria de ChessCoach: baja partidas, las analiza y publica si hay repo remoto.
# Se ejecuta desde la tarea programada "ChessCoach - Rutina diaria".

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root '.venv\Scripts\python.exe'
$log = Join-Path $root 'data\daily.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

function Write-Log($message) {
    "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message | Tee-Object -FilePath $log -Append
}

Write-Log '--- inicio ---'
try {
    & $python -m chesscoach.cli sync      2>&1 | Tee-Object -FilePath $log -Append
    & $python -m chesscoach.cli analyze --limit 25 2>&1 | Tee-Object -FilePath $log -Append
    # Las explicaciones se calculan aqui porque la nube no tiene Stockfish.
    & $python -m chesscoach.cli explain   2>&1 | Tee-Object -FilePath $log -Append
    & $python -m chesscoach.cli puzzles   2>&1 | Tee-Object -FilePath $log -Append

    # Publicar solo si ya se configuro el repo remoto para el panel en la nube.
    if ((Test-Path (Join-Path $root '.git')) -and (git remote 2>$null)) {
        git add data/games.db data/mis-blunders.pgn
        if (git diff --cached --quiet) {
            Write-Log 'sin cambios que publicar'
        } else {
            git commit -m "datos: $(Get-Date -Format 'yyyy-MM-dd')" | Out-Null
            git push 2>&1 | Tee-Object -FilePath $log -Append
            Write-Log 'datos publicados'
        }
    }
    Write-Log '--- fin OK ---'
} catch {
    Write-Log "ERROR: $_"
    exit 1
}

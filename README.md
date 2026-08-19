# ♟️ ChessCoach — Panel de Progreso

Mide automáticamente si el entrenamiento de ajedrez está funcionando. Descarga las
partidas de **Lichess** y **chess.com**, las analiza con **Stockfish**, y calcula
las cinco métricas del plan de entrenamiento.

No enseña ajedrez. Sirve para saber **dónde apuntar el estudio** y **ver si hay progreso**.

---

## Uso diario

```powershell
cd $HOME\Documents\ChessCoach

# Todo de una vez: descarga, analiza, reporta y exporta puzzles
.\.venv\Scripts\python.exe -m chesscoach.cli all

# Panel visual en el navegador
.\.venv\Scripts\streamlit.exe run app.py
```

### Comandos sueltos

| Comando | Qué hace |
|---|---|
| `chesscoach sync` | Descarga partidas nuevas de ambas plataformas |
| `chesscoach analyze` | Analiza con Stockfish las que faltan (incremental) |
| `chesscoach report` | Tarjeta de progreso en la terminal |
| `chesscoach puzzles` | Exporta `data/mis-blunders.pgn` |

`analyze` descarga Stockfish automáticamente la primera vez (a `data/engine/`).

---

## Las cinco métricas

| Métrica | Qué mide | Meta |
|---|---|---|
| **Errores graves por partida** | Blunders + mistakes por caída de probabilidad de victoria | < 0.5 |
| **Tiempo sobrante** | Segundos en el reloj al terminar. Alto = jugó demasiado rápido | < 3:00 |
| **Segundos por jugada** | Promedio real de tiempo pensado | > 20 s |
| **Partidas fuera del repertorio** | % de partidas donde se desvió de `repertoire.pgn` | 0 |
| **Ventajas convertidas** | % de partidas ganadas tras alcanzar +3 | > 90% |

Los errores se clasifican por **caída de probabilidad de victoria**, no por centipeones
brutos. Así una oscilación en una posición ya perdida no cuenta como error nuevo.

---

## Detectores específicos

- **Fuga de repertorio** — compara cada apertura contra `repertoire.pgn` y reporta la
  jugada exacta donde se salió, qué jugó y qué debía jugar. Solo cuenta si fue él
  quien se desvió primero.
- **Pieza atrapada** 🐴 — marca las jugadas donde una pieza entra en territorio
  enemigo, queda atacada y sin casillas de retirada seguras.
- **Puzzles propios** — exporta las posiciones justo antes de cada error a un PGN
  importable en un Lichess Study.

---

## Configuración

Todo se ajusta en `config.yaml`: cuentas, controles de tiempo a incluir, metas y
umbrales del motor. El repertorio vive en `repertoire.pgn` (formato PGN normal,
un capítulo por línea). Al cambiar el repertorio hay que reanalizar:

```powershell
Remove-Item data\games.db
.\.venv\Scripts\python.exe -m chesscoach.cli all
```

---

## Estructura

```
ChessCoach/
├─ config.yaml          # cuentas, metas, umbrales
├─ repertoire.pgn       # el repertorio a vigilar
├─ app.py               # panel Streamlit
├─ data/                # base SQLite, motor, puzzles (generado)
└─ src/chesscoach/
   ├─ fetch.py          # APIs de Lichess y chess.com
   ├─ engine.py         # localiza/descarga Stockfish
   ├─ analyze.py        # análisis jugada a jugada
   ├─ repertoire.py     # detector de desviaciones
   ├─ metrics.py        # cálculo de métricas y tendencias
   ├─ puzzles.py        # exportador de errores propios
   └─ store.py          # SQLite
```

Los datos son locales. No se sube nada a ningún lado.

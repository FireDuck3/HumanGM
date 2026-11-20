# HumanGM Chess Analysis

HumanGM gives a written recommendation for a chess position. Set up the board by making moves manually or import FEN or PGN. Choose a target rating for Maia-3 and press **Проаналізувати**.

Stockfish searches up to six legal moves at full strength. Maia-3 evaluates the likelihood of all legal moves for its rating input. HumanGM recommends the highest Maia probability among moves within the Stockfish evaluation limit. The margin is 20 centipawns at the default target of 2800. Forced mates or a missing Maia policy use Stockfish's top move. A rating input describes the model's target, and an actual playing Elo would require match calibration.

## Windows

This local installation already includes the engines. Double-click `scripts\run.cmd`, then open <http://127.0.0.1:8006>. A separate fresh source checkout needs Python, Node.js, the vendored Maia runtime, and a compatible Stockfish binary before the analysis API can run. Refer to `.env.example` for their paths.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\scripts\setup-engines.cmd
Push-Location frontend
npm.cmd ci
npm.cmd run build
Pop-Location
.\scripts\run.cmd
```

If there is no Windows Stockfish executable at the configured path, download the [official release](https://github.com/official-stockfish/Stockfish/releases) and update `STOCKFISH_PATH` in `.env`.

## Render

Use the included Dockerfile and `render.yaml` to create a Docker Web Service from a Git repository. The configuration uses Render Free in Frankfurt and checks `/healthz`. The image builds the frontend, downloads pinned Linux Stockfish 19 and Maia-3 5M files with SHA-256 verification, and runs FastAPI on Render's assigned port. It requires no app secret, database, or runtime model download.

The free service can sleep when idle. CPU inference latency and memory use on the Render instance should be verified after deployment. [Render Free limitations](https://render.com/docs/free)

The analysis API accepts `POST /api/analyze` with `initial_fen` (optional), `moves` (UCI strings), and `target_rating` (1200–3000). It returns the same position, a recommended move, and the Stockfish/Maia candidate table. Each request carries its own position.

## Engine source

- [Stockfish 19 source and release](https://github.com/official-stockfish/Stockfish/releases/tag/sf_19). The container includes its license.
- [Maia-3 source](https://github.com/CSSLab/maia3/tree/1e13597c42d4858b7cfd7cfdae01e297263364b2). The website's **Код Maia-3** link downloads its vendored source, license, and the exact wrapper scripts.

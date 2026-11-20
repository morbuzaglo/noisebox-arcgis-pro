# MATLAB engine options (for your decision)

Starting MATLAB costs about 7 s on the development computer and 10 to 80 s on slower ones, on every run, because the
original design started a new MATLAB for each run. Three ways to avoid it were looked at. Nothing about the physics changes:
all acoustics stay in `matlab/core/*.m`, Python never imports `matlab.engine`.

| Option | Status | What it does | Cost / risk |
|---|---|---|---|
| **fresh** | implemented, selectable | A new MATLAB for every run (the original behaviour). | Slowest start; nothing stays in memory; simplest. |
| **warm** (default now) | implemented and tested | One MATLAB process is started on the first run (`worker/nb_server.py`, localhost only, random token) and serves later runs. Before every job the md5 of every `.m` file in `matlab/core` and `worker/matlab_glue` is compared with the last job; if one changed, MATLAB's function cache is cleared, so an edited `.m` file takes effect on the next run, exactly as before. It quits after 30 idle minutes, on `engine stop`, or from the pane (Outputs > MATLAB engine > Stop engine). | About 0.5 GB of memory while it is ready. After a crash the next run starts a new one. |
| **compiled** (not built) | rejected on this computer | MATLAB Compiler would turn the core into a Python package or an executable. | The licence here has MATLAB Compiler but **not MATLAB Compiler SDK** (`license('test','Compiler_SDK') = 0`), which a Python package needs. A standalone executable would still need the MATLAB Runtime installed on every computer and must be rebuilt after every `.m` edit, and it would still pay a runtime start-up on every call. The warm engine gives the same saving without that. |

## How to choose
Edit `config.json` in the NoiseBox folder (create it if missing), or set the environment variable `NOISEBOX_ENGINE`:

```json
{ "engine": "warm", "engine_idle_minutes": 30 }
```
Use `"engine": "fresh"` to go back to one MATLAB per run. `propy noisebox_cli.py engine status | start | stop` shows or controls it.

## What was checked (`tests/test_engine.py`)
* warm and fresh give identical rasters (maximum difference 0.0 dB);
* the second warm run took 4.5 s against 12.2 s for a fresh run on the 60-cell test (MATLAB start-up 7 s is the difference);
* an edited `nb_adiv.m` (+3 dB) shows as exactly -3.000 dB on the next run **without restarting the engine**, and the original code is back on the run after;
* stop and restart give the same result again.

A detail found while testing: launching the engine with Windows' `DETACHED_PROCESS` flag made MATLAB's start-up take 19 minutes; the hidden-window launch used now takes 6 s.

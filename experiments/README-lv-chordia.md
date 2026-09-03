# lv-chordia experiment

This is an isolated experiment. It does not change `backend/`, the frontend,
the default engine, `pyproject.toml`, or `uv.lock`.

Create the environment and install the package:

```bash
uv venv .venv-lv --python 3.12
uv pip install --python .venv-lv/bin/python lv-chordia
```

Run one device:

```bash
./.venv-lv/bin/python experiments/lv_chordia_adapter.py sample.wav --device cpu
./.venv-lv/bin/python experiments/lv_chordia_adapter.py sample.wav --device mps
```

Run the comparison and write JSON plus Markdown under
`experiments/results/<audio-name>/`:

```bash
python experiments/compare_engines.py sample.wav --include-current
```

`lv-chordia 1.1.0` exposes no `device` argument and its network wrapper calls
`.cuda()` directly. The adapter uses a subprocess-local MPS bridge, so this
experiment does not patch the installed package or connect it to the app.

The checked-in `experiments/results/sample/summary.md` is the first-round
result. It records CPU/MPS timing, peak RSS, raw and converted chords, and the
compatibility conclusion. The current sample is not evidence for changing the
default engine.

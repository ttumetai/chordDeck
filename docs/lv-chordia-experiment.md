# lv-chordia 实验分支实施方案

> 目标：在不污染现有 Chord Deck 运行环境、不替换当前默认引擎的前提下，实验性接入 `lv-chordia`，验证其在 Apple Silicon 上的 CPU/MPS 可用性、运行速度和识别效果。

## 1. 当前项目状态

项目路径：

```text
/Users/ttumetai/pythonCodes/chordDeck
```

当前主分支：

```text
main
```

远端仓库：

```text
https://github.com/ttumetai/chordDeck.git
```

当前识别链路：

```text
auto
  ├── DeepChroma
  ├── Chordino
  └── librosa chroma template
```

当前主环境：

- Python 3.12
- NumPy `<2`
- librosa `>=0.10,<1`
- `madmom-infer`
- `chord-extractor`
- FastAPI
- Vue 3

需要注意：本地 `~/vamp-plugins/nnls-chroma.dylib` 是 x86_64 架构，而当前机器是 Apple Silicon ARM，因此 Chordino 实际加载失败后会回退到 librosa 模板匹配。

## 2. 为什么使用独立环境

不要将 `lv-chordia` 直接安装进当前 `.venv`。

依赖存在明显冲突：

| 依赖 | Chord Deck 当前要求 | lv-chordia 最新源码要求 |
| --- | --- | --- |
| Python | `>=3.9`，当前使用 3.12 | `>=3.10` |
| NumPy | `>=1.24,<2` | `>=2.2.6` |
| librosa | `>=0.10,<1` | `>=0.11` |
| PyTorch | 未安装 | `>=2.13` |

实验采用独立环境：

```text
.venv-lv/
```

主应用通过子进程调用它，避免改变现有 `pyproject.toml` 和 `uv.lock`。

## 3. 分支策略

先确认工作区状态：

```bash
cd /Users/ttumetai/pythonCodes/chordDeck
git status
```

当前工作区可能还有编辑工作台播放功能的未提交修改。不要丢弃这些修改。

创建实验分支：

```bash
git switch -c experiment/lv-chordia
```

如果需要先把编辑播放功能单独提交：

```bash
git add frontend/src/components/EditWorkspace.vue
git commit -m "Add DAW-style playback controls to chord editor"
git switch -c experiment/lv-chordia
```

实验阶段不要合并回 `main`，等效果验证完成后再决定。

## 4. 实验目标

需要验证以下问题：

1. `lv-chordia` 能否在 Apple Silicon ARM 上正常安装。
2. CPU 推理是否稳定。
3. MPS 推理是否支持全部模型算子。
4. 第一次加载五模型 ensemble 需要多长时间。
5. 单曲识别需要多长时间。
6. 是否比当前 DeepChroma/librosa 结果更准确。
7. 扩展和弦、七和弦、转位低音是否明显改善。
8. 输出标签是否能映射到 Chord Deck 当前格式。
9. 长音频的内存占用是否可接受。
10. 是否值得成为正式引擎。

## 5. 安装独立环境

创建环境：

```bash
uv venv .venv-lv --python 3.12
```

安装 `lv-chordia`：

```bash
uv pip install --python .venv-lv/bin/python lv-chordia
```

验证包和架构：

```bash
./.venv-lv/bin/python - <<'PY'
import platform
import torch
import lv_chordia

print("machine:", platform.machine())
print("torch:", torch.__version__)
print("cuda:", torch.cuda.is_available())
print("mps built:", torch.backends.mps.is_built())
print("mps available:", torch.backends.mps.is_available())
print("lv_chordia:", lv_chordia.__file__)
PY
```

期望：

```text
machine: arm64
cuda: False
mps built: True
mps available: True
```

如果 `mps available` 为 `False`，仍然可以继续 CPU 实验。

## 6. 最小推理验证

### 6.1 CPU

先使用项目中的合成音频：

```bash
time ./.venv-lv/bin/python - <<'PY'
from lv_chordia.chord_recognition import chord_recognition

result = chord_recognition(
    "sample.wav",
    chord_dict_name="submission",
    device="cpu",
)

for chord in result:
    print(chord)
PY
```

`sample.wav` 的已知进行是：

```text
C → F → G → Am
```

每个和弦约持续 3 秒。

重点观察：

- 是否正确识别四个和弦。
- 边界是否接近 `0 / 3 / 6 / 9` 秒。
- 是否产生大量短片段。
- 模型加载耗时。
- 总推理耗时。

### 6.2 MPS

CPU 成功后再测试：

```bash
time ./.venv-lv/bin/python - <<'PY'
from lv_chordia.chord_recognition import chord_recognition

result = chord_recognition(
    "sample.wav",
    chord_dict_name="submission",
    device="mps",
)

for chord in result:
    print(chord)
PY
```

如果出现 MPS 算子不支持、设备不一致或 tensor 迁移错误，不要立即修改模型代码。

记录错误，并继续使用 CPU 作为可靠基线。

可以临时测试 PyTorch 的 CPU 回退：

```bash
PYTORCH_ENABLE_MPS_FALLBACK=1 \
./.venv-lv/bin/python your_script.py
```

但正式使用前需要评估这种回退是否导致性能反而更差。

## 7. 建议新增文件

实验分支尽量只增加以下文件：

```text
experiments/
├── lv_chordia_adapter.py
├── compare_engines.py
└── README-lv-chordia.md
```

不要在第一阶段修改：

```text
backend/chords.py
backend/main.py
frontend/
pyproject.toml
uv.lock
```

先证明效果，再正式接入。

## 8. 适配器设计

建议文件：

```text
experiments/lv_chordia_adapter.py
```

职责：

1. 接收音频路径。
2. 接收 `cpu` 或 `mps`。
3. 调用 `lv-chordia`。
4. 将 Harte/MIREX 标签转换为 Chord Deck 格式。
5. 输出统一 JSON。
6. 在 stdout 只输出 JSON，日志写 stderr。
7. 异常时返回非零状态码。

建议命令：

```bash
./.venv-lv/bin/python experiments/lv_chordia_adapter.py \
  sample.wav \
  --device cpu \
  --vocabulary submission
```

建议输出：

```json
{
  "source": "lv-chordia",
  "device": "cpu",
  "vocabulary": "submission",
  "load_seconds": 2.41,
  "inference_seconds": 4.82,
  "chords": [
    {
      "timestamp": 0.0,
      "end": 3.02,
      "chord": "C"
    },
    {
      "timestamp": 3.02,
      "end": 6.01,
      "chord": "F"
    }
  ]
}
```

## 9. 标签转换

`lv-chordia` 通常输出 Harte/MIREX 风格：

```text
C:maj
A:min
G:7
F:maj7
B:min7
D:maj/F#
N
```

Chord Deck 当前格式倾向于：

```text
C
Am
G7
Fmaj7
Bm7
D/F#
N
```

至少需要处理：

```text
:maj   → ""
:min   → "m"
:maj7  → "maj7"
:min7  → "m7"
:7     → "7"
:dim   → "dim"
:dim7  → "dim7"
:aug   → "aug"
:sus2  → "sus2"
:sus4  → "sus4"
```

根音应统一为项目现有命名习惯：

```text
C# → Db
D# → Eb
G# → Ab
A# → Bb
```

但建议继续保留：

```text
F#
```

Slash chord 要保留低音：

```text
D:maj/F# → D/F#
A:min7/G → Am7/G
```

不要对 `lv-chordia` 原始结果立即调用现有 `simplify_chord()`，否则会丢失此次实验最有价值的复杂和弦信息。

同时保存：

- 原始标签
- 完整转换标签
- 简化标签

## 10. 模型复用

`lv-chordia` 默认的一次性调用会为每首歌重新加载五个模型，开销较大。

批量实验应使用官方的 session API：

```python
from lv_chordia import LVChordiaSession

with LVChordiaSession(
    chord_dict_name="submission",
    device="cpu",
) as session:
    result1 = session.recognize("song1.mp3")
    result2 = session.recognize("song2.mp3")
```

具体方法名以安装版本的实际 API 为准，可用以下命令确认：

```bash
./.venv-lv/bin/python - <<'PY'
from lv_chordia import LVChordiaSession
print(dir(LVChordiaSession))
PY
```

如果正式接入，应考虑常驻 sidecar 进程，让模型只加载一次。

## 11. 对比脚本

建议文件：

```text
experiments/compare_engines.py
```

对同一首音频分别运行：

- DeepChroma
- Chordino（如果插件架构可用）
- librosa 模板匹配
- lv-chordia CPU
- lv-chordia MPS

输出：

```text
experiments/results/<audio-name>/
├── deepchroma.json
├── chordino.json
├── librosa-template.json
├── lv-chordia-cpu.json
├── lv-chordia-mps.json
└── summary.md
```

对比字段：

```json
{
  "engine": "lv-chordia",
  "device": "cpu",
  "duration": 180.2,
  "load_seconds": 2.8,
  "inference_seconds": 18.4,
  "realtime_factor": 0.102,
  "peak_memory_mb": 1240,
  "chord_count": 96,
  "unique_chords": 18
}
```

实时系数：

```text
realtime_factor = 推理耗时 / 音频时长
```

值越低越快：

```text
0.1 = 3 分钟歌曲约 18 秒完成
1.0 = 与音频时长相同
```

## 12. 测试素材

### 12.1 合成样本

现有：

```text
sample.wav
```

预期：

```text
0s  C
3s  F
6s  G
9s  Am
```

### 12.2 真实歌曲

至少选择 10～20 首：

- 简单流行三和弦
- 包含 maj7/m7/7 的歌曲
- 包含 slash chord 的歌曲
- 爵士或复杂和声
- 纯器乐
- 密集编曲
- 低音不清晰
- 有明显静音/前奏
- 转调歌曲
- 节奏不稳定的歌曲

不要使用主观印象作为唯一标准。应手工制作部分 `.lab` 标注作为基准。

## 13. 评估指标

推荐用 `mir_eval.chord`。

需要记录：

| 指标 | 说明 |
| --- | --- |
| Root | 根音准确率 |
| Maj/min | 大小三和弦准确率 |
| Thirds | 三度性质准确率 |
| Triads | 三和弦准确率 |
| Sevenths | 七和弦准确率 |
| MIREX | MIREX 和弦匹配指标 |
| Boundary error | 和弦边界误差 |
| Segment count | 输出片段数 |
| Short segment ratio | 短片段比例 |
| Runtime | 推理耗时 |
| Peak memory | 峰值内存 |

如果没有完整标注，至少进行盲听人工打分：

```text
根音：0～5
和弦性质：0～5
复杂和弦：0～5
边界：0～5
稳定性：0～5
```

评测时隐藏引擎名，避免主观偏见。

## 14. 词汇选择实验

`lv-chordia` 提供三种词汇：

| 词汇 | 规模 | 建议用途 |
| --- | ---: | --- |
| `ismir2017` | 约 25 类 | 与 DeepChroma 公平比较 |
| `submission` | 约 170 类 | 推荐默认实验 |
| `full` | 约 600+ 类 | 爵士和复杂和声 |

建议顺序：

1. `ismir2017`
2. `submission`
3. `full`

不要直接把 `full` 当默认结果。词汇越大不一定越准确，可能出现：

- 罕见和弦误报
- 片段抖动
- 用户难以理解的符号
- 导出结果过于复杂

## 15. CPU/MPS 判断标准

### CPU 可接受

满足以下条件即可：

- 不崩溃。
- 3 分钟歌曲在 60 秒内完成。
- 峰值内存在本机可接受范围内。
- 模型可以在进程内复用。
- 准确率明显高于当前模板匹配。

### MPS 可接受

满足：

- 全流程不发生 device mismatch。
- 无关键算子回退错误。
- 输出与 CPU 基本一致。
- 比 CPU 至少快 20%。
- 内存增长可控。

如果 MPS 只快少量或错误较多，正式版本优先 CPU。

## 16. 正式接入方案

只有实验结果通过后才修改主应用。

推荐正式架构：

```text
FastAPI 主应用
      │
      ├── DeepChroma / Chordino / librosa
      │
      └── lv-chordia sidecar
              └── 独立 Python + NumPy 2 + PyTorch 环境
```

主应用通过以下方式调用 sidecar：

```text
stdin JSON → sidecar → stdout JSON
```

或：

```text
localhost HTTP
```

第一版优先使用长驻子进程或本地 HTTP sidecar，因为模型需要复用。

不要为每个请求启动一次 Python 进程并重新加载五模型 ensemble，否则长音频后台任务的体验会很差。

## 17. 缓存策略

如果正式接入，现有数据库缓存键：

```text
md5 + engine
```

建议扩展成：

```text
md5 + engine + engine_version + vocabulary
```

例如：

```text
4a9ed... + lv-chordia + 1.1.0 + submission
```

否则更换模型版本或词汇后可能误用旧缓存。

建议 `source`：

```text
lv-chordia
```

建议 `engine`：

```text
lv-chordia-submission
lv-chordia-ismir2017
lv-chordia-full
```

## 18. 环境检查扩展

正式接入后，`scripts/check_env.py` 只检查 sidecar 是否可调用，不要在主环境中导入 `torch`：

```bash
.venv-lv/bin/python -c "import torch, lv_chordia; print('ok')"
```

检查项目：

- `.venv-lv/bin/python` 是否存在。
- `lv_chordia` 是否能导入。
- `torch` 是否为 arm64。
- CPU 是否可用。
- MPS 是否可用。
- 模型权重是否完整。

`.gitignore` 增加：

```gitignore
.venv-lv/
experiments/results/
```

## 19. 风险

### 依赖冲突

风险最高。

处理方式：

```text
独立环境，不直接改主项目依赖
```

### 内存占用

五模型 ensemble 可能比现有引擎重。

需要实际记录：

- 加载前内存
- 加载后内存
- 单曲结束后内存
- 连续多曲后的内存

### MPS 兼容性

部分模型代码可能对 CUDA/CPU 路径做了特殊假设。MPS 支持虽然存在，但必须实际验证。

### 结果过于复杂

170 或 600 类词汇可能降低用户体验。

应保留：

```text
完整 / 简化
```

并考虑再加一个：

```text
基础 / 常用 / 完整
```

### 长音频

需要测试：

- 5 分钟
- 15 分钟
- 30 分钟

避免整首 CQT 和全部中间张量同时常驻内存。

## 20. 实验成功标准

只有同时满足以下条件才建议合并：

1. Apple Silicon CPU 稳定完成推理。
2. `sample.wav` 正确识别主要和弦。
3. 至少 10 首真实歌曲盲测优于当前默认方案。
4. 七和弦/转位识别有明显提升。
5. 3 分钟歌曲 CPU 推理不超过约 60 秒。
6. 内存占用可接受。
7. 输出标签能无损映射。
8. 不修改或污染主环境。
9. 失败时能自动回退到现有引擎。
10. 模型能在后台进程中复用。

## 21. 不应做的事情

实验第一阶段不要：

- 将 `lv-chordia` 直接加入主 `pyproject.toml`。
- 修改现有 `uv.lock`。
- 替换 `auto` 默认引擎。
- 删除 DeepChroma 或 librosa 回退。
- 把 `.venv-lv` 提交到 Git。
- 把用户音乐或测试音频提交到公开仓库。
- 只凭 `sample.wav` 判断模型优劣。
- 只比较输出是否“更复杂”。
- 未评测就将 `full` 词汇作为默认。

## 22. 下一会话执行清单

将以下内容直接交给新的 Codex 会话：

```text
请阅读 docs/lv-chordia-experiment.md 并继续执行。

要求：
1. 保留当前工作区所有改动。
2. 创建 experiment/lv-chordia 分支。
3. lv-chordia 必须安装在独立 .venv-lv 中，不修改主 pyproject.toml 和 uv.lock。
4. 先验证 Apple Silicon CPU，再测试 MPS。
5. 使用 sample.wav 进行第一轮验证。
6. 新增最小适配器和引擎对比脚本。
7. 不把 lv-chordia 接入正式 API，不改变默认引擎。
8. 输出 CPU/MPS 耗时、识别结果、内存和兼容性结论。
9. 未经确认不要合并回 main 或推送。
```

建议保存路径：

```text
docs/lv-chordia-experiment.md
```

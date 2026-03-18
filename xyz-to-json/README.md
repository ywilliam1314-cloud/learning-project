# XYZ to JSON Converter

版本: v1.1  
创作者: MingGui Yi

## 中文说明

### 项目简介

本项目用于将 GPUMD / EXTXYZ 风格的 `.xyz` 训练集文件转换为 JSON 文档。

项目同时提供一个基于 Flask 的本地网页前端，支持：

- 拖入单个 `.xyz` 文件并实时预览转换结果
- 拖入整个文件夹，递归寻找其中的 `.xyz` 文件
- 自动将转换后的 `.json` 写回到对应 `.xyz` 所在的原文件夹
- 右侧预览转换结果或批量转换摘要
- 切换 `light` / `dark` 两种页面模式

### 版本 v1.1 更新内容

- 新增文件夹拖入功能
- 新增文件夹递归扫描 `.xyz` 文件功能
- 新增批量转换接口 `/api/convert-batch`
- 新增将转换结果写回原文件夹的前端保存流程
- 命令行模式新增目录输入支持，可直接对整个目录递归生成同目录 `.json`

### 项目文件

- `xyz_to_json.py`
  后端转换脚本，同时提供 Flask 服务
- `index.html`
  前端页面，支持单文件转换和文件夹批量转换
- `start_xyz_json_app.bat`
  Windows 一键启动脚本
- `requirements.txt`
  Python 依赖列表

### 环境要求

- Python 3.x
- Flask 3.x
- 推荐浏览器：Chrome / Edge 最新版

安装依赖：

```bash
pip install -r requirements.txt
```

### 启动方式

Windows 下可直接运行：

```bat
start_xyz_json_app.bat
```

或者手动启动后端：

```bash
python xyz_to_json.py --serve --port 2100
```

然后在浏览器中打开：

```text
http://127.0.0.1:2100
```

### Docker 使用

构建镜像：

```bash
docker build -t xyz-to-json:v1.1 .
```

启动 Web 服务：

```bash
docker run --rm -p 2100:2100 xyz-to-json:v1.1
```

然后在浏览器中打开：

```text
http://127.0.0.1:2100
```

也可以通过 Docker Compose 启动：

```bash
docker compose up --build
```

如果要转换宿主机上的单个 `.xyz` 文件，可挂载目录后执行：

```bash
docker run --rm -v /path/to/data:/data xyz-to-json:v1.1 /data/input.xyz -o /data/output.json
```

如果要递归转换整个目录中的 `.xyz` 文件，并把 `.json` 写回原目录：

```bash
docker run --rm -v /path/to/data:/data xyz-to-json:v1.1 /data
```

### 命令行使用

转换单个 `.xyz` 文件：

```bash
python xyz_to_json.py input.xyz -o output.json
```

递归转换整个目录中的 `.xyz` 文件，并将 `.json` 写回到各自原目录：

```bash
python xyz_to_json.py path/to/folder
```

### 前端使用说明

#### 单文件模式

1. 拖入一个 `.xyz` 文件，或点击“选择 .xyz 文件”
2. 左栏显示原始 `.xyz` 内容
3. 右栏显示转换后的 JSON
4. 点击右上角按钮可下载当前 JSON

#### 文件夹模式

1. 拖入一个文件夹，或点击“选择文件夹”
2. 前端会递归寻找其中所有 `.xyz` 文件
3. 后端批量完成转换
4. 前端会把每个 `.json` 自动写回到对应 `.xyz` 所在目录
5. 右栏显示批量转换摘要

### 文件夹写回说明

文件夹模式下“写回原目录”依赖浏览器的 File System Access 能力。

推荐条件：

- 使用 `http://127.0.0.1:2100` 打开页面
- 使用 Chrome 或 Edge 最新版
- 当浏览器请求目录读写权限时选择允许

如果浏览器不支持该能力，前端仍可完成批量转换摘要预览，但可能无法自动把 `.json` 写回原文件夹。

### `.xyz` 分帧规则

每一帧固定由 `N + 2` 行组成，其中 `N` 为当前结构的原子数：

1. 第 `i` 行读取为原子数 `N`
2. 第 `i+1` 行读取为 metadata
3. 第 `i+2` 到第 `i+N+1` 行读取为原子信息
4. 当前帧结束后，下一帧从 `i + N + 2` 开始
5. 持续处理到文件结束

### Metadata 解析规则

每一帧第二行 metadata 会解析成结构化键值对，支持：

- `key=value`
- `key = value`
- 带双引号的值
- 大小写不敏感键名

特殊字段会做类型化处理：

- `Lattice` -> `3x3` 数值矩阵
- `virial` -> `3x3` 数值矩阵
- `pbc` -> 布尔数组
- `Properties` -> 支持字段定义串

`config_tye` 与 `config_type` 会统一归一化为 `config_type`。

### 支持读取的原子属性

程序当前只读取以下 `Properties` 字段：

- `species:S:1`
- `pos:R:3`
- `force:R:3`
- `forces:R:3`
- `bec:R:9`

每个 atom 都会额外生成一个从 `1` 开始的 `atom_index`。

输出时，原子字段顺序遵循 `Properties` 在 `.xyz` 中从左到右的顺序。

### JSON 输出结构

输出 JSON 根结构为“帧对象数组”。

每一帧字段顺序为：

1. `frame_index`
2. `atom_count`
3. 按原始 `.xyz` metadata 行顺序展开的 metadata 字段
4. `atoms`

每个 atom 字段顺序为：

1. `atom_index`
2. 按 `Properties` 从左到右出现顺序展开的原子字段

### 单位说明

- 长度和位置：`Angstrom`
- 能量：`eV`
- 力：`eV/Angstrom`
- virial：`eV`
- BEC：元电荷 `e`

### 说明

- 修改 `xyz_to_json.py` 后，需要重启 Flask 后端，前端才会看到新的逻辑
- 前端显示的 JSON 顺序完全以后端返回结果为准

## English

Version: v1.1  
Author: MingGui Yi

### Overview

This project converts GPUMD / EXTXYZ style `.xyz` training-set files into JSON documents.

It also provides a local Flask-based web UI with:

- drag-and-drop conversion for a single `.xyz` file
- drag-and-drop folder processing with recursive `.xyz` discovery
- automatic write-back of `.json` files next to the corresponding `.xyz` files
- JSON preview or batch summary preview on the right panel
- `light` / `dark` theme switching

### What Is New in v1.1

- Added folder drag-and-drop support
- Added recursive discovery of `.xyz` files inside folders
- Added batch conversion endpoint `/api/convert-batch`
- Added frontend write-back flow that saves `.json` beside the source `.xyz`
- Added command-line directory conversion support for recursive in-place output

### Project Files

- `xyz_to_json.py`
  Backend converter and Flask server
- `index.html`
  Frontend page for single-file and folder-based conversion
- `start_xyz_json_app.bat`
  One-click launcher for Windows
- `requirements.txt`
  Python dependency list

### Requirements

- Python 3.x
- Flask 3.x
- Recommended browser: latest Chrome or Edge

Install dependencies:

```bash
pip install -r requirements.txt
```

### Start the App

On Windows:

```bat
start_xyz_json_app.bat
```

Or start the backend manually:

```bash
python xyz_to_json.py --serve --port 2100
```

Then open:

```text
http://127.0.0.1:2100
```

### Docker Usage

Build the image:

```bash
docker build -t xyz-to-json:v1.1 .
```

Start the web service:

```bash
docker run --rm -p 2100:2100 xyz-to-json:v1.1
```

Then open:

```text
http://127.0.0.1:2100
```

You can also start it with Docker Compose:

```bash
docker compose up --build
```

To convert a single `.xyz` file from the host, mount the data directory and run:

```bash
docker run --rm -v /path/to/data:/data xyz-to-json:v1.1 /data/input.xyz -o /data/output.json
```

To recursively convert all `.xyz` files in a directory and write sibling `.json` files:

```bash
docker run --rm -v /path/to/data:/data xyz-to-json:v1.1 /data
```

### Command-Line Usage

Convert a single `.xyz` file:

```bash
python xyz_to_json.py input.xyz -o output.json
```

Recursively convert all `.xyz` files inside a directory and write sibling `.json` files:

```bash
python xyz_to_json.py path/to/folder
```

### Frontend Usage

#### Single-file mode

1. Drag in one `.xyz` file, or click "选择 .xyz 文件"
2. The left panel shows the original `.xyz` content
3. The right panel shows the converted JSON
4. Use the top-right button to download the current JSON

#### Folder mode

1. Drag in a folder, or click "选择文件夹"
2. The frontend recursively finds all `.xyz` files inside it
3. The backend performs batch conversion
4. The frontend writes each `.json` back into the same folder as its source `.xyz`
5. The right panel shows a batch conversion summary

### Folder Write-back Notes

Writing `.json` files back into the original folder depends on the browser File System Access capability.

Recommended setup:

- open the page via `http://127.0.0.1:2100`
- use the latest Chrome or Edge
- allow directory read/write permission when prompted

If the browser does not support this capability, the frontend can still show the batch conversion summary, but it may not be able to write `.json` files back into the original folders automatically.

### Frame Parsing Rule

Each frame always contains `N + 2` lines, where `N` is the atom count of the current structure:

1. Read line `i` as atom count `N`
2. Read line `i+1` as metadata
3. Read lines `i+2` to `i+N+1` as atom records
4. The next frame starts at `i + N + 2`
5. Continue until the end of the file

### Metadata Parsing

The second line of each frame is parsed into structured key-value metadata and supports:

- `key=value`
- `key = value`
- quoted values
- case-insensitive keys

Special fields are type-converted:

- `Lattice` -> `3x3` numeric matrix
- `virial` -> `3x3` numeric matrix
- `pbc` -> boolean array
- `Properties` -> supported-property definition string

`config_tye` and `config_type` are both normalized to `config_type`.

### Supported Atom Properties

The converter currently reads only the following `Properties` items:

- `species:S:1`
- `pos:R:3`
- `force:R:3`
- `forces:R:3`
- `bec:R:9`

Each atom also gets an `atom_index` starting from `1`.

Atom field order follows the left-to-right order of `Properties` in the source `.xyz`.

### JSON Output Structure

The output JSON root is an array of frame objects.

Each frame is written in this order:

1. `frame_index`
2. `atom_count`
3. metadata fields flattened in the same order as the original `.xyz` metadata line
4. `atoms`

Each atom is written in this order:

1. `atom_index`
2. atom fields flattened according to the left-to-right order of `Properties`

### Units

- Length and position: `Angstrom`
- Energy: `eV`
- Force: `eV/Angstrom`
- virial: `eV`
- BEC: elementary charge `e`

### Notes

- Restart the Flask backend after modifying `xyz_to_json.py`
- The frontend shows JSON exactly in the order returned by the backend

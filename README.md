# 3D STEP Professional Viewer

这是一个基于 Python 的专业级 3D 模型查看与分析软件，专为工程设计人员打造。它不仅支持 STEP 格式，还兼容 STL, OBJ, PLY, VTK 等多种通用 3D 格式。

## ✨ 核心功能

### 1. 多格式支持
- **导入/导出**: 支持 STEP (.stp/.step), STL, OBJ, PLY, VTK 等格式。
- **拖拽加载**: 直接将文件拖入窗口即可打开。
- **最近文件**: 自动记录最近打开的 10 个文件。
- **文件元数据**: 查看文件大小、路径、修改时间等信息。

### 2. 专业渲染引擎
- **显示模式**: 支持着色 (Shaded)、线框 (Wireframe)、点云 (Points)、透明 (Transparent) 模式。
- **高级渲染**: 
  - 抗锯齿 (Anti-Aliasing)
  - 实时阴影 (Shadows)
  - EDL (Eye Dome Lighting) 深度增强
  - 标量条 (Scalar Bar)
  - 地板网格 (Floor Grid)
- **投影方式**: 支持透视投影 (Perspective) 和平行投影 (Parallel/Orthographic)。

### 3. 工程分析工具
- **几何属性**: 实时计算体积、表面积、重心、包围盒尺寸、顶点数与面数。
- **剖切工具**: 支持 X/Y/Z 轴剖切，可动态交互。
- **测量工具**: 两点间距离测量。
- **可视化分析**:
  - 曲率分析 (Curvature)
  - 高程分析 (Elevation)
  - 法线可视化 (Normals)
  - 网格质量检查 (Mesh Quality)

### 4. 网格处理
- **网格简化**: 降低模型面数。
- **网格细分**: 增加模型细节。
- **盒体裁剪**: 裁剪指定区域的模型。
- **点选模式**: 拾取模型上的特定点。

### 5. 用户体验
- **现代化 UI**: 支持深色/浅色主题切换，极简设计风格。
- **自定义布局**: 工具栏支持拖拽、吸附、隐藏。
- **截图功能**: 支持普通截图、透明背景截图、复制到剪贴板。
- **交互导航**: 支持 Trackball 和 Terrain 两种导航风格。

## 🛠️ 环境安装

推荐使用 Conda 管理环境，因为 `pythonocc-core` 依赖复杂的 C++ 库。

### 方式一：Conda (推荐)
```bash
conda create -n step_viewer python=3.9
conda activate step_viewer
conda install -c conda-forge pythonocc-core=7.8.1
pip install -r requirements.txt
```

### 方式二：Pip (仅 Mesh 模式)
如果不安装 `pythonocc-core`，程序将尝试使用 `cadquery-ocp` 或 `gmsh` 降级运行。
```bash
pip install -r requirements.txt
```

## 🚀 运行程序
```bash
python main.py
```

## 📂 文件结构
- `main.py`: 主程序入口
- `requirements.txt`: 依赖列表

## ⚠️ 常见问题
1. **STEP 文件打不开**: 请确保已正确安装 `pythonocc-core`。
2. **界面显示异常**: 尝试在菜单 `视图` -> `主题切换` 中重置主题。

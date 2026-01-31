import sys
import logging
import os
import time

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox, 
    QToolBar, QVBoxLayout, QWidget, QPlainTextEdit, QLabel,
    QHBoxLayout, QPushButton, QColorDialog, QComboBox, QSlider,
    QProgressBar, QToolButton, QMenu, QWidgetAction, QInputDialog,
    QCheckBox, QDialog, QFormLayout, QDialogButtonBox, QSizePolicy
)
from PySide6.QtGui import QAction, QTextCursor, QIcon, QPixmap, QPainter, QColor, QKeySequence, QShortcut, QMouseEvent
from PySide6.QtCore import Qt, QObject, Signal, QTimer, QSettings, QSize, QPoint

# 优先尝试加载工程级 B-Rep 内核 (pythonocc-core 或 cadquery-ocp)
try:
    from OCC.Core.STEPControl import STEPControl_Reader, STEPControl_Writer, STEPControl_AsIs
    from OCC.Core.IFSelect import IFSelect_RetDone
    from OCC.Display.qtDisplay import qtViewer3d
    ENGINE_TYPE = "B-Rep (pythonocc)"
    DEPENDENCIES_OK = True
except Exception:
    try:
        from OCP.STEPControl import STEPControl_Reader, STEPControl_Writer, STEPControl_AsIs
        from OCP.IFSelect import IFSelect_RetDone
        # 核心 B-Rep 转换组件
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.BRep import BRep_Tool
        from OCP.Poly import Poly_Triangulation
        from OCP.TopoDS import TopoDS
        import numpy as np
        
        ENGINE_TYPE = "B-Rep (OCP)"
        DEPENDENCIES_OK = True
    except Exception:
        # 退而求其次，尝试 PyVista 网格模式
        try:
            import pyvista as pv
            from pyvistaqt import QtInteractor
            import gmsh
            ENGINE_TYPE = "Mesh (Preview)"
            DEPENDENCIES_OK = True
        except Exception as e:
            DEPENDENCIES_OK = False
            ENGINE_TYPE = "None"
            print(f"依赖加载失败: {str(e)}")

# 确保在 OCP 模式下也能访问 PyVista
if ENGINE_TYPE == "B-Rep (OCP)":
    try:
        import pyvista as pv
        from pyvistaqt import QtInteractor
    except ImportError:
        DEPENDENCIES_OK = False
        print("OCP 模式需要 pyvista 和 pyvistaqt")

# 配置日志记录
class LogHandler(logging.Handler, QObject):
    log_signal = Signal(str)

    def __init__(self):
        super(LogHandler, self).__init__()
        QObject.__init__(self)

    def emit(self, record):
        msg = self.format(record)
        self.log_signal.emit(msg)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RightClickToolButton(QToolButton):
    """支持右键信号的工具按钮"""
    rightClicked = Signal()
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            self.rightClicked.emit()
        super().mouseReleaseEvent(event)

class FloatingRotationButton(QPushButton):
    """悬浮旋转控制按钮"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(48, 48)
        self.setText("↻")
        self.setToolTip("开启/停止自动旋转 (Y轴 30°/s)")
        self.setCheckable(True)
        self.setStyleSheet("""
            QPushButton {
                background-color: rgba(30, 30, 30, 200);
                color: #10ffaf;
                border: 2px solid #10ffaf;
                border-radius: 24px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(50, 50, 50, 220);
            }
            QPushButton:checked {
                background-color: #10ffaf;
                color: #1e1e1e;
            }
        """)
        self.hide() # 默认隐藏

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Polar Bear")
        self.resize(700, 1000) # 初始化默认窗口尺寸 (700x1000)
        self.setAcceptDrops(True)
        
        # 独立模式状态
        self.is_independent_mode = False
        self.drag_position = None
        
        # 生成白色 α Logo
        self.setWindowIcon(self.create_alpha_icon())
        
        # 初始化设置
        self.settings = QSettings("Trae", "PolarBear")

        # 自动旋转状态
        self.is_rotating = False
        self.rotation_timer = QTimer()
        self.rotation_timer.timeout.connect(self.do_rotate)

        # 应用极简黑色主题
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #242424;
                color: #d1d1d1;
                font-family: "Segoe UI", sans-serif;
            }
            QToolBar {
                background: #242424;
                border-bottom: 1px solid #333;
                spacing: 5px;
            }
            QProgressBar {
                background-color: #1e1e1e;
                border: none;
                border-radius: 0px;
                text-align: center;
                height: 2px;
                color: transparent;
            }
            QProgressBar::chunk {
                background-color: #10ffaf;
            }
            QToolButton {
                background: transparent;
                border: none;
                border-radius: 4px;
                padding: 4px;
                color: #d1d1d1;
                font-size: 12px;
            }
            QToolButton:hover {
                background: #333;
            }
            QMenuBar {
                background-color: #242424;
                color: #d1d1d1;
                border-bottom: 1px solid #333;
            }
            QMenuBar::item:selected {
                background-color: #333;
            }
            QMenu {
                background-color: #242424;
                border: 1px solid #333;
            }
            QMenu::item:selected {
                background-color: #333;
            }
            QComboBox {
                background-color: #242424;
                color: #d1d1d1;
                border: 1px solid #333;
                border-radius: 3px;
                padding: 2px 5px;
                min-width: 60px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #242424;
                color: #d1d1d1;
                selection-background-color: #333;
            }
            QSlider::groove:horizontal {
                border: 1px solid #333;
                height: 4px;
                background: #1e1e1e;
                margin: 0px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #d1d1d1;
                border: 1px solid #d1d1d1;
                width: 10px;
                height: 10px;
                margin: -4px 0;
                border-radius: 5px;
            }
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d9d9d9;
                font-size: 9px;
                border-top: 1px solid #333;
            }
            QLabel {
                color: #888;
                font-size: 10px;
            }
        """)

        # 主布局
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0) # 移除边距以实现沉浸式
        self.layout.setSpacing(0)
        
        # 3D 视图容器
        self.view_container = QWidget()
        self.view_layout = QVBoxLayout(self.view_container)
        self.view_layout.setContentsMargins(0, 0, 0, 0)
        self.view_layout.setSpacing(0)
        self.layout.addWidget(self.view_container)

        # 3D 视图区域
        self.viewer = None
        self.display = None
        self.plotter = None
        self.current_shape = None 
        self.current_mesh = None
        self.mesh_actor = None
        self.edge_actor = None # 专门存储特征线 actor
        self.model_color = "#bcbcbc" # 初始改为 #bcbcbc
        self.current_opacity = 1.0
        self.current_specular = 0.5   # 默认光泽度
        # 1. 视角与精度控制
        self.current_fov = 60         # 增加默认视角
        self.current_precision = "Medium" 
        self.show_mesh_edges = False 
        
        if DEPENDENCIES_OK:
            if ENGINE_TYPE == "B-Rep (pythonocc)":
                try:
                    self.viewer = qtViewer3d(self)
                    self.view_layout.addWidget(self.viewer)
                    self.viewer.InitDriver()
                    self.display = self.viewer._display
                    self.display.set_bg_gradient_color([36, 36, 36], [51, 51, 51]) # 深灰渐变
                    logger.info("工程级 B-Rep (pythonocc) 引擎初始化成功")
                except Exception as e:
                    logger.error(f"B-Rep 视图初始化失败: {str(e)}")
            else:
                # OCP 和 Mesh 模式都使用 PyVista
                try:
                    self.plotter = QtInteractor(self)
                    self.view_layout.addWidget(self.plotter)
                    # 设置右键菜单策略
                    self.plotter.setContextMenuPolicy(Qt.CustomContextMenu)
                    self.plotter.customContextMenuRequested.connect(self.show_context_menu)
                    
                    # 设置深色渐变背景
                    self.plotter.set_background(color="#242424", top="#333333")
                    self.plotter.enable_anti_aliasing()
                    
                    # 增强光感与立体感配置 (移除 EDL 以去掉光圈/模糊)
                    self.plotter.enable_shadows()           # 开启阴影
                    self.plotter.enable_lightkit()          # 使用专业三点照明系统
                    
                    logger.info(f"{ENGINE_TYPE} 渲染引擎初始化成功")
                except Exception as e:
                    logger.error(f"视图初始化失败: {str(e)}")
        else:
            self.show_error_label("环境缺失，请运行: pip install cadquery-ocp pyvista gmsh")

        # 3D 底部工具栏 (包含旋转和截图按钮)
        self.view_bottom_toolbar = QToolBar(self)
        self.view_bottom_toolbar.setFixedHeight(46)
        self.view_bottom_toolbar.setStyleSheet("border-top: 1px solid #333; border-bottom: none;")
        
        # 旋转按钮
        self.rotate_btn = QPushButton("旋转")
        self.rotate_btn.setCheckable(True)
        self.rotate_btn.setFixedWidth(60)
        self.rotate_btn.setFixedHeight(40)
        self.rotate_btn.setStyleSheet("font-size: 12px; font-weight: bold; color: black; background-color: #2fff7b; border: none; border-radius: 10px; padding: 0px;")
        self.rotate_btn.clicked.connect(self.toggle_rotation)
        self.view_bottom_toolbar.addWidget(self.rotate_btn)
        
        # 间隔
        spacer = QWidget()
        spacer.setFixedWidth(5)
        self.view_bottom_toolbar.addWidget(spacer)
        
        # 截图按钮
        self.screenshot_btn = QPushButton("截图")
        self.screenshot_btn.setFixedWidth(60)
        self.screenshot_btn.setFixedHeight(40)
        self.screenshot_btn.setStyleSheet("font-size: 12px; font-weight: bold; color: black; background-color: #2fff7b; border: none; border-radius: 10px; padding: 0px;")
        self.screenshot_btn.clicked.connect(self.take_screenshot)
        self.view_bottom_toolbar.addWidget(self.screenshot_btn)

        # 间隔
        spacer2 = QWidget()
        spacer2.setFixedWidth(5)
        self.view_bottom_toolbar.addWidget(spacer2)

        # 设置按钮 (集成所有功能) - 移至此处
        self.settings_btn = QPushButton("⚙️")
        self.settings_btn.setToolTip("全局设置与功能菜单")
        self.settings_btn.setFixedWidth(20)
        self.settings_btn.setFixedHeight(20)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888;
                border: none;
                border-radius: 2px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #333;
                color: #fff;
            }
            QPushButton:menu-indicator { image: none; }
        """)
        
        # 构建设置菜单
        self.settings_menu = QMenu(self)
        self.settings_menu.setStyleSheet("""
            QMenu { background-color: #242424; color: #d1d1d1; border: 1px solid #444; }
            QMenu::item { padding: 6px 25px 6px 20px; }
            QMenu::item:selected { background-color: #333; }
            QMenu::separator { height: 1px; background: #444; margin: 5px 0; }
        """)
        self.settings_btn.setMenu(self.settings_menu)
        self.view_bottom_toolbar.addWidget(self.settings_btn)
        
        self.view_layout.addWidget(self.view_bottom_toolbar)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(2)
        self.layout.addWidget(self.progress_bar)

        # 日志与设置区域容器
        self.log_container = QWidget()
        self.log_container.setFixedHeight(80)
        self.log_layout = QHBoxLayout(self.log_container)
        self.log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_layout.setSpacing(0)
        
        # 日志显示区域
        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFrameShape(QPlainTextEdit.NoFrame)
        self.log_layout.addWidget(self.log_display)

        # 设置按钮已移动至底部 3D 工具栏
        
        self.layout.addWidget(self.log_container)

        # 设置日志处理器
        self.handler = LogHandler()
        self.handler.setFormatter(logging.Formatter('%(message)s')) # 简化日志格式
        self.handler.log_signal.connect(self.append_log)
        logging.getLogger().addHandler(self.handler)

        # 悬浮旋转按钮
        self.float_rotate_btn = FloatingRotationButton(self.central_widget)
        self.float_rotate_btn.clicked.connect(self.toggle_rotation_from_float)
        
        # 菜单与工具栏
        self.load_recent_files()
        self.setup_ui()
        logger.info("Ready.")

    def toggle_rotation_from_float(self, checked):
        """悬浮按钮控制旋转"""
        # 同步底部工具栏按钮状态
        if hasattr(self, 'rotate_btn'):
            self.rotate_btn.setChecked(checked)
        self.toggle_rotation(checked)

    def toggle_rotation(self, checked):
        self.is_rotating = checked
        
        # 同步悬浮按钮状态
        if hasattr(self, 'float_rotate_btn'):
            self.float_rotate_btn.setChecked(checked)
            
        if self.is_rotating:
            # 开启时保持绿色背景，或者可以加深一点以示区别，这里保持一致但加深一点点
            self.rotate_btn.setStyleSheet("font-size: 12px; font-weight: bold; color: black; background-color: #26cc62; border: none; border-radius: 10px;")
            self.rotation_timer.start(30) # 30ms 刷新
        else:
            self.rotate_btn.setStyleSheet("font-size: 12px; font-weight: bold; color: black; background-color: #2fff7b; border: none; border-radius: 10px;")
            self.rotation_timer.stop()

    def do_rotate(self):
        if self.plotter:
            self.plotter.camera.azimuth += 1 # 每次旋转 1 度
            self.plotter.render()

    def take_screenshot(self):
        """截图并保存"""
        if not self.plotter:
            logger.error("无可用 3D 视窗进行截图")
            return
        
        # 暂时停止自动旋转以获得清晰截图
        was_rotating = self.is_rotating
        if was_rotating:
            self.rotation_timer.stop()

        path, _ = QFileDialog.getSaveFileName(
            self, "保存 3D 视图截图", "screenshot.png", "Images (*.png *.jpg *.jpeg)"
        )
        
        if path:
            try:
                # 强制渲染一帧以确保最新
                self.plotter.render()
                self.plotter.screenshot(path)
                logger.info(f"截图已成功保存至: {path}")
            except Exception as e:
                logger.error(f"截图保存失败: {str(e)}")
        
        # 恢复旋转
        if was_rotating:
            self.rotation_timer.start(30)

    def copy_screenshot_to_clipboard(self):
        """复制截图到剪贴板"""
        if not self.plotter:
            return
        try:
            # 抓取控件截图
            pixmap = self.plotter.grab()
            QApplication.clipboard().setPixmap(pixmap)
            logger.info("截图已复制到剪贴板")
        except Exception as e:
            logger.error(f"复制截图失败: {e}")

    def clear_log(self):
        """清空日志"""
        if hasattr(self, 'log_display'):
            self.log_display.clear()
            logger.info("日志已清空")

    def toggle_log_view(self, checked):
        """显示/隐藏日志区域"""
        if hasattr(self, 'log_container'):
            self.log_container.setVisible(checked)

    def create_alpha_icon(self):
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setPen(QColor("#242424")) # 改成 #242424
        font = painter.font()
        font.setPixelSize(28)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "α")
        painter.end()
        return QIcon(pixmap)

    def show_error_label(self, text):
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: red; font-weight: bold; font-size: 14px; border: 1px solid gray;")
        self.layout.addWidget(label)

    def configure_toolbar(self, name):
        """配置标准可移动/横向工具栏"""
        tb = QToolBar(name, self)
        tb.setOrientation(Qt.Horizontal)
        tb.setMovable(True)
        tb.setFloatable(True)
        tb.setAllowedAreas(Qt.LeftToolBarArea | Qt.RightToolBarArea | Qt.TopToolBarArea)
        # 禁止工具栏自带的右键菜单
        tb.setContextMenuPolicy(Qt.PreventContextMenu)
        return tb

    def show_toolbar_edit_menu(self, toolbar, pos):
        """工具栏右键编辑菜单：控制吸附和移动"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #242424; color: #d1d1d1; border: 1px solid #444; }
            QMenu::item:selected { background-color: #333; }
        """)
        
        move_act = menu.addAction("🔓 允许移动")
        move_act.setCheckable(True)
        move_act.setChecked(toolbar.isMovable())
        move_act.triggered.connect(lambda: toolbar.setMovable(not toolbar.isMovable()))
        
        float_act = menu.addAction("☁️ 允许浮动")
        float_act.setCheckable(True)
        float_act.setChecked(toolbar.isFloatable())
        float_act.triggered.connect(lambda: toolbar.setFloatable(not toolbar.isFloatable()))

        menu.addSeparator()
        
        left_area = menu.addAction("⬅️ 吸附到左侧")
        left_area.triggered.connect(lambda: self.addToolBar(Qt.LeftToolBarArea, toolbar))
        
        right_area = menu.addAction("➡️ 吸附到右侧")
        right_area.triggered.connect(lambda: self.addToolBar(Qt.RightToolBarArea, toolbar))
        
        top_area = menu.addAction("⬆️ 吸附到顶部")
        top_area.triggered.connect(lambda: self.addToolBar(Qt.TopToolBarArea, toolbar))
        
        menu.exec_(toolbar.mapToGlobal(pos))

    def create_menu_button(self, icon_text, tooltip, parent_toolbar):
        """创建工具按钮 (取消左键编辑菜单)"""
        btn = QToolButton(self)
        btn.setText(icon_text)
        btn.setToolTip(tooltip)
        # 取消左键弹出菜单模式，恢复普通按钮点击
        # btn.setPopupMode(QToolButton.InstantPopup) 
        btn.setFixedHeight(45)
        
        # 移除左键编辑菜单逻辑
        # menu = QMenu(btn)
        # ... (removed)
        # btn.setMenu(menu)
        
        parent_toolbar.addWidget(btn)
        return btn

    def toggle_measure(self):
        if not self.plotter:
            return
            
        if getattr(self, 'is_measuring', False):
            # 取消测量
            try:
                self.plotter.clear_measure_widgets()
                self.is_measuring = False
                logger.info("已退出测量模式")
            except Exception as e:
                logger.error(f"退出测量失败: {e}")
        else:
            # 开启测量
            try:
                self.plotter.clear_measure_widgets() # 先清除可能存在的残留
                self.plotter.add_measurement_widget()
                self.is_measuring = True
                logger.info("已启用测量工具 (拖动控制点进行测量，右键可取消)")
            except Exception as e:
                logger.error(f"测量工具启动失败: {e}")

    def toggle_section(self):
        if not self.plotter: return
        
        # 状态初始化
        if not hasattr(self, 'is_sectioning'):
            self.is_sectioning = False
            
        if self.is_sectioning:
            # 关闭逻辑
            try:
                self.plotter.clear_plane_widgets()
                if self.mesh_actor: self.mesh_actor.SetVisibility(True)
                self.is_sectioning = False
                logger.info("已关闭剖切工具")
            except Exception as e:
                logger.error(f"关闭剖切失败: {e}")
        else:
            # 开启逻辑
            if not (self.current_mesh and self.current_mesh.n_points > 0):
                logger.warning("无有效模型可剖切")
                return

            try:
                if self.mesh_actor: self.mesh_actor.SetVisibility(False)
                
                # 关键修复：确保传递的是 pyvista.PolyData (它是 vtkDataObject)
                if not isinstance(self.current_mesh, (pv.PolyData, pv.UnstructuredGrid)):
                     logger.error(f"模型数据类型错误: {type(self.current_mesh)}")
                     if self.mesh_actor: self.mesh_actor.SetVisibility(True)
                     return

                self.plotter.add_mesh_clip_plane(
                    self.current_mesh, 
                    color=self.model_color,
                    show_edges=False,
                    assign_to_axis='z',
                    interaction_event='always',
                    specular=self.current_specular
                )
                self.is_sectioning = True
                logger.info("已启用剖切工具")
            except Exception as e:
                logger.error(f"剖切启动失败: {e}")
                if self.mesh_actor: self.mesh_actor.SetVisibility(True)

    def delete_object(self):
        """删除/清除当前物体"""
        if self.plotter:
            try:
                self.plotter.clear()
                self.current_shape = None
                self.current_mesh = None
                self.mesh_actor = None
                self.edge_actor = None
                
                # 重置状态
                self.is_measuring = False
                self.is_sectioning = False
                self.axes_visible = True
                self.bounds_visible = False
                
                logger.info("已删除当前物体并重置场景")
            except Exception as e:
                logger.error(f"删除物体失败: {e}")

    def load_recent_files(self):
        settings = QSettings("PolarBear", "RecentFiles")
        self.recent_files = settings.value("fileList", [])
        if not isinstance(self.recent_files, list):
            self.recent_files = []

    def save_recent_file(self, path):
        if not path: return
        path = os.path.abspath(path)
        
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        
        if len(self.recent_files) > 10:
            self.recent_files = self.recent_files[:10]
            
        settings = QSettings("PolarBear", "RecentFiles")
        settings.setValue("fileList", self.recent_files)
        self.update_recent_menu()

    def update_recent_menu(self):
        if not hasattr(self, 'recent_menu'): return
        
        self.recent_menu.clear()
        if not self.recent_files:
            self.recent_menu.setEnabled(False)
            return
            
        self.recent_menu.setEnabled(True)
        for path in self.recent_files:
            action = QAction(os.path.basename(path), self)
            action.setData(path)
            action.setToolTip(path)
            action.triggered.connect(lambda checked, p=path: self.load_step(p))
            self.recent_menu.addAction(action)
            
        self.recent_menu.addSeparator()
        clear_act = self.recent_menu.addAction("清除记录")
        clear_act.triggered.connect(self.clear_recent_files)

    def clear_recent_files(self):
        self.recent_files = []
        settings = QSettings("PolarBear", "RecentFiles")
        settings.setValue("fileList", [])
        self.update_recent_menu()

    def update_toolbar_menu(self):
        if not hasattr(self, 'toolbar_menu'): return
        
        self.toolbar_menu.clear()
        
        toolbars = self.findChildren(QToolBar)
        for tb in toolbars:
            name = tb.windowTitle()
            if not name: continue
            
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(tb.isVisible())
            action.triggered.connect(lambda checked, t=tb: t.setVisible(checked))
            self.toolbar_menu.addAction(action)

    def reset_section_plane(self):
        if self.plotter and getattr(self, 'is_sectioning', False):
            try:
                # 重新开启一次即可重置
                self.toggle_section() # 关闭
                self.toggle_section() # 开启
                logger.info("已重置剖切平面")
            except Exception as e:
                logger.error(f"重置剖切失败: {e}")

    def toggle_edges(self, checked):
        """切换边线显示"""
        self.show_mesh_edges = checked
        if self.edge_actor:
            self.edge_actor.SetVisibility(checked)
            self.plotter.render()
            logger.info(f"边线显示: {'开启' if checked else '关闭'}")
        elif self.current_mesh:
             # 如果没有 edge_actor 但有 mesh，尝试重新生成或设置属性
             if checked:
                 # 尝试提取边线
                 try:
                     edges = self.current_mesh.extract_feature_edges(
                        boundary_edges=True, 
                        feature_edges=True, 
                        manifold_edges=False
                     )
                     self.edge_actor = self.plotter.add_mesh(edges, color="black", line_width=1)
                     logger.info("已生成并显示边线")
                 except Exception as e:
                     logger.error(f"生成边线失败: {e}")

    def set_points_mode(self):
        """切换点云模式"""
        if self.mesh_actor:
            self.mesh_actor.SetVisibility(True)
            self.mesh_actor.prop.style = 'points'
            self.mesh_actor.prop.point_size = 5
            self.mesh_actor.prop.render_points_as_spheres = True
            if self.edge_actor:
                self.edge_actor.SetVisibility(False)
            self.plotter.render()
            logger.info("切换至点云模式")

    def pick_background_color(self):
        """选择背景颜色"""
        color = QColorDialog.getColor()
        if color.isValid():
            c = color.name()
            if self.plotter:
                self.plotter.set_background(c)
                logger.info(f"背景颜色已设置为: {c}")

    def toggle_grid(self, checked=None):
        """切换网格显示"""
        if checked is None:
            # 如果没有传入 checked (例如直接调用), 则反转当前状态
            checked = not getattr(self, 'grid_visible', False)
            
        self.grid_visible = checked
        
        if self.plotter:
            if checked:
                self.plotter.show_grid()
                logger.info("已开启网格")
            else:
                self.plotter.remove_bounds_axes()
                logger.info("已关闭网格")

    # --- 新增功能 Batch 2: 渲染增强 ---
    def toggle_anti_aliasing(self, checked):
        """切换抗锯齿"""
        if checked:
            self.plotter.enable_anti_aliasing()
        else:
            self.plotter.disable_anti_aliasing()
        logger.info(f"抗锯齿: {'开启' if checked else '关闭'}")

    def toggle_shadows(self, checked):
        """切换阴影"""
        if checked:
            self.plotter.enable_shadows()
        else:
            self.plotter.disable_shadows()
        self.plotter.render()
        logger.info(f"阴影: {'开启' if checked else '关闭'}")

    def toggle_edl(self, checked):
        """切换 EDL (Eye Dome Lighting)"""
        if checked:
            self.plotter.enable_eye_dome_lighting()
        else:
            self.plotter.disable_eye_dome_lighting()
        self.plotter.render()
        logger.info(f"EDL 光照: {'开启' if checked else '关闭'}")
        
    def toggle_floor(self, checked):
        """切换地板显示"""
        if checked:
            self.floor_actor = self.plotter.add_floor(face='-z', color='#444444', pad=1.5, opacity=0.5, show_edges=True)
        else:
            if hasattr(self, 'floor_actor') and self.floor_actor:
                self.plotter.remove_actor(self.floor_actor)
                self.floor_actor = None
        self.plotter.render()
        logger.info(f"地板: {'开启' if checked else '关闭'}")

    def toggle_scalar_bar(self, checked):
        """切换标量条"""
        if checked:
             if self.mesh_actor:
                 self.plotter.add_scalar_bar()
        else:
            self.plotter.remove_scalar_bar()
        self.plotter.render()

    # --- 新增功能 Batch 3: 分析工具 ---
    def plot_curvature(self):
        """曲率分析"""
        if not self.current_mesh: 
            QMessageBox.warning(self, "提示", "请先加载模型")
            return
        self.current_mesh['curvature'] = self.current_mesh.curvature(curv_type='mean')
        if self.mesh_actor:
            self.mesh_actor.mapper.scalar_range = (self.current_mesh['curvature'].min(), self.current_mesh['curvature'].max())
            self.plotter.update_scalars(self.current_mesh['curvature'], mesh=self.mesh_actor)
        self.plotter.add_scalar_bar("Mean Curvature")
        self.plotter.render()
        logger.info("已应用曲率分析")

    def plot_elevation(self):
        """高程分析 (Z轴)"""
        if not self.current_mesh: 
            QMessageBox.warning(self, "提示", "请先加载模型")
            return
        self.current_mesh['elevation'] = self.current_mesh.points[:, 2]
        if self.mesh_actor:
            self.mesh_actor.mapper.scalar_range = (self.current_mesh['elevation'].min(), self.current_mesh['elevation'].max())
            self.plotter.update_scalars(self.current_mesh['elevation'], mesh=self.mesh_actor)
        self.plotter.add_scalar_bar("Elevation (Z)")
        self.plotter.render()
        logger.info("已应用高程分析")

    def show_normals(self):
        """显示法线"""
        if not self.current_mesh: return
        try:
            normals = self.current_mesh.compute_normals(cell_normals=True, point_normals=True)
            arrows = normals.glyph(scale="Normals", orient="Normals", tolerance=0.05, factor=0.1) # factor adjustment needed usually
            self.plotter.add_mesh(arrows, color="yellow", name="normals")
            logger.info("已显示表面法线")
        except Exception as e:
            logger.error(f"计算法线失败: {e}")

    def compute_quality(self):
        """网格质量分析"""
        if not self.current_mesh: return
        try:
            qual = self.current_mesh.compute_cell_quality(quality_measure='scaled_jacobian')
            self.current_mesh['quality'] = qual['CellQuality']
            if self.mesh_actor:
                self.plotter.update_scalars(self.current_mesh['quality'], mesh=self.mesh_actor)
            self.plotter.add_scalar_bar("Cell Quality")
            self.plotter.render()
            logger.info("已应用网格质量分析")
        except Exception as e:
            logger.error(f"质量分析失败: {e}")

    # --- 新增功能 Batch 4: 几何与交互工具 ---
    def enable_point_picking(self, checked):
        """点选模式"""
        if checked:
            self.plotter.enable_point_picking(callback=lambda p: logger.info(f"选中点: {p}"), show_message=True, color='red', point_size=10, use_mesh=True)
        else:
            self.plotter.disable_picking()

    def clip_box(self):
        """盒式剖切"""
        if not self.current_mesh: return
        try:
            self.plotter.add_mesh_clip_box(self.current_mesh, color=self.model_color)
            logger.info("已启用盒式剖切")
        except Exception as e:
            logger.error(f"盒式剖切失败: {e}")

    def subdivide_mesh(self):
        """网格细分 (平滑)"""
        if not self.current_mesh: return
        try:
            self.current_mesh = self.current_mesh.subdivide(1, subfilter='loop')
            if self.plotter:
                self.plotter.clear()
                self.mesh_actor = self.plotter.add_mesh(self.current_mesh, color=self.model_color, smooth_shading=True)
                self.plotter.reset_camera()
            logger.info("网格已细分")
        except Exception as e:
            logger.error(f"细分失败: {e}")

    def screenshot_transparent(self):
        """透明背景截图"""
        path, _ = QFileDialog.getSaveFileName(self, "保存截图", "screenshot_transparent.png", "PNG (*.png)")
        if path:
            self.plotter.screenshot(path, transparent_background=True)
            logger.info(f"透明截图已保存: {path}")

    # --- 新增功能 Batch 5: 系统与视角 ---
    def set_trackball_style(self):
        # PyVista 默认通常是 Trackball
        self.plotter.interactor.SetInteractorStyle(pv.vtk.vtkInteractorStyleTrackballCamera())
        logger.info("切换为 Trackball 交互模式")

    def set_terrain_style(self):
        self.plotter.interactor.SetInteractorStyle(pv.vtk.vtkInteractorStyleTerrain())
        logger.info("切换为 Terrain 交互模式")

    def save_view(self):
        self.saved_camera = (self.plotter.camera.GetPosition(), self.plotter.camera.GetFocalPoint(), self.plotter.camera.GetViewUp())
        logger.info("视角已保存")

    def load_view(self):
        if hasattr(self, 'saved_camera'):
            pos, focal, up = self.saved_camera
            self.plotter.camera.SetPosition(pos)
            self.plotter.camera.SetFocalPoint(focal)
            self.plotter.camera.SetViewUp(up)
            self.plotter.render()
            logger.info("视角已恢复")
        else:
            logger.warning("未保存视角")

    def reset_settings(self):
        """重置所有设置"""
        reply = QMessageBox.question(self, '确认重置', "确定要重置所有设置吗？这将清除保存的布局和偏好。",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        self.settings.clear()
        
        # 恢复默认窗口尺寸
        self.resize(700, 1000)
        
        if self.plotter:
            self.plotter.clear()
            self.plotter.enable_anti_aliasing() # Default
            self.plotter.enable_shadows() # Default
        
        logger.info("所有设置已重置")
        QMessageBox.information(self, "重置完成", "设置已重置。窗口尺寸已恢复默认 (700x1000)。")

    def toggle_fullscreen(self):
        """切换全屏模式"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def simplify_mesh(self):
        """网格简化"""
        if not self.current_mesh:
            QMessageBox.warning(self, "提示", "无模型可简化")
            return
        
        target, ok = QInputDialog.getDouble(self, "网格简化", "目标减少比例 (0.1-0.9):", 0.5, 0.1, 0.9, 2)
        if ok:
            try:
                self.current_mesh = self.current_mesh.decimate(target)
                # 更新显示
                if self.plotter:
                    self.plotter.clear()
                    self.mesh_actor = self.plotter.add_mesh(
                        self.current_mesh, 
                        color=self.model_color, 
                        smooth_shading=True,
                        specular=self.current_specular
                    )
                    # 重建边线
                    edges = self.current_mesh.extract_feature_edges(
                        boundary_edges=True, feature_edges=True, manifold_edges=False
                    )
                    self.edge_actor = self.plotter.add_mesh(edges, color="black", line_width=1)
                    
                    self.plotter.render()
                    logger.info(f"网格已简化，减少比例: {target}")
                    QMessageBox.information(self, "成功", f"简化完成\n剩余面数: {self.current_mesh.n_cells}")
            except Exception as e:
                logger.error(f"简化失败: {e}")
                QMessageBox.warning(self, "错误", f"简化失败: {e}")

    def show_camera_info(self):
        """显示相机信息"""
        if not self.plotter: return
        cam = self.plotter.camera
        pos = cam.position
        foc = cam.focal_point
        up = cam.up
        msg = (
            f"📸 相机参数:\n\n"
            f"位置 (Position):\n  X: {pos[0]:.2f}, Y: {pos[1]:.2f}, Z: {pos[2]:.2f}\n\n"
            f"焦点 (Focal Point):\n  X: {foc[0]:.2f}, Y: {foc[1]:.2f}, Z: {foc[2]:.2f}\n\n"
            f"上方 (View Up):\n  X: {up[0]:.2f}, Y: {up[1]:.2f}, Z: {up[2]:.2f}\n\n"
            f"视角 (View Angle): {cam.view_angle:.2f}°\n"
            f"距离 (Distance): {cam.distance:.2f}"
        )
        QMessageBox.information(self, "相机信息", msg)

    def set_section_axis(self, axis):
        """设置剖切轴向"""
        if not getattr(self, 'is_sectioning', False):
            self.toggle_section() # 自动开启
            
        # PyVista 的 add_mesh_clip_plane 返回的是 widget，比较难直接修改轴向
        # 简单做法是重置剖切并指定轴向
        if self.plotter and self.current_mesh:
            self.plotter.clear_plane_widgets()
            if self.mesh_actor: self.mesh_actor.SetVisibility(False)
            
            try:
                self.plotter.add_mesh_clip_plane(
                    self.current_mesh, 
                    color=self.model_color,
                    show_edges=False,
                    assign_to_axis=axis,
                    interaction_event='always',
                    specular=self.current_specular
                )
                self.is_sectioning = True
                logger.info(f"已切换剖切轴向至: {axis.upper()} 轴")
            except Exception as e:
                logger.error(f"切换剖切轴失败: {e}")

    def set_opacity_dialog(self):
        """设置透明度对话框"""
        if not self.mesh_actor:
            return
            
        val, ok = QInputDialog.getInt(self, "设置透明度", "透明度 (0-100%):", int(self.current_opacity * 100), 0, 100, 1)
        if ok:
            self.on_opacity_changed(val)
            # 同步滑块
            if hasattr(self, 'opacity_slider'):
                self.opacity_slider.setValue(val)

    def setup_menu_bar(self):
        """创建顶部标准菜单栏"""
        menubar = self.menuBar()
        menubar.clear() 
        
        # 1. 文件菜单 (File)
        file_menu = menubar.addMenu("文件 (&File)")
        
        open_act = QAction("📂 打开文件 (Open)", self)
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self.open_step)
        file_menu.addAction(open_act)
        
        # 最近文件
        self.recent_menu = file_menu.addMenu("🕒 最近打开 (Recent)")
        self.update_recent_menu()
        
        # 文件信息 (New)
        info_act = QAction("ℹ️ 文件元数据 (Info)", self)
        info_act.triggered.connect(self.show_file_info)
        file_menu.addAction(info_act)

        save_act = QAction("📤 导出模型 (Export)", self)
        save_act.setShortcut("Ctrl+E")
        save_act.triggered.connect(self.export_file)
        file_menu.addAction(save_act)
        
        file_menu.addSeparator()
        
        del_act = QAction("🗑️ 删除物体 (Delete)", self)
        del_act.setShortcut("Del")
        del_act.triggered.connect(self.delete_object)
        file_menu.addAction(del_act)
        
        file_menu.addSeparator()
        
        exit_act = QAction("❌ 退出 (Exit)", self)
        exit_act.setShortcut("Ctrl+Q")
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)
        
        # 2. 编辑菜单 (Edit)
        edit_menu = menubar.addMenu("编辑 (&Edit)")
        
        copy_act = QAction("📋 复制截图 (Copy Screenshot)", self)
        copy_act.setShortcut("Ctrl+C")
        copy_act.triggered.connect(self.copy_screenshot_to_clipboard)
        edit_menu.addAction(copy_act)
        
        edit_menu.addSeparator()
        
        clear_log_act = QAction("🧹 清空日志 (Clear Log)", self)
        clear_log_act.triggered.connect(self.clear_log)
        edit_menu.addAction(clear_log_act)

        # 3. 视图菜单 (View)
        view_menu = menubar.addMenu("视图 (&View)")
        
        # 工具栏显示控制
        self.toolbar_menu = view_menu.addMenu("🛠️ 工具栏显示")
        # 将在 setup_ui 中更新内容
        
        view_menu.addSeparator()
        
        log_view_act = QAction("📝 显示日志 (Log View)", self)
        log_view_act.setCheckable(True)
        log_view_act.setChecked(True)
        log_view_act.triggered.connect(self.toggle_log_view)
        view_menu.addAction(log_view_act)
        
        view_menu.addSeparator()

        # 显示控制
        edges_act = QAction("📏 显示边线 (Show Edges)", self)
        edges_act.setCheckable(True)
        edges_act.setChecked(getattr(self, 'show_mesh_edges', False))
        edges_act.triggered.connect(self.toggle_edges)
        view_menu.addAction(edges_act)

        grid_act = QAction("🕸️ 显示网格 (Show Grid)", self)
        grid_act.setCheckable(True)
        grid_act.setChecked(getattr(self, 'grid_visible', False))
        grid_act.triggered.connect(self.toggle_grid)
        view_menu.addAction(grid_act)

        full_act = QAction("📺 全屏模式 (Fullscreen)", self)
        full_act.setShortcut("F11")
        full_act.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(full_act)
        
        view_menu.addSeparator()
        
        bg_act = QAction("🎨 设置背景颜色 (Background Color)", self)
        bg_act.triggered.connect(self.pick_background_color)
        view_menu.addAction(bg_act)

        op_act = QAction("💧 设置透明度 (Opacity)", self)
        op_act.triggered.connect(self.set_opacity_dialog)
        view_menu.addAction(op_act)

        view_menu.addSeparator()

        view_menu.addAction("🧊 等轴测 (Iso)", lambda: self.plotter and self.plotter.view_isometric())
        view_menu.addAction("🖥️ 适应屏幕 (Fit)", lambda: self.plotter and self.plotter.reset_camera())
        view_menu.addSeparator()
        view_menu.addAction("⬆️ 顶视图 (Top)", lambda: self.plotter and self.plotter.view_xy())
        view_menu.addAction("⬇️ 底视图 (Bottom)", lambda: self.plotter and self.plotter.view_xy(negative=True))
        view_menu.addAction("⏺️ 前视图 (Front)", lambda: self.plotter and self.plotter.view_xz())
        view_menu.addAction("🔙 后视图 (Back)", lambda: self.plotter and self.plotter.view_xz(negative=True))
        view_menu.addAction("⬅️ 左视图 (Left)", lambda: self.plotter and self.plotter.view_yz(negative=True))
        view_menu.addAction("➡️ 右视图 (Right)", lambda: self.plotter and self.plotter.view_yz())
        
        view_menu.addSeparator()
        
        proj_menu = view_menu.addMenu("🎥 投影方式")
        proj_menu.addAction("📐 透视投影", self.set_perspective_view)
        proj_menu.addAction("📏 平行投影", self.set_parallel_view)
        
        view_menu.addSeparator()
        
        # 显示模式子菜单
        mode_menu = view_menu.addMenu("👁️ 显示模式")
        mode_menu.addAction("🌕 着色模式 (Surface)", self.set_shaded_mode)
        mode_menu.addAction("🔳 着色+边线 (Surface with Edges)", self.set_surface_with_edges_mode)
        mode_menu.addAction("🕸️ 线框模式 (Wireframe)", self.set_wireframe_mode)
        mode_menu.addAction("☁️ 点云模式 (Points)", self.set_points_mode)
        mode_menu.addAction("👻 透明模式 (Transparent)", self.set_transparent_mode)
        
        mode_menu.addSeparator()
        
        mode_menu.addAction("⬛ 平坦着色 (Flat Shading)", self.set_flat_shading_mode)
        mode_menu.addAction("🟣 平滑着色 (Smooth Shading)", self.set_smooth_shading_mode)

        # 渲染效果子菜单 (New)
        render_menu = view_menu.addMenu("✨ 渲染效果 (Rendering)")
        
        aa_act = QAction("🔲 抗锯齿 (Anti-Aliasing)", self)
        aa_act.setCheckable(True)
        aa_act.triggered.connect(self.toggle_anti_aliasing)
        render_menu.addAction(aa_act)
        
        shadow_act = QAction("🌑 阴影 (Shadows)", self)
        shadow_act.setCheckable(True)
        shadow_act.triggered.connect(self.toggle_shadows)
        render_menu.addAction(shadow_act)
        
        edl_act = QAction("💡 EDL 光照 (Eye Dome Lighting)", self)
        edl_act.setCheckable(True)
        edl_act.triggered.connect(self.toggle_edl)
        render_menu.addAction(edl_act)
        
        floor_act = QAction("🧱 显示地板 (Floor)", self)
        floor_act.setCheckable(True)
        floor_act.triggered.connect(self.toggle_floor)
        render_menu.addAction(floor_act)
        
        scalar_act = QAction("🌈 标量条 (Scalar Bar)", self)
        scalar_act.setCheckable(True)
        scalar_act.triggered.connect(self.toggle_scalar_bar)
        render_menu.addAction(scalar_act)

        view_menu.addSeparator()
        
        theme_menu = view_menu.addMenu("🎨 主题切换")
        theme_menu.addAction("🌑 深色模式 (Dark)", lambda: self.set_theme("dark"))
        theme_menu.addAction("☀️ 浅色模式 (Light)", lambda: self.set_theme("light"))

        # 4. 分析菜单 (Analysis) - New
        analysis_menu = menubar.addMenu("分析 (&Analysis)")
        analysis_menu.addAction("📈 曲率分析 (Curvature)", self.plot_curvature)
        analysis_menu.addAction("🏔️ 高程分析 (Elevation)", self.plot_elevation)
        analysis_menu.addAction("📏 法线可视化 (Normals)", self.show_normals)
        analysis_menu.addAction("🔍 网格质量 (Mesh Quality)", self.compute_quality)

        # 5. 工具菜单 (Tools)
        tools_menu = menubar.addMenu("工具 (&Tools)")
        
        tools_menu.addAction("📏 测量距离 (Measure)", self.toggle_measure)
        
        section_menu = tools_menu.addMenu("🔪 剖切工具 (Section)")
        section_menu.addAction("启用/关闭", self.toggle_section)
        section_menu.addSeparator()
        section_menu.addAction("❌ X 轴剖切", lambda: self.set_section_axis('x'))
        section_menu.addAction("❌ Y 轴剖切", lambda: self.set_section_axis('y'))
        section_menu.addAction("❌ Z 轴剖切", lambda: self.set_section_axis('z'))
        section_menu.addSeparator()
        section_menu.addAction("重置剖切", self.reset_section_plane)
        
        tools_menu.addSeparator()
        
        bounds_act = QAction("📦 显示包围盒 (Bounding Box)", self)
        bounds_act.setCheckable(True)
        bounds_act.setChecked(getattr(self, 'bounds_visible', False))
        bounds_act.triggered.connect(self.toggle_bounds)
        tools_menu.addAction(bounds_act)
        
        tools_menu.addAction("📸 相机信息 (Camera Info)", self.show_camera_info)
        tools_menu.addAction("🔄 网格简化 (Simplify Mesh)", self.simplify_mesh)
        
        tools_menu.addSeparator()
        tools_menu.addAction("📊 几何属性 (Properties)", self.calculate_properties)
        tools_menu.addSeparator()
        tools_menu.addAction("📸 截图 (Screenshot)", self.take_screenshot)
        
        # 网格处理子菜单 (New)
        mesh_tools_menu = tools_menu.addMenu("🔧 网格处理 (Mesh Tools)")
        
        pick_act = QAction("👉 点选模式 (Point Picking)", self)
        pick_act.setCheckable(True)
        pick_act.triggered.connect(self.enable_point_picking)
        mesh_tools_menu.addAction(pick_act)
        
        mesh_tools_menu.addAction("✂️ 盒体裁剪 (Box Clip)", self.clip_box)
        mesh_tools_menu.addAction("➗ 网格细分 (Subdivide)", self.subdivide_mesh)
        
        # 高级工具子菜单 (New)
        adv_menu = tools_menu.addMenu("⚙️ 高级 (Advanced)")
        adv_menu.addAction("🖼️ 透明背景截图", self.screenshot_transparent)
        
        nav_menu = adv_menu.addMenu("🎮 导航风格")
        nav_menu.addAction("Trackball (默认)", self.set_trackball_style)
        nav_menu.addAction("Terrain", self.set_terrain_style)
        
        adv_menu.addAction("💾 保存视角", self.save_view)
        adv_menu.addAction("📂 加载视角", self.load_view)
        adv_menu.addAction("🔄 重置所有设置", self.reset_settings)

        # 6. 帮助菜单 (Help)
        help_menu = menubar.addMenu("帮助 (&Help)")
        help_menu.addAction("ℹ️ 关于 (About)", self.show_about)

    def set_theme(self, theme):
        """切换深色/浅色主题"""
        if theme == "dark":
            bg_color = "#242424"
            fg_color = "#d1d1d1"
            hover_bg = "#333333"
            border_color = "#333333"
            if self.plotter: self.plotter.set_background(color="#242424", top="#333333")
        else:
            bg_color = "#f5f5f5"
            fg_color = "#333333"
            hover_bg = "#e0e0e0"
            border_color = "#cccccc"
            if self.plotter: self.plotter.set_background(color="#ffffff", top="#e6e6e6")
        
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {bg_color}; color: {fg_color}; font-family: "Segoe UI", sans-serif; }}
            QToolBar {{ background: {bg_color}; border-bottom: 1px solid {border_color}; spacing: 5px; }}
            QMenuBar {{ background-color: {bg_color}; color: {fg_color}; border-bottom: 1px solid {border_color}; }}
            QMenuBar::item:selected {{ background-color: {hover_bg}; }}
            QMenu {{ background-color: {bg_color}; border: 1px solid {border_color}; color: {fg_color}; }}
            QMenu::item:selected {{ background-color: {hover_bg}; }}
            QPlainTextEdit {{ background-color: {bg_color}; color: {fg_color}; border-top: 1px solid {border_color}; }}
            QProgressBar {{ background-color: {bg_color}; border: none; height: 2px; color: transparent; }}
            QProgressBar::chunk {{ background-color: #10ffaf; }}
            QToolButton {{ background: transparent; border: none; border-radius: 4px; padding: 4px; color: {fg_color}; font-size: 12px; }}
            QToolButton:hover {{ background: {hover_bg}; }}
            QComboBox {{ background-color: {bg_color}; color: {fg_color}; border: 1px solid {border_color}; border-radius: 3px; padding: 2px 5px; min-width: 60px; }}
            QComboBox::drop-down {{ border: none; }}
        """)
        logger.info(f"已切换至 {theme} 主题")

    def calculate_properties(self):
        """计算体积和表面积"""
        if not (self.current_mesh and self.current_mesh.n_points > 0):
            QMessageBox.warning(self, "提示", "请先加载模型")
            return
            
        try:
            vol = self.current_mesh.volume
            area = self.current_mesh.area
            bounds = self.current_mesh.bounds
            center = self.current_mesh.center
            
            msg = (
                f"📊 几何属性统计:\n\n"
                f"体积: {vol:.2f}\n"
                f"表面积: {area:.2f}\n\n"
                f"重心 (Center of Mass):\n"
                f"  X: {center[0]:.2f}, Y: {center[1]:.2f}, Z: {center[2]:.2f}\n\n"
                f"包围盒尺寸:\n"
                f"X: {bounds[1]-bounds[0]:.2f}\n"
                f"Y: {bounds[3]-bounds[2]:.2f}\n"
                f"Z: {bounds[5]-bounds[4]:.2f}\n"
                f"顶点数: {self.current_mesh.n_points}\n"
                f"面数: {self.current_mesh.n_cells}"
            )
            QMessageBox.information(self, "几何属性", msg)
        except Exception as e:
            logger.error(f"计算属性失败: {e}")
            QMessageBox.warning(self, "错误", f"计算失败: {e}")

    def export_file(self):
        """导出模型 (支持 STEP, STL, OBJ, PLY, VTK)"""
        if not (self.current_mesh or self.current_shape):
            QMessageBox.warning(self, "提示", "无可用模型")
            return
            
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "导出模型",
            "model.stp",
            "STEP Files (*.step *.stp);;STL Files (*.stl);;OBJ Files (*.obj);;PLY Files (*.ply);;VTK Files (*.vtk)",
            options=options
        )
        
        if not file_name:
            return
            
        try:
            ext = os.path.splitext(file_name)[1].lower()
            
            # STEP Export
            if ext in ['.step', '.stp']:
                if hasattr(self, 'current_shape') and self.current_shape:
                    writer = STEPControl_Writer()
                    status = writer.Transfer(self.current_shape, STEPControl_AsIs)
                    if status != IFSelect_RetDone:
                        raise Exception("STEP 转换失败")
                    status = writer.Write(file_name)
                    if status != IFSelect_RetDone:
                        raise Exception("STEP 写入失败")
                else:
                    QMessageBox.warning(self, "无法导出", "当前模型为网格数据，无法导出为 STEP 实体格式。\n请尝试导出为 STL 或 OBJ。")
                    return

            # Mesh Export
            elif ext in ['.stl', '.obj', '.ply', '.vtk']:
                if self.current_mesh:
                    self.current_mesh.save(file_name)
                else:
                    raise Exception("网格数据不存在")
            
            logger.info(f"模型已导出至: {file_name}")
            QMessageBox.information(self, "成功", f"导出成功:\n{file_name}")
            
        except Exception as e:
            logger.error(f"导出失败: {e}")
            QMessageBox.critical(self, "错误", f"导出失败: {e}")

    def show_file_info(self):
        """显示文件元数据"""
        if not self.recent_files:
             QMessageBox.information(self, "文件信息", "当前未打开文件")
             return
             
        current_file = self.recent_files[0]
        if not os.path.exists(current_file):
             return
             
        info = os.stat(current_file)
        size_mb = info.st_size / (1024 * 1024)
        created = time.ctime(info.st_ctime)
        modified = time.ctime(info.st_mtime)
        
        msg = (
            f"📂 文件路径: {current_file}\n\n"
            f"📦 大小: {size_mb:.2f} MB\n"
            f"📅 创建时间: {created}\n"
            f"📝 修改时间: {modified}\n"
        )
        
        if self.current_mesh:
            msg += (
                f"\n📊 网格信息:\n"
                f"  - 顶点数: {self.current_mesh.n_points}\n"
                f"  - 面数: {self.current_mesh.n_cells}"
            )
            
        QMessageBox.information(self, "文件元数据", msg)

    def show_about(self):
        QMessageBox.about(self, "关于 Polar Bear", 
            "<h3>Polar Bear 3D Viewer</h3>"
            "<p>基于 PySide6 + PyVista + OCP/PythonOCC</p>"
        )


    def setup_ui(self):
        """初始化 UI 界面"""
        # 1. 顶部菜单栏
        self.setup_menu_bar()
        
        # 2. 顶部工具栏 (全面重构)
        self.setup_top_toolbar()
        
        # 3. 加载设置
        self.load_settings()

    def create_tool_button(self, icon, tooltip, slot=None, checkable=False, shortcut=None, parent_toolbar=None, obj_name=None):
        """创建高级工具按钮 (支持右键参数面板)"""
        btn = RightClickToolButton(self)
        btn.setText(icon)
        btn.setToolTip(tooltip)
        btn.setStatusTip(tooltip) # 状态栏提示
        btn.setCheckable(checkable)
        btn.setAutoRaise(True)
        btn.setFixedSize(45, 45)
        
        # 样式优化：平滑过渡动画
        btn.setStyleSheet("""
            QToolButton {
                border: none;
                border-radius: 4px;
                background-color: transparent;
                font-size: 20px;
            }
            QToolButton:hover {
                background-color: #3d3d3d;
            }
            QToolButton:checked {
                background-color: #505050;
                border: 1px solid #666;
            }
            QToolButton:pressed {
                background-color: #2a2a2a;
            }
        """)
        
        if slot:
            btn.clicked.connect(slot)
            
        if shortcut:
            btn.setShortcut(QKeySequence(shortcut))
            btn.setToolTip(f"{tooltip} ({shortcut})")
            
        if obj_name:
            btn.setObjectName(obj_name)
            btn.setAccessibleName(obj_name)
            
        btn.setAccessibleDescription(tooltip)
            
        # 右键点击事件
        btn.rightClicked.connect(lambda: self.show_tool_params(tooltip))
            
        if parent_toolbar:
            parent_toolbar.addWidget(btn)
            
        return btn

    def enter_independent_mode(self):
        """进入独立 3D 视图模式"""
        if self.is_independent_mode: return
        
        # 1. 保存当前状态
        self.original_geometry = self.saveGeometry()
        self.original_state = self.saveState() # 保存工具栏/Dock状态
        
        # 2. 隐藏 UI 元素
        self.menuBar().hide()
        # 隐藏所有工具栏
        for tb in self.findChildren(QToolBar):
            if tb.isVisible():
                tb.setProperty("was_visible", True)
                tb.hide()
            else:
                tb.setProperty("was_visible", False)
                
        # 隐藏日志区域
        if self.log_container.isVisible():
            self.log_container.setProperty("was_visible", True)
            self.log_container.hide()
        else:
             self.log_container.setProperty("was_visible", False)
             
        # 隐藏进度条
        self.progress_bar.hide()
        
        # 3. 设置窗口属性 (无边框 + 透明)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setWindowOpacity(0.7) # 整体透明度 0.7
        # self.setAttribute(Qt.WA_TranslucentBackground) # 如果需要背景透明
        
        # 4. 显示悬浮按钮
        self.float_rotate_btn.show()
        self.update_float_btn_pos()
        
        self.is_independent_mode = True
        self.show() # 刷新窗口状态
        
        # 提示
        QMessageBox.information(self, "独立模式", "已进入独立 3D 视图模式。\n\n• 按住顶部区域拖动窗口\n• 按 ESC 键退出")

    def exit_independent_mode(self):
        """退出独立 3D 视图模式"""
        if not self.is_independent_mode: return
        
        # 1. 恢复窗口属性
        self.setWindowFlags(Qt.Window)
        self.setWindowOpacity(1.0)
        
        # 2. 恢复 UI 元素
        self.menuBar().show()
        
        for tb in self.findChildren(QToolBar):
            if tb.property("was_visible"):
                tb.show()
                
        if self.log_container.property("was_visible"):
            self.log_container.show()
            
        self.progress_bar.show()
        
        # 3. 隐藏悬浮按钮
        self.float_rotate_btn.hide()
        
        self.is_independent_mode = False
        self.show()
        
        # 4. 恢复几何布局 (可选，如果不想保留独立模式下的移动位置，则恢复)
        # self.restoreGeometry(self.original_geometry) 
        # 用户可能希望保留位置，所以暂时不强制恢复位置，只恢复布局
        # self.restoreState(self.original_state)

    def update_float_btn_pos(self):
        """更新悬浮按钮位置 (右下角)"""
        if self.float_rotate_btn.isVisible():
            m = 20 # 边距
            x = self.central_widget.width() - self.float_rotate_btn.width() - m
            y = self.central_widget.height() - self.float_rotate_btn.height() - m
            self.float_rotate_btn.move(x, y)

    def resizeEvent(self, event):
        """窗口大小改变时触发响应式布局"""
        self.update_responsive_layout()
        self.update_float_btn_pos()
        super().resizeEvent(event)

    def keyPressEvent(self, event):
        """键盘事件监听"""
        if event.key() == Qt.Key_Escape:
            if self.is_independent_mode:
                self.exit_independent_mode()
            elif self.plotter and self.plotter.camera.parallel_projection:
                 # 可以在这里处理其他 ESC 逻辑
                 pass
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        """处理无边框拖拽"""
        if self.is_independent_mode:
            if event.button() == Qt.LeftButton:
                # 顶部 30px 为拖拽区域
                if event.position().y() <= 30:
                    self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """处理拖拽移动"""
        if self.is_independent_mode and self.drag_position:
            if event.buttons() & Qt.LeftButton:
                self.move(event.globalPosition().toPoint() - self.drag_position)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """释放拖拽"""
        self.drag_position = None
        super().mouseReleaseEvent(event)

    def update_responsive_layout(self):
        """根据宽度动态调整工具栏布局 (Breakpoints: 800px, 480px)"""
        width = self.width()
        logger.debug(f"Window width: {width}, adjusting layout...")
        
        # 确保工具栏已初始化
        if not hasattr(self, 'tb_file'): return
            
        # 先移除所有可能的换行 (Break)
        self.removeToolBarBreak(self.tb_file)
        self.removeToolBarBreak(self.tb_view)
        self.removeToolBarBreak(self.tb_render)
        self.removeToolBarBreak(self.tb_tools)
        
        if width < 480:
            # 小于 480px: 三行布局 (File | View / Render / Tools)
            self.insertToolBarBreak(self.tb_view)   # File 后换行
            self.insertToolBarBreak(self.tb_tools)  # Render 后换行
        elif width < 800:
            # 小于 800px: 两行布局 (File + View | Render + Tools)
            self.insertToolBarBreak(self.tb_render) # View 后换行
        else:
            # 大于 800px: 单行布局
            pass

    def setup_top_toolbar(self):
        """构建响应式顶部工具栏 (File, View, Render, Tools)"""
        # 1. 清除旧工具栏
        if hasattr(self, 'main_toolbar'):
            self.removeToolBar(self.main_toolbar)
            del self.main_toolbar
            
        # 清除可能存在的拆分工具栏
        for tb_name in ['tb_file', 'tb_view', 'tb_render', 'tb_tools']:
            if hasattr(self, tb_name):
                tb = getattr(self, tb_name)
                self.removeToolBar(tb)
                delattr(self, tb_name)

        # 2. 创建四个分组工具栏
        # 添加平滑过渡动画 (transition) 到 QToolButton
        style = """
            QToolBar { spacing: 8px; padding: 5px; border-bottom: 1px solid #333; }
            QToolButton { margin: 0 2px; }
            QToolButton:hover { background: #333; }
        """
        
        # (1) 文件与系统 (File)
        self.tb_file = QToolBar("文件", self)
        self.tb_file.setObjectName("TB_File")
        self.tb_file.setStyleSheet(style)
        self.tb_file.setIconSize(QSize(24, 24))
        self.tb_file.setMovable(True)
        self.tb_file.setFloatable(True)
        self.addToolBar(Qt.TopToolBarArea, self.tb_file)
        
        self.create_tool_button("📂", "打开文件", self.open_step, shortcut="Ctrl+O", parent_toolbar=self.tb_file)
        self.create_tool_button("💾", "导出模型", self.export_file, shortcut="Ctrl+E", parent_toolbar=self.tb_file)
        self.create_tool_button("📸", "截图", self.take_screenshot, shortcut="F12", parent_toolbar=self.tb_file)
        
        # (2) 视图控制 (View)
        self.tb_view = QToolBar("视图", self)
        self.tb_view.setObjectName("TB_View")
        self.tb_view.setStyleSheet(style)
        self.tb_view.setIconSize(QSize(24, 24))
        self.tb_view.setMovable(True)
        self.tb_view.setFloatable(True)
        self.addToolBar(Qt.TopToolBarArea, self.tb_view)
        
        # 重置视角 (带菜单)
        reset_btn = self.create_tool_button("🏠", "重置视角", lambda: self.plotter.view_isometric() if self.plotter else None, shortcut="Home", parent_toolbar=self.tb_view)
        reset_menu = QMenu(reset_btn)
        reset_menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: #fff; } QMenu::item:selected { background-color: #444; }")
        reset_menu.addAction("🏠 等轴测 (Iso)", lambda: self.plotter.view_isometric() if self.plotter else None)
        reset_menu.addAction("🖥️ 适应屏幕 (Fit)", lambda: self.plotter.reset_camera() if self.plotter else None)
        reset_menu.addSeparator()
        reset_menu.addAction("⬆️ 顶视图 (Top)", lambda: self.plotter.view_xy() if self.plotter else None)
        reset_menu.addAction("⏺️ 前视图 (Front)", lambda: self.plotter.view_xz() if self.plotter else None)
        reset_menu.addAction("➡️ 右视图 (Right)", lambda: self.plotter.view_yz() if self.plotter else None)
        reset_btn.setMenu(reset_menu)
        reset_btn.setPopupMode(QToolButton.DelayedPopup)

        self.create_tool_button("🖥️", "适应屏幕", lambda: self.plotter.reset_camera() if self.plotter else None, shortcut="R", parent_toolbar=self.tb_view)
        
        # 新增：标准视图直接按钮
        self.create_tool_button("⬆️", "顶视图", lambda: self.plotter.view_xy() if self.plotter else None, parent_toolbar=self.tb_view)
        self.create_tool_button("⏺️", "前视图", lambda: self.plotter.view_xz() if self.plotter else None, parent_toolbar=self.tb_view)
        self.create_tool_button("➡️", "右视图", lambda: self.plotter.view_yz() if self.plotter else None, parent_toolbar=self.tb_view)
        
        # 投影切换
        self.projection_btn = self.create_tool_button("🎥", "切换投影", self.toggle_projection, parent_toolbar=self.tb_view, obj_name="proj_btn")

        self.create_tool_button("📺", "全屏模式", self.toggle_fullscreen, shortcut="F11", parent_toolbar=self.tb_view)
        
        self.create_tool_button("👻", "独立3D视图 (ESC退出)", self.enter_independent_mode, parent_toolbar=self.tb_view)

        # (3) 渲染与显示 (Render)
        self.tb_render = QToolBar("渲染", self)
        self.tb_render.setObjectName("TB_Render")
        self.tb_render.setStyleSheet(style)
        self.tb_render.setIconSize(QSize(24, 24))
        self.tb_render.setMovable(True)
        self.tb_render.setFloatable(True)
        self.addToolBar(Qt.TopToolBarArea, self.tb_render)
        
        self.grid_btn = self.create_tool_button("🕸️", "显示网格", self.toggle_grid, checkable=True, shortcut="G", parent_toolbar=self.tb_render, obj_name="grid_btn")
        self.wireframe_btn = self.create_tool_button("📐", "线框模式", self.toggle_wireframe_mode_btn, checkable=True, shortcut="W", parent_toolbar=self.tb_render, obj_name="wireframe_btn")
        self.light_btn = self.create_tool_button("💡", "灯光/阴影", self.toggle_lights, checkable=True, shortcut="L", parent_toolbar=self.tb_render, obj_name="light_btn")
        self.axes_btn = self.create_tool_button("📏", "显示坐标轴", self.toggle_axes, checkable=True, shortcut="A", parent_toolbar=self.tb_render, obj_name="axes_btn")
        
        # 新增：更多渲染选项
        self.bounds_btn = self.create_tool_button("📦", "显示包围盒", self.toggle_bounds, checkable=True, parent_toolbar=self.tb_render, obj_name="bounds_btn")
        if hasattr(self, 'toggle_floor'):
            self.floor_btn = self.create_tool_button("🧱", "显示地板", self.toggle_floor, checkable=True, parent_toolbar=self.tb_render, obj_name="floor_btn")

        self.create_tool_button("🎨", "设置颜色", self.choose_color, parent_toolbar=self.tb_render)

        # (4) 工具与分析 (Tools)
        self.tb_tools = QToolBar("工具", self)
        self.tb_tools.setObjectName("TB_Tools")
        self.tb_tools.setStyleSheet(style)
        self.tb_tools.setIconSize(QSize(24, 24))
        self.tb_tools.setMovable(True)
        self.tb_tools.setFloatable(True)
        self.addToolBar(Qt.TopToolBarArea, self.tb_tools)
        
        self.measure_btn = self.create_tool_button("📏", "测量工具", self.toggle_measure, checkable=True, shortcut="M", parent_toolbar=self.tb_tools, obj_name="measure_btn")
        self.section_btn = self.create_tool_button("🔪", "剖切工具", self.toggle_section, checkable=True, shortcut="X", parent_toolbar=self.tb_tools, obj_name="section_btn")
        
        # 几何操作
        geo_btn = self.create_tool_button("🔧", "几何操作", None, parent_toolbar=self.tb_tools)
        geo_menu = QMenu(geo_btn)
        geo_menu.setStyleSheet("QMenu { background-color: #2b2b2b; color: #fff; } QMenu::item:selected { background-color: #444; }")
        geo_menu.addAction("📉 网格简化", self.simplify_mesh)
        geo_menu.addAction("➗ 网格细分", self.subdivide_mesh)
        geo_menu.addAction("📦 盒式剖切", self.clip_box)
        geo_btn.setMenu(geo_menu)
        geo_btn.setPopupMode(QToolButton.InstantPopup)

        self.create_tool_button("☝️", "点选模式", self.enable_point_picking, checkable=True, parent_toolbar=self.tb_tools, obj_name="pick_btn")
        
        # 新增：清空日志
        self.create_tool_button("🧹", "清空日志", lambda: self.log_display.clear(), parent_toolbar=self.tb_tools)
        
        self.create_tool_button("ℹ️", "关于", self.show_about, parent_toolbar=self.tb_tools)

        # 占位与退出
        empty = QWidget()
        empty.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.tb_tools.addWidget(empty)
        self.create_tool_button("❌", "退出", self.close, shortcut="Ctrl+Q", parent_toolbar=self.tb_tools)
        
        # 3. 初始化响应式布局
        self.update_responsive_layout()

    def toggle_wireframe_mode_btn(self, checked):
        """工具栏线框模式切换"""
        if checked:
            self.set_wireframe_mode()
        else:
            self.set_shaded_mode()

    def toggle_lights(self, checked):
        """切换灯光/阴影"""
        if not self.plotter: return
        self.toggle_shadows(checked)
        if checked:
             logger.info("已开启阴影与增强光照")
        else:
             logger.info("已关闭阴影")

    def toggle_projection(self):
        """切换投影模式"""
        if not self.plotter: return
        if self.plotter.camera.parallel_projection:
            self.set_perspective_view()
            self.projection_btn.setText("🎥")
            self.projection_btn.setToolTip("切换投影 (当前:透视)")
        else:
            self.set_parallel_view()
            self.projection_btn.setText("📏")
            self.projection_btn.setToolTip("切换投影 (当前:平行)")

    def show_tool_params(self, tool_name):
        """右键显示参数面板"""
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{tool_name} 参数设置")
        layout = QFormLayout(dlg)
        
        if "网格" in tool_name:
            layout.addRow("网格颜色:", QPushButton("选择颜色..."))
            layout.addRow("不透明度:", QSlider(Qt.Horizontal))
        elif "测量" in tool_name:
            layout.addRow("单位:", QComboBox())
            layout.addRow("精度:", QComboBox())
        elif "剖切" in tool_name:
             layout.addRow("剖切轴:", QComboBox())
             layout.addRow("显示剖切面:", QCheckBox("显示"))
        elif "颜色" in tool_name:
            # 颜色设置的高级面板
            opacity_slider = QSlider(Qt.Horizontal)
            opacity_slider.setRange(0, 100)
            opacity_slider.setValue(int(self.current_opacity * 100))
            opacity_slider.valueChanged.connect(self.on_opacity_changed)
            layout.addRow("透明度:", opacity_slider)
            
            gloss_slider = QSlider(Qt.Horizontal)
            gloss_slider.setRange(0, 100)
            gloss_slider.setValue(int(self.current_specular * 100))
            gloss_slider.valueChanged.connect(self.on_glossiness_changed)
            layout.addRow("光泽度:", gloss_slider)
        else:
            layout.addRow(QLabel("暂无高级参数"))
            
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addRow(btns)
        
        dlg.exec_()

    def load_settings(self):
        """加载状态持久化"""
        # 窗口状态
        try:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        except Exception as e:
            logger.warning(f"恢复窗口几何布局失败: {e}")
        
        try:
            state = self.settings.value("windowState")
            if state:
                self.restoreState(state)
        except Exception as e:
            logger.warning(f"恢复窗口状态失败: {e}")
            
        # 工具状态恢复
        if self.settings.value("grid_visible", False, type=bool):
            self.grid_btn.setChecked(True)
            self.toggle_grid(True)
            
        if self.settings.value("wireframe", False, type=bool):
            self.wireframe_btn.setChecked(True)
            self.set_wireframe_mode()
            
        if self.settings.value("shadows", False, type=bool):
            self.light_btn.setChecked(True)
            self.toggle_shadows(True)
            
        if self.settings.value("axes_visible", True, type=bool):
            self.axes_btn.setChecked(True)
            # 默认是开启的，如果 saved 是 False 则关闭
        else:
            self.axes_btn.setChecked(False)
            self.toggle_axes(False)

        # 扩展状态恢复
        if hasattr(self, 'floor_btn'):
            if self.settings.value("floor_visible", False, type=bool):
                self.floor_btn.setChecked(True)
                self.toggle_floor(True)

        if hasattr(self, 'bounds_btn'):
            if self.settings.value("bounds_visible", False, type=bool):
                self.bounds_btn.setChecked(True)
                self.toggle_bounds(True)

    def save_settings(self):
        """保存状态持久化"""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        
        self.settings.setValue("grid_visible", self.grid_btn.isChecked())
        self.settings.setValue("wireframe", self.wireframe_btn.isChecked())
        self.settings.setValue("shadows", self.light_btn.isChecked())
        self.settings.setValue("axes_visible", self.axes_btn.isChecked())
        
        # 扩展状态保存
        if hasattr(self, 'floor_btn'):
            self.settings.setValue("floor_visible", self.floor_btn.isChecked())
        if hasattr(self, 'bounds_btn'):
            self.settings.setValue("bounds_visible", self.bounds_btn.isChecked())
        
        # 保存最近文件
        self.settings.setValue("RecentFiles/fileList", self.recent_files)

    def closeEvent(self, event):
        """退出机制：清理与保存"""
        reply = QMessageBox.question(self, '确认退出', "确定要退出吗？未保存的更改可能会丢失。",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.save_settings()
            
            # 资源释放
            if self.plotter:
                self.plotter.close()
            if hasattr(self, 'viewer') and self.viewer:
                # pythonocc 清理
                pass
                
            event.accept()
        else:
            event.ignore()

    def set_perspective_view(self):
        if self.plotter:
            self.plotter.disable_parallel_projection()
            self.plotter.camera.view_angle = self.current_fov
            self.plotter.render()

    def set_parallel_view(self):
        if self.plotter:
            self.plotter.enable_parallel_projection()
            self.plotter.render()

    def on_fov_changed(self, value):
        self.current_fov = value
        if self.plotter:
            self.plotter.camera.view_angle = self.current_fov
            self.plotter.render()

    def on_opacity_changed(self, value):
        self.current_opacity = value / 100.0
        if self.mesh_actor:
            self.mesh_actor.prop.opacity = self.current_opacity
            self.plotter.render()

    def on_precision_changed(self, text):
        self.current_precision = text
        if self.current_shape:
            logger.info(f"切换精度至: {text}")
            self.load_current_shape()

    def on_glossiness_changed(self, value):
        self.current_specular = value / 100.0
        if self.mesh_actor:
            self.mesh_actor.prop.specular = self.current_specular
            self.plotter.render()

    def show_context_menu(self, pos):
        """模型右键功能菜单"""
        if not self.plotter:
            return
            
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #242424;
                color: #d1d1d1;
                border: 1px solid #444;
            }
            QMenu::item:selected {
                background-color: #333;
            }
        """)
        
        # 常用操作
        fit_act = menu.addAction("🔍 适应屏幕")
        fit_act.triggered.connect(self.plotter.view_isometric)
        
        reset_act = menu.addAction("🔄 重置视角")
        reset_act.triggered.connect(lambda: self.plotter.view_xy())
        
        menu.addSeparator()

        # 工具操作
        # 剖切子菜单
        section_menu = menu.addMenu("🔪 剖切工具")
        
        sec_toggle = section_menu.addAction("启用/关闭")
        sec_toggle.setCheckable(True)
        sec_toggle.setChecked(getattr(self, 'is_sectioning', False))
        sec_toggle.triggered.connect(self.toggle_section)
        
        section_menu.addSeparator()
        section_menu.addAction("❌ X 轴剖切", lambda: self.set_section_axis('x'))
        section_menu.addAction("❌ Y 轴剖切", lambda: self.set_section_axis('y'))
        section_menu.addAction("❌ Z 轴剖切", lambda: self.set_section_axis('z'))
        section_menu.addSeparator()
        section_menu.addAction("🔄 重置剖切", self.reset_section_plane)
            
        measure_act = menu.addAction("📏 测量距离")
        measure_act.setCheckable(True)
        measure_act.setChecked(getattr(self, 'is_measuring', False))
        measure_act.triggered.connect(self.toggle_measure)
        
        menu.addSeparator()
        
        prop_act = menu.addAction("📊 几何属性")
        prop_act.triggered.connect(self.calculate_properties)
        
        del_act = menu.addAction("🗑️ 删除物体")
        del_act.triggered.connect(self.delete_object)
        
        menu.addSeparator()
        
        # 渲染模式快选
        shaded_act = menu.addAction("🌕 着色模式")
        shaded_act.triggered.connect(self.set_shaded_mode)

        edges_mode_act = menu.addAction("🔳 着色+边线")
        edges_mode_act.triggered.connect(self.set_surface_with_edges_mode)
        
        wire_act = menu.addAction("🕸️ 线框模式")
        wire_act.triggered.connect(self.set_wireframe_mode)

        points_act = menu.addAction("☁️ 点云模式")
        points_act.triggered.connect(self.set_points_mode)
        
        ghost_act = menu.addAction("👻 透明模式")
        ghost_act.triggered.connect(self.set_transparent_mode)
        
        menu.addSeparator()
        
        # 截图
        shot_act = menu.addAction("📸 保存截图")
        shot_act.triggered.connect(self.take_screenshot)
        
        menu.exec_(self.plotter.mapToGlobal(pos))

    def on_material_changed(self, index):
        color_val = self.material_combo.itemData(index)
        if color_val:
            self.apply_color(color_val)

    def choose_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.apply_color(color.name())

    def apply_color(self, color_val):
        self.model_color = color_val
        if self.mesh_actor:
            self.mesh_actor.prop.color = color_val
            self.plotter.render()
            logger.info(f"材质颜色已更新: {color_val}")

    def set_shaded_mode(self):
        if self.mesh_actor:
            self.mesh_actor.SetVisibility(True)
            self.mesh_actor.prop.style = 'surface'
            self.mesh_actor.prop.opacity = self.current_opacity
            self.mesh_actor.prop.color = self.model_color
            self.mesh_actor.prop.specular = self.current_specular
            self.mesh_actor.prop.ambient = 0.3 # 恢复至 0.3
            self.mesh_actor.prop.diffuse = 0.8
            self.mesh_actor.prop.show_edges = False 
            if self.edge_actor:
                # 只有在启用显示边线时才显示
                self.edge_actor.SetVisibility(getattr(self, 'show_mesh_edges', False))
                self.edge_actor.prop.color = "#333333" # 使用深色线框
            self.plotter.render()
            logger.info(f"切换至着色模式")

    def set_wireframe_mode(self):
        if self.mesh_actor:
            self.mesh_actor.SetVisibility(False) # 隐藏表面
            if self.edge_actor:
                self.edge_actor.SetVisibility(True) 
                self.edge_actor.prop.color = "#d6d6d6" # 线条颜色改为 #d6d6d6
            self.plotter.render()
            logger.info("切换至工程线框模式 (#d6d6d6)")

    def set_transparent_mode(self):
        if self.mesh_actor:
            self.mesh_actor.SetVisibility(True)
            self.mesh_actor.prop.style = 'surface'
            self.mesh_actor.prop.opacity = 0.04 # 96% 透明度 (0.04 不透明度)
            if hasattr(self, 'opacity_slider'):
                self.opacity_slider.setValue(4)
            self.mesh_actor.prop.show_edges = False
            if self.edge_actor:
                self.edge_actor.SetVisibility(True)
                self.edge_actor.prop.color = "#d6d6d6" # 透明模式也用浅色线
            self.plotter.render()
            logger.info("切换至极高透明模式 (96%)")

    def set_surface_with_edges_mode(self):
        """切换至着色+边线模式"""
        if self.mesh_actor:
            self.mesh_actor.SetVisibility(True)
            self.mesh_actor.prop.style = 'surface'
            self.mesh_actor.prop.show_edges = True
            self.mesh_actor.prop.opacity = self.current_opacity
            if self.edge_actor:
                self.edge_actor.SetVisibility(False)
            self.plotter.render()
            logger.info("切换至着色+边线模式")

    def set_flat_shading_mode(self):
        """切换至平坦着色模式"""
        if self.mesh_actor:
            self.mesh_actor.prop.interpolation = 'flat'
            self.plotter.render()
            logger.info("切换至平坦着色模式")

    def set_smooth_shading_mode(self):
        """切换至平滑着色模式"""
        if self.mesh_actor:
            self.mesh_actor.prop.interpolation = 'phong'
            self.plotter.render()
            logger.info("切换至平滑着色模式")

    def append_log(self, msg):
        self.log_display.appendPlainText(msg)
        self.log_display.moveCursor(QTextCursor.End)

    def open_step(self):
        if not DEPENDENCIES_OK:
            logger.error("依赖未就绪，无法打开文件")
            return
            
        path, _ = QFileDialog.getOpenFileName(
            self, 
            "打开 3D 模型", 
            "", 
            "Supported Files (*.step *.stp *.stl *.obj *.ply *.vtk *.vtp);;STEP Files (*.step *.stp);;STL Files (*.stl);;OBJ Files (*.obj);;All Files (*)"
        )
        if path:
            self.load_step(path)

    def load_step(self, path):
        logger.info(f"正在尝试加载: {path}")
        self.progress_bar.setValue(10)
        
        # 记录到最近文件
        self.save_recent_file(path)
        
        # 检查扩展名
        ext = os.path.splitext(path)[1].lower()
        
        if ext in ['.step', '.stp']:
            if ENGINE_TYPE == "B-Rep (pythonocc)":
                self.load_step_pythonocc(path)
            elif ENGINE_TYPE == "B-Rep (OCP)":
                self.load_step_ocp(path)
            elif ENGINE_TYPE == "Mesh (Preview)":
                self.load_step_mesh(path)
            else:
                self.load_mesh_file(path)
        else:
            self.load_mesh_file(path)
            
        self.progress_bar.setValue(100)
        QTimer.singleShot(1000, lambda: self.progress_bar.setValue(0))

    def load_mesh_file(self, path):
        """加载通用网格文件 (STL, OBJ, PLY, VTK)"""
        try:
            self.current_mesh = pv.read(path)
            self.current_shape = None # 非 STEP 文件无 B-Rep 形状
            
            if self.plotter:
                self.plotter.clear()
                self.mesh_actor = self.plotter.add_mesh(
                    self.current_mesh, 
                    color=self.model_color, 
                    show_edges=False,
                    smooth_shading=True,
                    specular=self.current_specular,
                    diffuse=0.8,
                    ambient=0.3
                )
                self.mesh_actor.prop.opacity = self.current_opacity
                
                # 尝试提取边线
                try:
                    edges = self.current_mesh.extract_feature_edges(
                        boundary_edges=True, 
                        feature_edges=True, 
                        manifold_edges=False
                    )
                    self.edge_actor = self.plotter.add_mesh(edges, color="black", line_width=1)
                    self.edge_actor.SetVisibility(getattr(self, 'show_mesh_edges', False))
                except:
                    self.edge_actor = None

                self.plotter.view_isometric()
                self.plotter.reset_camera()
                # self.update_info_label() # Method not found in context, maybe add it or skip
                logger.info(f"网格文件加载成功: {os.path.basename(path)}")
        except Exception as e:
            logger.error(f"网格加载失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"无法加载文件: {e}") # 1秒后重置

    def load_step_pythonocc(self, path):
        try:
            reader = STEPControl_Reader()
            status = reader.ReadFile(path)
            if status != IFSelect_RetDone:
                logger.error(f"B-Rep 读取错误: 状态码 {status}")
                return
            reader.TransferRoots()
            shape = reader.Shape()
            if self.display:
                self.display.EraseAll()
                self.display.DisplayShape(shape, update=True, color="SILVER")
                self.display.FitAll()
                logger.info("B-Rep (pythonocc) 加载成功")
        except Exception as e:
            logger.error(f"B-Rep 加载异常: {str(e)}")

    def load_step_ocp(self, path):
        """使用 OCP 内核原生加载 STEP，严禁使用网格中转"""
        try:
            reader = STEPControl_Reader()
            status = reader.ReadFile(path)
            if status != IFSelect_RetDone:
                logger.error(f"OCP 读取 STEP 失败")
                return
            
            reader.TransferRoots()
            self.current_shape = reader.Shape() # 核心：将 B-Rep 数据保留在内存中
            
            logger.info("B-Rep 数据模型已导入 (OCP Native)")
            self.load_current_shape()
                
        except Exception as e:
            logger.error(f"OCP 加载过程发生错误: {str(e)}")
            logger.error(traceback.format_exc())

    def load_current_shape(self):
        """重新离散化并加载当前内存中的形状"""
        if not self.current_shape:
            return
            
        try:
            self.progress_bar.setValue(30)
            # 根据精度设置参数
            params = {
                "Low": (0.5, 0.8),
                "Medium": (0.1, 0.5),
                "High": (0.02, 0.1)
            }
            lin_def, ang_def = params.get(self.current_precision, (0.1, 0.5))
            
            self.current_mesh = self._shape_to_pyvista_mesh(self.current_shape, lin_def, ang_def)
            self.progress_bar.setValue(70)
            
            if self.plotter:
                self.plotter.clear()
                self.mesh_actor = self.plotter.add_mesh(
                    self.current_mesh, 
                    color=self.model_color, 
                    show_edges=False,
                    smooth_shading=True,
                    specular=self.current_specular,
                    specular_power=80, 
                    ambient=0.3,       # 恢复至 0.3
                    diffuse=0.8        
                )
                self.mesh_actor.prop.opacity = self.current_opacity
                
                # 提取几何边线 (工程线框)
                edges = self.current_mesh.extract_feature_edges(
                    boundary_edges=True, 
                    feature_edges=True, 
                    manifold_edges=False
                )
                self.edge_actor = self.plotter.add_mesh(edges, color="black", line_width=1)
                
                self.plotter.view_isometric()
                self.plotter.reset_camera()
                self.progress_bar.setValue(90)
                logger.info(f"模型加载成功 (精度: {self.current_precision})")
        except Exception as e:
            logger.error(f"模型离散化失败: {str(e)}")
            self.progress_bar.setValue(0)

    def _shape_to_pyvista_mesh(self, shape, linear_deflection=0.1, angular_deflection=0.5):
        """将 TopoDS_Shape 转换为 PyVista 网格（内存中执行）"""
        from OCP.TopLoc import TopLoc_Location
        
        # 1. 触发 OCC 原生三角化算法 (B-Rep 离散化)
        BRepMesh_IncrementalMesh(shape, linear_deflection, False, angular_deflection, True)
        
        vertices = []
        triangles = []
        
        # 2. 遍历拓扑面并提取三角化数据
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            shape_face = explorer.Current()
            # 关键修复：OCP 需要将 TopoDS_Shape 显式转换为 TopoDS_Face
            face = TopoDS.Face_s(shape_face)
            
            location = TopLoc_Location()
            triangulation = BRep_Tool.Triangulation_s(face, location)
            
            if triangulation:
                nb_nodes = triangulation.NbNodes()
                nb_triangles = triangulation.NbTriangles()
                transform = location.Transformation()
                
                # 记录当前顶点偏移量
                offset = len(vertices)
                
                # 提取顶点坐标并应用位置变换
                for i in range(1, nb_nodes + 1):
                    pnt = triangulation.Node(i)
                    pnt.Transform(transform)
                    vertices.append([pnt.X(), pnt.Y(), pnt.Z()])
                
                # 提取三角索引
                for i in range(1, nb_triangles + 1):
                    tri = triangulation.Triangle(i)
                    # Get() 返回 3 个索引 (1-based)
                    idx1, idx2, idx3 = tri.Get()
                    # VTK 格式：[3, i1, i2, i3] (转换为 0-based 并加上偏移)
                    triangles.append([3, idx1 + offset - 1, 
                                        idx2 + offset - 1, 
                                        idx3 + offset - 1])
            
            explorer.Next()
        
        # 3. 构建 PyVista 对象
        v_array = np.array(vertices)
        f_array = np.array(triangles).flatten()
        return pv.PolyData(v_array, f_array)

    def load_step_mesh(self, path):
        try:
            import gmsh
            import tempfile
            import pyvista as pv
            gmsh.initialize()
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.model.add("STEP_Model")
            gmsh.model.occ.importShapes(path)
            gmsh.model.occ.synchronize()
            gmsh.model.mesh.generate(2)
            with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
                tmp_path = tmp.name
            gmsh.write(tmp_path)
            gmsh.finalize()
            self.current_mesh = pv.read(tmp_path)
            os.remove(tmp_path)
            if self.plotter:
                self.plotter.clear()
                self.mesh_actor = self.plotter.add_mesh(
                    self.current_mesh, 
                    color="silver", 
                    show_edges=False,
                    smooth_shading=True,
                    specular=0.5,
                    ambient=0.3
                )
                edges = self.current_mesh.extract_feature_edges(
                    boundary_edges=True, 
                    feature_edges=True, 
                    manifold_edges=False
                )
                self.plotter.add_mesh(edges, color="black", line_width=1)
                self.plotter.view_isometric()
                self.plotter.reset_camera()
                logger.info("模型加载成功")
        except Exception as e:
             logger.error(f"加载异常: {str(e)}")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = url.toLocalFile().lower()
                if p.endswith(".step") or p.endswith(".stp"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = url.toLocalFile()
                if p.lower().endswith(".step") or p.lower().endswith(".stp"):
                    self.load_step(p)
                    break

    def create_slider_action(self, parent_menu, label, min_v, max_v, init_v, slot):
        """创建带滑块的菜单项"""
        wa = QWidgetAction(parent_menu)
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(15, 5, 15, 5)
        l.setSpacing(10)
        
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #d1d1d1; border: none; min-width: 40px;")
        
        sld = QSlider(Qt.Horizontal)
        sld.setRange(min_v, max_v)
        sld.setValue(init_v)
        sld.setFixedWidth(120)
        sld.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #444; height: 4px; background: #1e1e1e; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #888; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px;
            }
            QSlider::handle:horizontal:hover { background: #10ffaf; }
        """)
        sld.valueChanged.connect(slot)
        
        l.addWidget(lbl)
        l.addWidget(sld)
        wa.setDefaultWidget(w)
        return wa

    def toggle_axes(self):
        """切换坐标轴显示"""
        if self.plotter:
            if getattr(self, 'axes_visible', True):
                self.plotter.hide_axes()
                self.axes_visible = False
            else:
                self.plotter.show_axes()
                self.axes_visible = True

    def toggle_bounds(self):
        """切换包围盒显示"""
        if self.plotter and hasattr(self, 'current_mesh'):
            if getattr(self, 'bounds_visible', False):
                self.plotter.remove_bounds_axes()
                self.bounds_visible = False
            else:
                self.plotter.show_bounds(color='white')
                self.bounds_visible = True

    def setup_settings_menu(self):
        """配置底部设置按钮的完整功能菜单"""
        m = self.settings_menu
        m.clear()
        
        # --- 1. 文件与视图 ---
        view_menu = m.addMenu("📁 文件与视图")
        
        open_act = view_menu.addAction("📂 打开文件")
        open_act.triggered.connect(self.open_step)
        
        view_menu.addSeparator()

        view_menu.addAction("📐 坐标轴开关", self.toggle_axes)
        view_menu.addAction("📦 包围盒开关", self.toggle_bounds)
        view_menu.addSeparator()
        
        view_menu.addAction("🏠 等轴测视图", lambda: self.plotter and self.plotter.view_isometric())
        
        # 标准视图子菜单
        std_views = view_menu.addMenu("👁️ 标准视图")
        std_views.addAction("前视图 (Front)", lambda: self.plotter and self.plotter.view_xz())
        std_views.addAction("后视图 (Back)", lambda: self.plotter and self.plotter.view_xz(negative=True))
        std_views.addAction("顶视图 (Top)", lambda: self.plotter and self.plotter.view_xy())
        std_views.addAction("底视图 (Bottom)", lambda: self.plotter and self.plotter.view_xy(negative=True))
        std_views.addAction("左视图 (Left)", lambda: self.plotter and self.plotter.view_yz())
        std_views.addAction("右视图 (Right)", lambda: self.plotter and self.plotter.view_yz(negative=True))
        
        view_menu.addSeparator()
        # 视角滑块
        view_menu.addAction(self.create_slider_action(view_menu, "视角", 10, 150, self.current_fov, self.on_fov_changed))
        
        # --- 2. 显示模式 ---
        display_menu = m.addMenu("🎨 显示模式")
        
        display_menu.addAction("🌕 着色模式", self.set_shaded_mode)
        display_menu.addAction("🕸️ 线框模式", self.set_wireframe_mode)
        display_menu.addAction("👻 透明模式", self.set_transparent_mode)
        
        display_menu.addSeparator()
        # 透明度滑块
        display_menu.addAction(self.create_slider_action(display_menu, "透明", 0, 100, int(self.current_opacity * 100), self.on_opacity_changed))
        
        # --- 3. 材质与渲染 ---
        mat_menu = m.addMenu("💎 材质与渲染")
        
        mat_menu.addAction("🎨 自定义颜色...", self.choose_color)
        
        # 材质预设子菜单
        presets_menu = mat_menu.addMenu("🗿 材质预设")
        materials = [
            ("⚪ 默认白", "#e6e6e6"), ("🔴 磨砂红", "#ff4d4d"), ("🔵 天空蓝", "#4d94ff"),
            ("🟢 草地绿", "#4dff88"), ("⚠️ 警示黄", "#ffd700"), ("⚫ 深空灰", "#333333"),
            ("🟠 活力橙", "#ffa500"), ("🟣 罗兰紫", "#9370db"), ("🟤 青铜色", "#cd7f32"),
            ("🪙 土豪金", "#ffd700"),
        ]
        
        def make_mat_setter(c):
            return lambda: self.apply_color(c)
            
        for name, color_val in materials:
            presets_menu.addAction(name, make_mat_setter(color_val))
            
        mat_menu.addSeparator()
        # 光泽度滑块
        mat_menu.addAction(self.create_slider_action(mat_menu, "光泽", 0, 100, int(self.current_specular * 100), self.on_glossiness_changed))

        # 精度设置
        mat_menu.addSeparator()
        prec_menu = mat_menu.addMenu("📏 网格精度")
        
        def make_prec_setter(p):
            return lambda: self.on_precision_changed(p)

        prec_menu.addAction("低 (Low)", make_prec_setter("Low"))
        prec_menu.addAction("中 (Medium)", make_prec_setter("Medium"))
        prec_menu.addAction("高 (High)", make_prec_setter("High"))
        
        # --- 4. 系统功能 ---
        m.addSeparator()
        sys_menu = m.addMenu("⚙️ 系统功能")
        sys_menu.addAction("🧹 清空日志", self.log_display.clear)
        sys_menu.addAction("🖥️ 适应屏幕", lambda: self.plotter and self.plotter.reset_camera())

def main():
    app = QApplication(sys.argv)
    try:
        w = MainWindow()
        w.show()
        sys.exit(app.exec())
    except Exception as e:
        if 'logger' in globals():
            logger.fatal(f"程序崩溃: {str(e)}")
            logger.fatal(traceback.format_exc())
        else:
            print(f"Fatal: {str(e)}")

if __name__ == "__main__":
    main()

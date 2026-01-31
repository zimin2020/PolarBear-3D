
import os
import re

file_path = r'e:\程序\TRAE\4\main.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Define new setup_top_toolbar content
new_toolbar_code = '''    def setup_top_toolbar(self):
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
        
        # 占位与退出
        empty = QWidget()
        empty.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.tb_tools.addWidget(empty)
        self.create_tool_button("❌", "退出", self.close, shortcut="Ctrl+Q", parent_toolbar=self.tb_tools)
        
        # 3. 初始化响应式布局
        self.update_responsive_layout()'''

# Replace setup_top_toolbar
# Regex to match def setup_top_toolbar(self): until the next def or end of file
# Assuming indentation is 4 spaces.
# We match from `def setup_top_toolbar` until `    def toggle_wireframe_mode_btn` (the next function)
pattern = re.compile(r'    def setup_top_toolbar\(self\):.*?    def toggle_wireframe_mode_btn', re.DOTALL)
match = pattern.search(content)

if match:
    new_content = content[:match.start()] + new_toolbar_code + '\n\n' + content[match.end():]
    
    # Also remove setup_ui_deprecated
    pattern_deprecated = re.compile(r'    def setup_ui_deprecated\(self\):.*?    def set_perspective_view', re.DOTALL)
    match_deprecated = pattern_deprecated.search(new_content)
    if match_deprecated:
        # Keep set_perspective_view but remove the deprecated function
        # The match includes set_perspective_view start, so we need to be careful
        # Let's just replace the deprecated function body.
        # Simpler: regex replace setup_ui_deprecated until set_perspective_view
        new_content = re.sub(r'    def setup_ui_deprecated\(self\):.*?    def set_perspective_view', '    def set_perspective_view', new_content, flags=re.DOTALL)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully updated main.py")
else:
    print("Could not find setup_top_toolbar function")

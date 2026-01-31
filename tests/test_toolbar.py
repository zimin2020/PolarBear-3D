
import sys
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QSize
from main import MainWindow

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

class TestToolbar(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow()
        self.window.show()

    def tearDown(self):
        self.window.close()

    def test_toolbar_creation(self):
        """Test if toolbars are created correctly"""
        self.assertTrue(hasattr(self.window, 'tb_file'))
        self.assertTrue(hasattr(self.window, 'tb_view'))
        self.assertTrue(hasattr(self.window, 'tb_render'))
        self.assertTrue(hasattr(self.window, 'tb_tools'))
        
        self.assertTrue(self.window.tb_file.isVisible())
        self.assertTrue(self.window.tb_view.isVisible())

    def test_toolbar_actions(self):
        """Test if key actions exist in toolbars"""
        # File toolbar
        actions_file = self.window.tb_file.actions()
        self.assertTrue(len(actions_file) >= 3) # Open, Export, Screenshot
        
        # View toolbar
        actions_view = self.window.tb_view.actions()
        # Reset, Fit, Top, Front, Right, Proj, Fullscreen -> at least 7
        self.assertTrue(len(actions_view) >= 7)
        
        # Render toolbar
        actions_render = self.window.tb_render.actions()
        # Grid, Wireframe, Light, Axes, Bounds, Floor, Color -> at least 7
        self.assertTrue(len(actions_render) >= 7)

    def test_responsive_layout_logic(self):
        """Test responsive layout breakpoints logic"""
        # Test < 480px logic
        self.window.resize(400, 600)
        self.window.update_responsive_layout()
        # We can't easily check 'insertToolBarBreak' effect via public API directly without checking internal state
        # But we can check if it runs without error
        
        # Test < 800px logic
        self.window.resize(700, 600)
        self.window.update_responsive_layout()
        
        # Test > 800px logic
        self.window.resize(1000, 600)
        self.window.update_responsive_layout()

    def test_tool_state_persistence(self):
        """Test if tool states are saved/loaded"""
        # Simulate changing a setting
        self.window.grid_btn.setChecked(True)
        self.window.save_settings()
        
        # Create new window to test load
        new_window = MainWindow()
        # settings are shared via QSettings organization/app name
        new_window.load_settings()
        self.assertTrue(new_window.grid_btn.isChecked())
        new_window.close()

if __name__ == '__main__':
    unittest.main()

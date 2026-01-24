import sys
import os
from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtCore import Qt
from gui.dialogs import AspectRatioDialog
from gui.main_window import MainWindow
from gui.theme import SettingsStore, apply_theme

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # Set application name
    app.setApplicationName("VideoForge")
    app.setOrganizationName("VideoForge")

    # Theme (persisted)
    store = SettingsStore(settings_path=os.path.join(os.getcwd(), "settings.json"))
    settings = store.load()
    apply_theme(app, settings.theme)
    
    # 1. Aspect Ratio Dialog
    dialog = AspectRatioDialog()
    if dialog.exec_() == QDialog.Accepted:
        selected_ratio = dialog.get_selected_ratio()
        
        # 2. Main Window
        window = MainWindow(selected_ratio, settings_store=store, initial_theme=settings.theme)
        window.show()
        
        sys.exit(app.exec_())
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()

import sys
from PyQt5.QtWidgets import QApplication, QDialog
from gui.dialogs import AspectRatioDialog
from gui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion') # Modern look
    
    # 1. Aspect Ratio Dialog
    dialog = AspectRatioDialog()
    if dialog.exec_() == QDialog.Accepted:
        selected_ratio = dialog.get_selected_ratio()
        
        # 2. Main Window
        window = MainWindow(selected_ratio)
        window.show()
        
        sys.exit(app.exec_())
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()

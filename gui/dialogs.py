from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QButtonGroup, 
                             QRadioButton, QPushButton)

class AspectRatioDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Select Video Size")
        self.setFixedSize(300, 200)
        
        layout = QVBoxLayout()
        
        label = QLabel("Choose the aspect ratio for your video:")
        layout.addWidget(label)
        
        self.ratio_group = QButtonGroup(self)
        
        self.rb_reel = QRadioButton("Reel (9:16)")
        self.rb_youtube = QRadioButton("YouTube (16:9)")
        self.rb_square = QRadioButton("Square (1:1)")
        
        self.rb_reel.setChecked(True) # Default
        
        layout.addWidget(self.rb_reel)
        layout.addWidget(self.rb_youtube)
        layout.addWidget(self.rb_square)
        
        self.ratio_group.addButton(self.rb_reel)
        self.ratio_group.addButton(self.rb_youtube)
        self.ratio_group.addButton(self.rb_square)
        
        btn_confirm = QPushButton("Confirm")
        btn_confirm.clicked.connect(self.accept)
        layout.addWidget(btn_confirm)
        
        self.setLayout(layout)
        
    def get_selected_ratio(self):
        if self.rb_reel.isChecked():
            return "Reel (9:16)"
        elif self.rb_youtube.isChecked():
            return "YouTube (16:9)"
        else:
            return "Square (1:1)"

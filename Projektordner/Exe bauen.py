from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile
f = QFile("ui/mainwindow.ui"); f.open(QFile.ReadOnly)
window = QUiLoader().load(f); f.close()
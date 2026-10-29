from PyQt6 import uic
from PyQt6.QtWidgets import QDialog

from config import DELETE_COMMENT_DIALOG_UI

class DeleteCommentDialog(QDialog):
    def __init__(self, text: str = "", window_title: str = "Подтверждение удаления", parent=None):
        super().__init__(parent)

        uic.loadUi(DELETE_COMMENT_DIALOG_UI, self)

        self.setWindowTitle(window_title)

        self.DeleteCommentButton.clicked.connect(self.accept)
        self.DiscardDeleteButton.clicked.connect(self.reject)
from PyQt6 import uic
from PyQt6.QtWidgets import QDialog

from config import COMMENT_DIALOG_UI

class CommentDialog(QDialog):
    def __init__(self, text: str = "", window_title: str = "Комментарий", parent=None):
        super().__init__(parent)

        uic.loadUi(COMMENT_DIALOG_UI, self)

        self.CommentText.setPlainText(text)
        self.setWindowTitle(window_title)

        self.SaveCommentButton.clicked.connect(self.accept)
        self.DiscardChangesButton.clicked.connect(self.reject)

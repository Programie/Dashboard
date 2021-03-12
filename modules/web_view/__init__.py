from PyQt5 import QtWebEngineWidgets, QtCore

from lib.common import AbstractView


class View(QtWebEngineWidgets.QWebEngineView, AbstractView):
    def __init__(self, url, js=None, css=None):
        super().__init__()

        self.js = js
        self.css = css

        self.loadFinished.connect(self.loaded)
        self.load(QtCore.QUrl(url))

    def loaded(self):
        if self.js is not None:
            self.page().runJavaScript(self.js)

        if self.css is not None:
            js = """
                (function() {
                    css = document.createElement("style");
                    css.type = "text/css";
                    document.head.appendChild(css);
                    css.innerText = "{INJECT}";
                })();
            """

            js = js.replace("{INJECT}", self.css)

            self.page().runJavaScript(js)

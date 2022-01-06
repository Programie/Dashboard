import webbrowser

from PyQt5 import QtWebEngineWidgets, QtCore

from lib.common import AbstractView


class WebPage(QtWebEngineWidgets.QWebEnginePage):
    def __init__(self, parent, open_links_in_default_browser: bool):
        super().__init__(parent)

        self.open_links_in_default_browser = open_links_in_default_browser

    def acceptNavigationRequest(self, url: QtCore.QUrl, navigation_type: QtWebEngineWidgets.QWebEnginePage.NavigationType, is_main_frame: bool):
        if navigation_type == QtWebEngineWidgets.QWebEnginePage.NavigationTypeLinkClicked and self.open_links_in_default_browser:
            webbrowser.open(url.toString())
            return False

        return True


class View(QtWebEngineWidgets.QWebEngineView, AbstractView):
    def __init__(self, url, js=None, css=None, open_links_in_default_browser=False):
        super().__init__()

        self.js = js
        self.css = css

        self.setPage(WebPage(self, open_links_in_default_browser))

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

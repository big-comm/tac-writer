"""
TAC UI Package
User interface components for the TAC application using GTK4 and libadwaita
"""

from .main_window import MainWindow
from .components import (
    ParagraphEditor,
    TextEditor,
    ProjectListWidget,
    WelcomeView
)
from .dialogs import (
    NewProjectDialog,
    ExportDialog,
    PreferencesDialog,
    AboutDialog
)

__all__ = [
    # Main window
    'MainWindow',
    
    # Components
    'ParagraphEditor',
    'TextEditor', 
    'ProjectListWidget',
    'WelcomeView',
    
    # Dialogs
    'NewProjectDialog',
    'ExportDialog', 
    'PreferencesDialog',
    'AboutDialog'
]

__version__ = '1.0.0'

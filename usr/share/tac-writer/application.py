"""
TAC Application Class
Main application controller using GTK4 and libadwaita
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio, Gdk
from core.config import Config
from core.services import ProjectManager
from ui.main_window import MainWindow
from utils.i18n import _

# Try to load PyGTKSpellcheck
try:
    import gtkspellcheck
    SPELL_CHECK_AVAILABLE = True
    print("PyGTKSpellcheck available - spell checking enabled")
except ImportError:
    SPELL_CHECK_AVAILABLE = False
    print("PyGTKSpellcheck not available - spell checking disabled")

class TacApplication(Adw.Application):
    """Main TAC application class"""

    def __init__(self):
        super().__init__(
            application_id='com.github.tac',
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )

        # Application components
        self.config = Config()
        self.project_manager = ProjectManager()
        self.main_window = None

        # Check spell checking availability
        self._check_spell_dependencies()

        # Connect signals
        self.connect('activate', self._on_activate)
        self.connect('startup', self._on_startup)
        
        print("TacApplication initialized")

    def _check_spell_dependencies(self):
        """Check and configure spell checking dependencies"""
        if SPELL_CHECK_AVAILABLE:
            try:
                # Test if enchant backend is working
                import enchant
                # Check for available dictionaries
                available_dicts = []
                for lang in ['pt_BR', 'en_US', 'es_ES', 'fr_FR', 'de_DE', 'it_IT']:
                    try:
                        if enchant.dict_exists(lang):
                            available_dicts.append(lang)
                    except:
                        pass

                if available_dicts:
                    print(f"Available spell check dictionaries: {available_dicts}")
                    # Update config with actually available languages
                    self.config.set('spell_check_available_languages', available_dicts)
                    
                    # Set default language to first available if current isn't available
                    current_lang = self.config.get_spell_check_language()
                    if current_lang not in available_dicts:
                        self.config.set_spell_check_language(available_dicts[0])
                        print(f"Default spell check language set to: {available_dicts[0]}")
                else:
                    print("No spell check dictionaries found - disabling spell checking")
                    self.config.set_spell_check_enabled(False)

            except ImportError:
                print("Enchant backend not available - disabling spell checking")
                self.config.set_spell_check_enabled(False)
        else:
            print("PyGTKSpellcheck not installed - disabling spell checking")
            self.config.set_spell_check_enabled(False)

    def _on_startup(self, app):
        """Called when application starts"""
        print("Application startup...")
        
        # Setup application actions
        self._setup_actions()
        
        # Setup application menu and shortcuts
        self._setup_menu()
        
        # Apply application theme
        self._setup_theme()

    def _on_activate(self, app):
        """Called when application is activated"""
        print("Application activate...")
        
        try:
            if not self.main_window:
                self.main_window = MainWindow(
                    application=self,
                    project_manager=self.project_manager,
                    config=self.config
                )
                print("Main window created")
            
            self.main_window.present()
            print("Main window presented")
            
        except Exception as e:
            print(f"Error activating application: {e}")
            import traceback
            traceback.print_exc()
            self.quit()

    def _setup_actions(self):
        """Setup application-wide actions"""
        actions = [
            ('new_project', self._action_new_project),
            ('open_project', self._action_open_project),
            ('save_project', self._action_save_project),
            ('export_project', self._action_export_project),
            ('preferences', self._action_preferences),
            ('about', self._action_about),
            ('quit', self._action_quit),
            # NOVO: Adicionadas ações globais de undo/redo (opcional)
            ('undo', self._action_global_undo),
            ('redo', self._action_global_redo),
        ]

        for action_name, callback in actions:
            action = Gio.SimpleAction.new(action_name, None)
            action.connect('activate', callback)
            self.add_action(action)

        print("Application actions setup complete")

    def _setup_menu(self):
        """Setup application menu and keyboard shortcuts"""
        # Keyboard shortcuts
        shortcuts = [
            ('<Ctrl>n', 'app.new_project'),
            ('<Ctrl>o', 'app.open_project'),
            ('<Ctrl>s', 'app.save_project'),
            ('<Ctrl>e', 'app.export_project'),
            ('<Ctrl>comma', 'app.preferences'),
            ('<Ctrl>q', 'app.quit'),
            # NOVO: Atalhos globais de undo/redo (backup se os atalhos da janela falharem)
            ('<Ctrl>z', 'app.undo'),
            ('<Ctrl><Shift>z', 'app.redo'),
        ]

        for accelerator, action in shortcuts:
            self.set_accels_for_action(action, [accelerator])

        print("Application menu and shortcuts setup complete")

    def _setup_theme(self):
        """Setup application theme"""
        style_manager = Adw.StyleManager.get_default()
        
        # Apply theme preference
        if self.config.get('use_dark_theme', False):
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

        # Load custom CSS for drag and drop and spell checking
        css_provider = Gtk.CssProvider()
        css_data = '''
        .card.draggable-hover {
            background: alpha(@accent_color, 0.05);
            border: 1px solid alpha(@accent_color, 0.3);
            transition: all 200ms ease;
        }

        .card.dragging {
            opacity: 0.6;
            transform: scale(0.98);
            transition: all 150ms ease;
        }

        .card.drop-target {
            background: alpha(@accent_color, 0.1);
            border: 2px solid @accent_color;
            transition: all 200ms ease;
        }

        /* Spell check styles */
        .spell-error {
            text-decoration: underline;
            text-decoration-color: red;
            text-decoration-style: wavy;
        }

        /* NOVO: Estilos para undo/redo feedback */
        .undo-feedback {
            background: alpha(@success_color, 0.1);
            border: 1px solid alpha(@success_color, 0.3);
            transition: all 300ms ease;
        }

        .redo-feedback {
            background: alpha(@warning_color, 0.1);
            border: 1px solid alpha(@warning_color, 0.3);
            transition: all 300ms ease;
        }
        '''

        css_provider.load_from_data(css_data.encode())

        # Apply CSS safely
        try:
            display = Gdk.Display.get_default()
            if display:
                Gtk.StyleContext.add_provider_for_display(
                    display,
                    css_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
        except Exception as e:
            print(f"Could not apply CSS: {e}")

        print("Application theme setup complete")

    # NOVOS MÉTODOS: Ações globais de undo/redo
    def _action_global_undo(self, action, param):
        """Handle global undo action (backup method)"""
        print("Debug: Global app-level undo action triggered")
        
        # Delegar para a janela principal se disponível
        if self.main_window and hasattr(self.main_window, '_action_undo'):
            # Criar um parâmetro vazio para manter compatibilidade
            dummy_action = Gio.SimpleAction.new("undo", None)
            self.main_window._action_undo(dummy_action, None)
        else:
            print("Debug: No main window available for global undo")

    def _action_global_redo(self, action, param):
        """Handle global redo action (backup method)"""
        print("Debug: Global app-level redo action triggered")
        
        # Delegar para a janela principal se disponível
        if self.main_window and hasattr(self.main_window, '_action_redo'):
            # Criar um parâmetro vazio para manter compatibilidade
            dummy_action = Gio.SimpleAction.new("redo", None)
            self.main_window._action_redo(dummy_action, None)
        else:
            print("Debug: No main window available for global redo")

    # Ações existentes
    def _action_new_project(self, action, param):
        """Handle new project action"""
        if self.main_window:
            self.main_window.show_new_project_dialog()

    def _action_open_project(self, action, param):
        """Handle open project action"""
        if self.main_window:
            self.main_window.show_open_project_dialog()

    def _action_save_project(self, action, param):
        """Handle save project action"""
        if self.main_window:
            self.main_window.save_current_project()

    def _action_export_project(self, action, param):
        """Handle export project action"""
        if self.main_window:
            self.main_window.show_export_dialog()

    def _action_preferences(self, action, param):
        """Handle preferences action"""
        if self.main_window:
            self.main_window.show_preferences_dialog()

    def _action_about(self, action, param):
        """Handle about action"""
        if self.main_window:
            self.main_window.show_about_dialog()

    def _action_quit(self, action, param):
        """Handle quit action"""
        self.quit()

    def do_shutdown(self):
        """Called when application shuts down"""
        print("Application shutdown...")
        
        # Save configuration
        if self.config:
            self.config.save()
            print("Configuration saved")

        # Call parent shutdown
        Adw.Application.do_shutdown(self)
        print("Application shutdown complete")

    # NOVOS MÉTODOS: Utilitários para debug
    def debug_spell_config(self):
        """Debug method to print spell check configuration"""
        if self.config:
            self.config.debug_spell_config()
        else:
            print("No config available for spell check debug")

    def get_main_window(self):
        """Get reference to main window"""
        return self.main_window

    def is_spell_check_available(self):
        """Check if spell checking is available"""
        return SPELL_CHECK_AVAILABLE and self.config.get_spell_check_enabled()

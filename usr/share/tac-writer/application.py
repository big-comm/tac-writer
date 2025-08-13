"""
TAC Application Class

Main application controller using GTK4 and libadwaita
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio, Gdk, GLib
from core.config import Config
from core.services import ProjectManager
from ui.main_window import MainWindow
from utils.i18n import _

import locale
import os
import gettext

# Try to load PyGTKSpellcheck
try:
    import gtkspellcheck
    SPELL_CHECK_AVAILABLE = True
    print("PyGTKSpellcheck available - spell checking enabled")
except ImportError:
    SPELL_CHECK_AVAILABLE = False
    print("PyGTKSpellcheck not available - spell checking disabled")


def setup_system_localization():
    """
    Configura localização automática baseada no locale do sistema
    para PyGTKSpellcheck e traduções do GTK
    """
    
    # Mapeamento dos idiomas disponíveis no spellchecker
    SPELLCHECK_LANGUAGES = ['pt_BR', 'en_US', 'en_GB', 'es_ES', 'fr_FR', 'de_DE', 'it_IT']
    FALLBACK_LANGUAGE = 'en_GB'
    
    def detect_system_locale():
        """Detecta o locale do sistema usando múltiplas fontes"""
        
        # Método 1: Variáveis de ambiente (ordem de prioridade do gettext)
        for env_var in ['LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG']:
            locale_str = os.environ.get(env_var, '').strip()
            if locale_str:
                # Extrair o primeiro idioma da lista (formato: pt_BR:pt:en)
                first_locale = locale_str.split(':')[0]
                if first_locale:
                    return first_locale
        
        # Método 2: locale.getdefaultlocale()
        try:
            default_locale, _ = locale.getdefaultlocale()
            if default_locale:
                return default_locale
        except Exception:
            pass
        
        # Método 3: locale.setlocale com string vazia (user's default)
        try:
            current_locale = locale.setlocale(locale.LC_MESSAGES, '')
            if current_locale and current_locale != 'C':
                return current_locale
        except Exception:
            pass
        
        return None
    
    def map_locale_to_spellcheck_language(detected_locale):
        """Mapeia locale do sistema para idioma disponível no spellchecker"""
        
        if not detected_locale:
            return FALLBACK_LANGUAGE
        
        # Normalizar formato: pt-BR -> pt_BR, pt.utf8 -> pt
        normalized = detected_locale.replace('-', '_').split('.')[0]
        
        # Verificação direta
        if normalized in SPELLCHECK_LANGUAGES:
            return normalized
        
        # Mapeamento por código de idioma (primeiros dois caracteres)
        language_code = normalized.split('_')[0].lower()
        
        language_mapping = {
            'pt': 'pt_BR',     # Português -> Português Brasileiro
            'en': 'en_GB',     # Inglês -> Inglês Britânico (fallback especificado)
            'es': 'es_ES',     # Espanhol -> Espanhol da Espanha
            'fr': 'fr_FR',     # Francês -> Francês da França
            'de': 'de_DE',     # Alemão -> Alemão da Alemanha
            'it': 'it_IT',     # Italiano -> Italiano da Itália
        }
        
        mapped_language = language_mapping.get(language_code, FALLBACK_LANGUAGE)
        
        print(f"DEBUG: Mapeamento de locale - '{detected_locale}' -> '{language_code}' -> '{mapped_language}'")
        return mapped_language
    
    # Detectar locale do sistema
    system_locale = detect_system_locale()
    target_language = map_locale_to_spellcheck_language(system_locale)
    
    print(f"DEBUG: Locale detectado: {system_locale}")
    print(f"DEBUG: Idioma mapeado para spellchecker: {target_language}")
    
    # Configurar locale do sistema
    try:
        # Configurar locale usando a detecção automática
        locale.setlocale(locale.LC_ALL, '')
        print(f"DEBUG: Locale configurado automaticamente")
    except locale.Error as e:
        print(f"DEBUG: Falha ao configurar locale automaticamente: {e}")
        # Fallback para C locale
        try:
            locale.setlocale(locale.LC_ALL, 'C.UTF-8')
        except locale.Error:
            locale.setlocale(locale.LC_ALL, 'C')
    
    # Configurar variáveis de ambiente para traduções do GTK/GSpell
    detected_language = target_language.split('_')[0]  # pt_BR -> pt
    detected_country = target_language  # manter formato completo
    
    os.environ['LANGUAGE'] = f"{detected_country}:{detected_language}:en"
    os.environ['LC_MESSAGES'] = f"{detected_country}.UTF-8"
    
    # Configurar gettext para bibliotecas do sistema (incluindo PyGTKSpellcheck)
    try:
        # Configurar domínios de tradução conhecidos
        domains_to_configure = [
            'gedit',        # Editor Gedit
            'gspell-1',     # GSpell (biblioteca de spell checking)
            'gtkspell',     # GTKSpell alternativo
            'gtk30',        # GTK 3.0
            'gtk40',        # GTK 4.0
            'glib20',       # GLib
        ]
        
        for domain in domains_to_configure:
            try:
                gettext.bindtextdomain(domain, '/usr/share/locale')
                print(f"DEBUG: Configurado domínio de tradução: {domain}")
            except Exception as e:
                print(f"DEBUG: Falha ao configurar domínio {domain}: {e}")
    
    except Exception as e:
        print(f"DEBUG: Erro na configuração de gettext: {e}")
    
    return target_language

# Chamar a função de configuração
DETECTED_SPELLCHECK_LANGUAGE = setup_system_localization()


class TacApplication(Adw.Application):
    """Main TAC application class"""
    
    def __init__(self):
        super().__init__(
            application_id='org.communitybig.tac',
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )
        GLib.set_prgname('org.communitybig.tac')
        
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
                for lang in ['pt_BR', 'en_US', 'en_GB', 'es_ES', 'fr_FR', 'de_DE', 'it_IT']:
                    try:
                        if enchant.dict_exists(lang):
                            available_dicts.append(lang)
                    except:
                        pass

                if available_dicts:
                    print(f"Available spell check dictionaries: {available_dicts}")
                    # Update config with actually available languages
                    self.config.set('spell_check_available_languages', available_dicts)
                    
                    # NOVO: Usar o idioma detectado automaticamente se disponível
                    if DETECTED_SPELLCHECK_LANGUAGE in available_dicts:
                        detected_language = DETECTED_SPELLCHECK_LANGUAGE
                        print(f"Using auto-detected language: {detected_language}")
                    else:
                        # Fallback para o primeiro disponível
                        detected_language = available_dicts[0]
                        print(f"Auto-detected language not available, using fallback: {detected_language}")
                    
                    self.config.set_spell_check_language(detected_language)
                    
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
            ('<Control>n', 'app.new_project'),
            ('<Control>o', 'app.open_project'),
            ('<Control>s', 'app.save_project'),
            ('<Control>e', 'app.export_project'),
            ('<Control>comma', 'app.preferences'),
            ('<Control>q', 'app.quit'),
            # NOVO: Atalhos globais de undo/redo (backup se os atalhos da janela falharem)
            ('<Control>z', 'app.undo'),
            ('<Control><Shift>z', 'app.redo'),
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
        
        # NOVO: Configuração adicional para traduções do GTK
        try:
            # Forçar recarregamento das traduções GTK com novo locale
            import gi
            gi.require_version('Gtk', '4.0')
            from gi.repository import Gtk
            
            # Isso força o GTK a recarregar as traduções
            display = Gtk.Widget.get_default_direction()
            print(f"DEBUG: GTK direction: {display}")
            
        except Exception as e:
            print(f"DEBUG: Erro ao configurar traduções GTK: {e}")
        
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


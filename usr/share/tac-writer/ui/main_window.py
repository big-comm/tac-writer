"""
TAC Main Window
Main application window using GTK4 and libadwaita
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio, GObject, GLib
from core.models import Project, ParagraphType
from core.services import ProjectManager, ExportService
from core.config import Config
from utils.helpers import TextHelper, ValidationHelper, FormatHelper
from utils.i18n import _
from .components import WelcomeView, ParagraphEditor, ProjectListWidget
from .dialogs import NewProjectDialog, ExportDialog, PreferencesDialog, AboutDialog, WelcomeDialog

class MainWindow(Adw.ApplicationWindow):
    """Main application window"""

    __gtype_name__ = 'TacMainWindow'

    def __init__(self, application, project_manager: ProjectManager, config: Config, **kwargs):
        super().__init__(application=application, **kwargs)

        # Store references
        self.project_manager = project_manager
        self.config = config
        self.export_service = ExportService()
        self.current_project: Project = None

        # UI components
        self.header_bar = None
        self.toast_overlay = None
        self.main_stack = None
        self.welcome_view = None
        self.editor_view = None
        self.sidebar = None

        # Setup window
        self._setup_window()
        self._setup_ui()
        self._setup_actions()
        self._setup_keyboard_shortcuts()  # NOVO: Configurar atalhos de teclado
        self._restore_window_state()

        # Show welcome dialog if enabled
        GLib.timeout_add(500, self._maybe_show_welcome_dialog)

        print("MainWindow initialized")

    def _setup_window(self):
        """Setup basic window properties"""
        self.set_title(_("TAC - Continuous Argumentation Technique"))
        self.set_icon_name("com.github.tac")

        # Set default size
        default_width = self.config.get('window_width', 1200)
        default_height = self.config.get('window_height', 800)
        self.set_default_size(default_width, default_height)

        # Connect window state events
        self.connect('close-request', self._on_close_request)
        self.connect('notify::maximized', self._on_window_state_changed)

    def _setup_ui(self):
        """Setup the user interface"""
        # Toast overlay for notifications
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(main_box)

        # Header bar
        self._setup_header_bar()
        main_box.append(self.header_bar)

        # Main content area with sidebar
        self._setup_content_area(main_box)

        # Show welcome view initially
        self._show_welcome_view()

    def _setup_header_bar(self):
        """Setup the header bar"""
        self.header_bar = Adw.HeaderBar()

        # Title widget
        title_widget = Adw.WindowTitle()
        title_widget.set_title("TAC")
        self.header_bar.set_title_widget(title_widget)

        # Left side buttons
        new_button = Gtk.Button()
        new_button.set_icon_name("document-new-symbolic")
        new_button.set_tooltip_text(_("New Project (Ctrl+N)"))
        new_button.set_action_name("app.new_project")
        self.header_bar.pack_start(new_button)

        open_button = Gtk.Button()
        open_button.set_icon_name("document-open-symbolic")
        open_button.set_tooltip_text(_("Open Project (Ctrl+O)"))
        open_button.set_action_name("app.open_project")
        self.header_bar.pack_start(open_button)

        # Right side buttons
        save_button = Gtk.Button()
        save_button.set_icon_name("document-save-symbolic")
        save_button.set_tooltip_text(_("Save Project (Ctrl+S)"))
        save_button.set_action_name("app.save_project")
        save_button.set_sensitive(False)  # Initially disabled
        self.header_bar.pack_end(save_button)
        self.save_button = save_button

        # Menu button
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_tooltip_text(_("Main Menu"))
        self._setup_menu(menu_button)
        self.header_bar.pack_end(menu_button)

    def _setup_menu(self, menu_button):
        """Setup the main menu - CORRIGIDO"""
        menu_model = Gio.Menu()

        # File section
        file_section = Gio.Menu()
        file_section.append(_("Export Project..."), "app.export_project")
        menu_model.append_section(None, file_section)

        # Edit section - Undo/Redo (CORRIGIDO: separado das preferences)
        edit_section = Gio.Menu()
        edit_section.append(_("Undo"), "win.undo")
        edit_section.append(_("Redo"), "win.redo")
        menu_model.append_section(None, edit_section)

        # Preferences section - CORRIGIDO: seção separada para criar separador visual
        preferences_section = Gio.Menu()
        preferences_section.append(_("Preferences"), "app.preferences")
        menu_model.append_section(None, preferences_section)

        # Help section
        help_section = Gio.Menu()
        help_section.append(_("Welcome Guide"), "win.show_welcome")
        help_section.append(_("About TAC"), "app.about")
        menu_model.append_section(None, help_section)

        menu_button.set_menu_model(menu_model)

    def _setup_content_area(self, main_box):
        """Setup the main content area"""
        # Leaflet for responsive layout
        self.leaflet = Adw.Leaflet()
        self.leaflet.set_can_navigate_back(True)
        self.leaflet.set_can_navigate_forward(True)
        main_box.append(self.leaflet)

        # Sidebar
        self._setup_sidebar()

        # Main content stack
        self.main_stack = Adw.ViewStack()
        self.main_stack.set_vexpand(True)
        self.main_stack.set_hexpand(True)
        self.leaflet.append(self.main_stack)

    def _setup_sidebar(self):
        """Setup the sidebar"""
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_box.set_size_request(300, -1)
        sidebar_box.add_css_class("sidebar")

        # Sidebar header
        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_show_end_title_buttons(False)
        sidebar_title = Adw.WindowTitle()
        sidebar_title.set_title(_("Projects"))
        sidebar_header.set_title_widget(sidebar_title)
        sidebar_box.append(sidebar_header)

        # Project list
        self.project_list = ProjectListWidget(self.project_manager)
        self.project_list.connect('project-selected', self._on_project_selected)
        sidebar_box.append(self.project_list)

        self.leaflet.append(sidebar_box)
        self.sidebar = sidebar_box

    def _setup_actions(self):
        """Setup window-specific actions"""
        actions = [
            ('toggle_sidebar', self._action_toggle_sidebar),
            ('add_paragraph', self._action_add_paragraph, 's'),  # 's' = string parameter
            ('show_welcome', self._action_show_welcome),
            # NOVO: Adicionadas ações de undo/redo
            ('undo', self._action_undo),
            ('redo', self._action_redo),
        ]

        for action_data in actions:
            if len(action_data) == 3:
                # Action with parameter - use string to create VariantType
                action = Gio.SimpleAction.new(action_data[0], GLib.VariantType.new(action_data[2]))
            else:
                # Simple action
                action = Gio.SimpleAction.new(action_data[0], None)
            action.connect('activate', action_data[1])
            self.add_action(action)

    def _setup_keyboard_shortcuts(self):
        """Setup window-specific shortcuts"""
        shortcut_controller = Gtk.ShortcutController()
        
        # Undo
        undo_shortcut = Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("<Ctrl>z"),
            Gtk.NamedAction.new("win.undo")
        )
        shortcut_controller.add_shortcut(undo_shortcut)
        
        # Redo
        redo_shortcut = Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("<Ctrl><Shift>z"),
            Gtk.NamedAction.new("win.redo")
        )
        shortcut_controller.add_shortcut(redo_shortcut)
        
        self.add_controller(shortcut_controller)

    def _show_welcome_view(self):
        """Show the welcome view"""
        if not self.welcome_view:
            self.welcome_view = WelcomeView()
            self.welcome_view.connect('create-project', self._on_create_project_from_welcome)
            self.welcome_view.connect('open-project', self._on_open_project_from_welcome)

        self.main_stack.add_named(self.welcome_view, "welcome")
        self.main_stack.set_visible_child_name("welcome")
        self._update_header_for_view("welcome")

    def _show_editor_view(self):
        """Show the editor view"""
        if not self.current_project:
            return

        # Remove existing editor view if any
        editor_page = self.main_stack.get_child_by_name("editor")
        if editor_page:
            self.main_stack.remove(editor_page)

        # Create new editor view
        self.editor_view = self._create_editor_view()
        self.main_stack.add_named(self.editor_view, "editor")
        self.main_stack.set_visible_child_name("editor")
        self._update_header_for_view("editor")

    def _create_editor_view(self) -> Gtk.Widget:
        """Create the editor view for current project"""
        # Main editor container
        editor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Scrolled window for paragraphs
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        # Paragraphs container
        self.paragraphs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.paragraphs_box.set_spacing(12)
        self.paragraphs_box.set_margin_start(20)
        self.paragraphs_box.set_margin_end(20)
        self.paragraphs_box.set_margin_top(20)
        self.paragraphs_box.set_margin_bottom(20)

        scrolled.set_child(self.paragraphs_box)
        editor_box.append(scrolled)

        # Add existing paragraphs
        self._refresh_paragraphs()

        # Add paragraph toolbar
        toolbar = self._create_paragraph_toolbar()
        editor_box.append(toolbar)

        return editor_box

    def _create_paragraph_toolbar(self) -> Gtk.Widget:
        """Create toolbar for adding paragraphs and formatting"""
        toolbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        toolbar_box.set_spacing(6)
        toolbar_box.set_margin_start(20)
        toolbar_box.set_margin_end(20)
        toolbar_box.set_margin_top(10)
        toolbar_box.set_margin_bottom(20)
        toolbar_box.add_css_class("toolbar")

        # Add paragraph menu button
        add_button = Gtk.MenuButton()
        add_button.set_label(_("Add Paragraph"))
        add_button.set_icon_name("list-add-symbolic")
        add_button.add_css_class("suggested-action")

        # Create menu model
        menu_model = Gio.Menu()
        paragraph_types = [
            (_("Title 1"), ParagraphType.TITLE_1),
            (_("Title 2"), ParagraphType.TITLE_2),
            (_("Introduction"), ParagraphType.INTRODUCTION),
            (_("Argument"), ParagraphType.ARGUMENT),
            (_("Quote"), ParagraphType.QUOTE),
            (_("Conclusion"), ParagraphType.CONCLUSION),
        ]

        for label, ptype in paragraph_types:
            menu_model.append(label, f"win.add_paragraph('{ptype.value}')")

        add_button.set_menu_model(menu_model)
        toolbar_box.append(add_button)

        # Add formatting button
        format_button = Gtk.Button()
        format_button.set_label(_("Format"))
        format_button.set_icon_name("format-text-bold-symbolic")
        format_button.set_tooltip_text(_("Format paragraphs"))
        format_button.connect('clicked', self._on_format_clicked)
        toolbar_box.append(format_button)

        return toolbar_box

    def _refresh_paragraphs(self):
        """Refresh the paragraphs display"""
        if not self.current_project:
            return

        # Clear existing paragraphs
        child = self.paragraphs_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.paragraphs_box.remove(child)
            child = next_child

        # Add paragraphs SYNCHRONOUSLY, without delay
        for paragraph in self.current_project.paragraphs:
            paragraph_editor = ParagraphEditor(paragraph, config=self.config)
            paragraph_editor.connect('content-changed', self._on_paragraph_changed)
            paragraph_editor.connect('remove-requested', self._on_paragraph_remove_requested)
            paragraph_editor.connect('paragraph-reorder', self._on_paragraph_reorder)
            self.paragraphs_box.append(paragraph_editor)

    def _update_header_for_view(self, view_name: str):
        """Update header bar for current view"""
        if view_name == "welcome":
            title_widget = self.header_bar.get_title_widget()
            title_widget.set_title("TAC")
            title_widget.set_subtitle(_("Continuous Argumentation Technique"))
            self.save_button.set_sensitive(False)

        elif view_name == "editor" and self.current_project:
            title_widget = self.header_bar.get_title_widget()
            title_widget.set_title(self.current_project.name)
            # Show project statistics in subtitle
            stats = self.current_project.get_statistics()
            subtitle = _("{} words • {} paragraphs").format(stats['total_words'], stats['total_paragraphs'])
            title_widget.set_subtitle(subtitle)
            self.save_button.set_sensitive(True)

    # NOVOS MÉTODOS PARA UNDO/REDO
    def _get_focused_text_view(self):
        """Get the currently focused TextView widget"""
        focus_widget = self.get_focus()
        
        # Percorrer a hierarquia de widgets procurando por TextView
        current_widget = focus_widget
        while current_widget:
            if isinstance(current_widget, Gtk.TextView):
                return current_widget
            current_widget = current_widget.get_parent()
        
        # Se não encontrou foco específico, tentar encontrar o primeiro TextView visível
        if hasattr(self, 'paragraphs_box'):
            child = self.paragraphs_box.get_first_child()
            while child:
                if hasattr(child, 'text_view') and isinstance(child.text_view, Gtk.TextView):
                    return child.text_view
                child = child.get_next_sibling()
        
        return None

    def _get_paragraph_editor_from_text_view(self, text_view):
        """Get the ParagraphEditor that contains the given TextView"""
        if not text_view:
            return None
            
        current_widget = text_view
        while current_widget:
            if hasattr(current_widget, '__gtype_name__') and current_widget.__gtype_name__ == 'TacParagraphEditor':
                return current_widget
            current_widget = current_widget.get_parent()
        
        return None

    def _action_undo(self, action, param):
        """Handle global undo action - NOVO MÉTODO"""
        print("Debug: Global undo action triggered")
        
        focused_text_view = self._get_focused_text_view()
        if focused_text_view:
            # Encontrar o editor que contém este TextView
            paragraph_editor = self._get_paragraph_editor_from_text_view(focused_text_view)
            
            if paragraph_editor and hasattr(paragraph_editor, 'undo'):
                paragraph_editor.undo()
                print("Debug: Undo executed on paragraph editor")
                return
            
            # Fallback: tentar undo direto no buffer se disponível
            buffer = focused_text_view.get_buffer()
            if buffer and hasattr(buffer, 'get_can_undo') and buffer.get_can_undo():
                buffer.undo()
                print("Debug: Undo executed on text buffer directly")
                return
        
        # Se não conseguiu executar undo, mostrar mensagem
        self._show_toast(_("Nothing to undo"))
        print("Debug: No focused text view for undo")

    def _action_redo(self, action, param):
        """Handle global redo action - NOVO MÉTODO"""
        print("Debug: Global redo action triggered")
        
        focused_text_view = self._get_focused_text_view()
        if focused_text_view:
            # Encontrar o editor que contém este TextView
            paragraph_editor = self._get_paragraph_editor_from_text_view(focused_text_view)
            
            if paragraph_editor and hasattr(paragraph_editor, 'redo'):
                paragraph_editor.redo()
                print("Debug: Redo executed on paragraph editor")
                return
            
            # Fallback: tentar redo direto no buffer se disponível
            buffer = focused_text_view.get_buffer()
            if buffer and hasattr(buffer, 'get_can_redo') and buffer.get_can_redo():
                buffer.redo()
                print("Debug: Redo executed on text buffer directly")
                return
        
        # Se não conseguiu executar redo, mostrar mensagem
        self._show_toast(_("Nothing to redo"))
        print("Debug: No focused text view for redo")

    # Event handlers
    def _on_create_project_from_welcome(self, widget, template_name):
        """Handle create project from welcome view"""
        self.show_new_project_dialog()

    def _on_open_project_from_welcome(self, widget, project_info):
        """Handle open project from welcome view"""
        self._load_project(project_info['id'])

    def _on_project_selected(self, widget, project_info):
        """Handle project selection from sidebar"""
        self._load_project(project_info['id'])

    def _on_paragraph_changed(self, paragraph_editor):
        """Handle paragraph content changes"""
        if self.current_project:
            # Update project modification time
            self.current_project._update_modified_time()
            self._update_header_for_view("editor")

    def _on_paragraph_remove_requested(self, paragraph_editor, paragraph_id):
        """Handle paragraph removal request"""
        if self.current_project:
            self.current_project.remove_paragraph(paragraph_id)
            self._refresh_paragraphs()
            self._update_header_for_view("editor")

    def _on_paragraph_reorder(self, paragraph_editor, dragged_id, target_id, position):
        """Handle paragraph reordering"""
        if not self.current_project:
            return

        # Find paragraphs
        dragged_paragraph = None
        target_paragraph = None

        for p in self.current_project.paragraphs:
            if p.id == dragged_id:
                dragged_paragraph = p
            elif p.id == target_id:
                target_paragraph = p

        if not dragged_paragraph or not target_paragraph:
            return

        # Remove dragged paragraph from current position
        self.current_project.paragraphs.remove(dragged_paragraph)

        # Find target index
        target_index = self.current_project.paragraphs.index(target_paragraph)

        # Insert at new position
        if position == "before":
            insert_index = target_index
        else:  # "after"
            insert_index = target_index + 1

        self.current_project.paragraphs.insert(insert_index, dragged_paragraph)

        # Reorder paragraph numbers
        self.current_project._reorder_paragraphs()
        self.current_project._update_modified_time()

        # Refresh display
        self._refresh_paragraphs()
        self._update_header_for_view("editor")

        # Show feedback
        self._show_toast(_("Paragraph reordered"))

    def _on_close_request(self, window):
        """Handle window close request"""
        self._save_window_state()

        # Auto-save current project
        if self.current_project:
            self.save_current_project()

        return False  # Allow closing

    def _on_window_state_changed(self, window, pspec):
        """Handle window state changes"""
        self._save_window_state()

    # Action handlers
    def _action_toggle_sidebar(self, action, param):
        """Toggle sidebar visibility"""
        # TODO: Implement sidebar toggle
        pass

    def _action_add_paragraph(self, action, param):
        """Add paragraph action"""
        if param:
            paragraph_type = ParagraphType(param.get_string())
            self._add_paragraph(paragraph_type)

    # Public methods called by application
    def show_new_project_dialog(self):
        """Show new project dialog"""
        dialog = NewProjectDialog(self)
        dialog.connect('project-created', self._on_project_created)
        dialog.present()

    def show_open_project_dialog(self):
        """Show open project dialog"""
        file_chooser = Gtk.FileChooserNative.new(
            _("Open Project"),
            self,
            Gtk.FileChooserAction.OPEN,
            _("Open"),
            _("Cancel")
        )

        # Set initial folder to projects directory
        projects_dir = self.project_manager.projects_dir
        if projects_dir.exists():
            file_chooser.set_current_folder(Gio.File.new_for_path(str(projects_dir)))

        # Add file filter for JSON files
        filter_json = Gtk.FileFilter()
        filter_json.set_name(_("TAC Projects (*.json)"))
        filter_json.add_pattern("*.json")
        file_chooser.add_filter(filter_json)

        filter_all = Gtk.FileFilter()
        filter_all.set_name(_("All Files"))
        filter_all.add_pattern("*")
        file_chooser.add_filter(filter_all)

        def on_response(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                file = dialog.get_file()
                if file:
                    file_path = file.get_path()
                    # Load project by file path
                    project = self.project_manager.load_project(file_path)
                    if project:
                        self.current_project = project
                        self._show_editor_view()
                        # Update sidebar to show all projects including this one
                        self.project_list.refresh_projects()
                        self._show_toast(_("Opened project: {}").format(project.name))
                    else:
                        self._show_toast(_("Failed to open project"), Adw.ToastPriority.HIGH)
            dialog.destroy()

        file_chooser.connect('response', on_response)
        file_chooser.show()

    def save_current_project(self) -> bool:
        """Save the current project"""
        if not self.current_project:
            return False

        success = self.project_manager.save_project(self.current_project)
        if success:
            self._show_toast(_("Project saved successfully"))
            # Update sidebar to reflect changes
            self.project_list.refresh_projects()
            # Update recent projects
            project_path = str(self.project_manager.get_project_path(self.current_project))
            self.config.add_recent_project(project_path)
        else:
            self._show_toast(_("Failed to save project"), Adw.ToastPriority.HIGH)

        return success

    def show_export_dialog(self):
        """Show export dialog"""
        if not self.current_project:
            self._show_toast(_("No project to export"), Adw.ToastPriority.HIGH)
            return

        dialog = ExportDialog(self, self.current_project, self.export_service)
        dialog.present()

    def show_preferences_dialog(self):
        """Show preferences dialog"""
        dialog = PreferencesDialog(self, self.config)
        dialog.present()

    def show_about_dialog(self):
        """Show about dialog"""
        dialog = AboutDialog(self)
        dialog.present()

    # Helper methods
    def _load_project(self, project_id: str):
        """Load a project"""
        project = self.project_manager.load_project(project_id)
        if project:
            self.current_project = project
            self._show_editor_view()
            self._show_toast(_("Opened project: {}").format(project.name))
        else:
            self._show_toast(_("Failed to open project"), Adw.ToastPriority.HIGH)

    def _add_paragraph(self, paragraph_type: ParagraphType):
        """Add a new paragraph"""
        if not self.current_project:
            return

        paragraph = self.current_project.add_paragraph(paragraph_type)

        # Instead of _refresh_paragraphs(), just add the new one:
        paragraph_editor = ParagraphEditor(paragraph, config=self.config)
        paragraph_editor.connect('content-changed', self._on_paragraph_changed)
        paragraph_editor.connect('remove-requested', self._on_paragraph_remove_requested)
        paragraph_editor.connect('paragraph-reorder', self._on_paragraph_reorder)
        self.paragraphs_box.append(paragraph_editor)

        self._update_header_for_view("editor")

    def _on_project_created(self, dialog, project):
        """Handle new project creation"""
        self.current_project = project
        self._show_editor_view()

        # Update sidebar to show new project
        self.project_list.refresh_projects()
        self._show_toast(_("Created project: {}").format(project.name))

    def _show_toast(self, message: str, priority=Adw.ToastPriority.NORMAL):
        """Show a toast notification"""
        toast = Adw.Toast.new(message)
        toast.set_priority(priority)
        self.toast_overlay.add_toast(toast)

    def _save_window_state(self):
        """Save window state to config"""
        width, height = self.get_default_size()
        self.config.set('window_width', width)
        self.config.set('window_height', height)
        self.config.set('window_maximized', self.is_maximized())

    def _restore_window_state(self):
        """Restore window state from config"""
        if self.config.get('window_maximized', False):
            self.maximize()

    def _on_format_clicked(self, button):
        """Handle format button click - MODIFICADO para salvar formatação preferida"""
        if not self.current_project:
            return

        # Collect non-Quote paragraphs
        non_quote_paragraphs = [
            p for p in self.current_project.paragraphs
            if p.type != ParagraphType.QUOTE
        ]

        if not non_quote_paragraphs:
            self._show_toast(_("No paragraphs to format"))
            return

        # Open formatting dialog
        from .dialogs import FormatDialog
        dialog = FormatDialog(self, paragraphs=non_quote_paragraphs)
        
        # NOVO: Conectar sinal para salvar formatação preferida
        def on_dialog_destroy(dialog):
            if non_quote_paragraphs:
                # Salvar a formatação aplicada como preferida para novos parágrafos
                sample_formatting = non_quote_paragraphs[0].formatting.copy()
                # Remover formatações específicas que não devem ser herdadas
                preferred = {
                    'font_family': sample_formatting.get('font_family', 'Liberation Serif'),
                    'font_size': sample_formatting.get('font_size', 12),
                    'line_spacing': sample_formatting.get('line_spacing', 1.5),
                    'alignment': sample_formatting.get('alignment', 'justify'),
                    'bold': sample_formatting.get('bold', False),
                    'italic': sample_formatting.get('italic', False),
                    'underline': sample_formatting.get('underline', False),
                }
                self.current_project.update_preferred_formatting(preferred)
                print(f"Debug: Saved preferred formatting after dialog close: {preferred}")
        
        dialog.connect('destroy', on_dialog_destroy)
        dialog.present()

    def _maybe_show_welcome_dialog(self):
        """Show welcome dialog if enabled in config"""
        if self.config.get('show_welcome_dialog', True):
            self.show_welcome_dialog()
        return False  # Don't repeat the timeout

    def show_welcome_dialog(self):
        """Show the welcome dialog"""
        dialog = WelcomeDialog(self, self.config)
        dialog.present()

    def _action_show_welcome(self, action, param):
        """Handle show welcome action"""
        self.show_welcome_dialog()

    def _refresh_paragraph_formatting(self):
        """Refresh formatting display for all paragraph editors"""
        if hasattr(self, 'paragraphs_box'):
            child = self.paragraphs_box.get_first_child()
            while child:
                if hasattr(child, 'refresh_formatting'):
                    child.refresh_formatting()
                child = child.get_next_sibling()


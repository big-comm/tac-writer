"""
TAC Main Window
Main application window using GTK4 and libadwaita
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio, GLib, Gdk

from core.models import Project, ParagraphType
from core.services import ProjectManager, ExportService
from core.config import Config
from utils.helpers import FormatHelper
from utils.i18n import _
from .components import WelcomeView, ParagraphEditor, ProjectListWidget, SpellCheckHelper, PomodoroTimer
from .dialogs import NewProjectDialog, ExportDialog, PreferencesDialog, AboutDialog, WelcomeDialog, BackupManagerDialog


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

        # Shared spell check helper
        self.spell_helper = SpellCheckHelper(config) if config else None

        # Pomodoro Timer
        self.pomodoro_dialog = None
        self.timer = PomodoroTimer()

        # Auto-save timer tracking
        self.auto_save_timeout_id = None
        self.auto_save_pending = False

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
        self._setup_keyboard_shortcuts()
        self._restore_window_state()

        # Show welcome dialog if enabled
        GLib.timeout_add(500, self._maybe_show_welcome_dialog)

    def _setup_window(self):
        """Setup basic window properties"""
        self.set_title(_("TAC - Continuous Argumentation Technique"))
        self.set_icon_name("tac-writer")

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
        new_button.set_icon_name('tac-document-new-symbolic')
        new_button.set_tooltip_text(_("New Project (Ctrl+N)"))
        new_button.set_action_name("app.new_project")
        self.header_bar.pack_start(new_button)

        # Pomodoro Timer Button
        self.pomodoro_button = Gtk.Button()
        self.pomodoro_button.set_icon_name('tac-alarm-symbolic')
        self.pomodoro_button.set_tooltip_text(_("Pomodoro Timer"))
        self.pomodoro_button.connect('clicked', self._on_pomodoro_clicked)
        self.pomodoro_button.set_sensitive(False)
        self.header_bar.pack_start(self.pomodoro_button)

        # Right side buttons
        save_button = Gtk.Button()
        save_button.set_icon_name('tac-document-save-symbolic')
        save_button.set_tooltip_text(_("Save Project (Ctrl+S)"))
        save_button.set_action_name("app.save_project")
        save_button.set_sensitive(False)
        self.header_bar.pack_end(save_button)
        self.save_button = save_button

        # Menu button
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name('tac-open-menu-symbolic')
        menu_button.set_tooltip_text(_("Main Menu"))
        self._setup_menu(menu_button)
        self.header_bar.pack_end(menu_button)

    def _setup_menu(self, menu_button):
        """Setup the main menu"""
        menu_model = Gio.Menu()

        # File section
        file_section = Gio.Menu()
        file_section.append(_("Export Project..."), "app.export_project")
        file_section.append(_("Backup Manager..."), "win.backup_manager")
        menu_model.append_section(None, file_section)

        # Edit section
        edit_section = Gio.Menu()
        edit_section.append(_("Undo"), "win.undo")
        edit_section.append(_("Redo"), "win.redo")
        menu_model.append_section(None, edit_section)

        # Preferences section
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
            ('add_paragraph', self._action_add_paragraph, 's'),
            ('show_welcome', self._action_show_welcome),
            ('undo', self._action_undo),
            ('redo', self._action_redo),
            ('backup_manager', self._action_backup_manager),
        ]

        for action_data in actions:
            if len(action_data) == 3:
                action = Gio.SimpleAction.new(action_data[0], GLib.VariantType.new(action_data[2]))
            else:
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
        # Main editor container with overlay for floating buttons
        overlay = Gtk.Overlay()

        # Main editor container
        editor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Scrolled window for paragraphs
        self.editor_scrolled = Gtk.ScrolledWindow()
        self.editor_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.editor_scrolled.set_vexpand(True)

        # Paragraphs container
        self.paragraphs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.paragraphs_box.set_spacing(12)
        self.paragraphs_box.set_margin_start(20)
        self.paragraphs_box.set_margin_end(20)
        self.paragraphs_box.set_margin_top(20)
        self.paragraphs_box.set_margin_bottom(20)

        self.editor_scrolled.set_child(self.paragraphs_box)
        editor_box.append(self.editor_scrolled)

        # Add existing paragraphs
        self._refresh_paragraphs()

        # Add paragraph toolbar
        toolbar = self._create_paragraph_toolbar()
        editor_box.append(toolbar)

        # Set main editor as overlay child
        overlay.set_child(editor_box)

        # Create floating navigation buttons
        nav_buttons = self._create_navigation_buttons()
        overlay.add_overlay(nav_buttons)

        return overlay

    def _create_paragraph_toolbar(self) -> Gtk.Widget:
        """Create toolbar for adding paragraphs"""
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
        add_button.set_icon_name('tac-list-add-symbolic')
        add_button.add_css_class("suggested-action")

        # Create menu model
        menu_model = Gio.Menu()
        paragraph_types = [
            (_("Title 1"), ParagraphType.TITLE_1),
            (_("Title 2"), ParagraphType.TITLE_2),
            (_("Introduction"), ParagraphType.INTRODUCTION),
            (_("Argument"), ParagraphType.ARGUMENT),
            (_("Argument Resumption"), ParagraphType.ARGUMENT_RESUMPTION),
            (_("Quote"), ParagraphType.QUOTE),
            (_("Epigraph"), ParagraphType.EPIGRAPH),
            (_("Conclusion"), ParagraphType.CONCLUSION),
        ]

        for label, ptype in paragraph_types:
            menu_model.append(label, f"win.add_paragraph('{ptype.value}')")

        add_button.set_menu_model(menu_model)
        toolbar_box.append(add_button)

        return toolbar_box
    
    def _create_navigation_buttons(self) -> Gtk.Widget:
        """Create floating navigation buttons for quick scrolling"""
        # Container for buttons positioned at bottom right
        nav_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        nav_container.set_halign(Gtk.Align.END)
        nav_container.set_valign(Gtk.Align.END)
        nav_container.set_margin_end(20)
        nav_container.set_margin_bottom(20)

        # Go to top button
        top_button = Gtk.Button()
        top_button.set_icon_name('tac-go-up-symbolic')
        top_button.set_tooltip_text(_("Go to beginning"))
        top_button.add_css_class("circular")
        top_button.add_css_class("flat")
        top_button.set_size_request(40, 40)
        top_button.connect('clicked', self._on_scroll_to_top)
        nav_container.append(top_button)

        # Go to bottom button  
        bottom_button = Gtk.Button()
        bottom_button.set_icon_name('tac-go-down-symbolic')
        bottom_button.set_tooltip_text(_("Go to end"))
        bottom_button.add_css_class("circular")
        bottom_button.add_css_class("flat")
        bottom_button.set_size_request(40, 40)
        bottom_button.connect('clicked', self._on_scroll_to_bottom)
        nav_container.append(bottom_button)

        return nav_container

    def _on_scroll_to_top(self, button):
        """Scroll to the top of the project"""
        if hasattr(self, 'editor_scrolled'):
            adjustment = self.editor_scrolled.get_vadjustment()
            adjustment.set_value(adjustment.get_lower())

    def _on_scroll_to_bottom(self, button):
        """Scroll to the bottom of the project"""
        if hasattr(self, 'editor_scrolled'):
            adjustment = self.editor_scrolled.get_vadjustment()
            adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())

    def _refresh_paragraphs(self):
        """Refresh paragraphs display with optimized loading"""
        if not self.current_project:
            return
    
        existing_widgets = {}
        child = self.paragraphs_box.get_first_child()
        while child:
            if hasattr(child, 'paragraph') and hasattr(child.paragraph, 'id'):
                existing_widgets[child.paragraph.id] = child
            child = child.get_next_sibling()

        current_paragraph_ids = {p.id for p in self.current_project.paragraphs}
    
        for paragraph_id, widget in list(existing_widgets.items()):
            if paragraph_id not in current_paragraph_ids:
                self.paragraphs_box.remove(widget)
                del existing_widgets[paragraph_id]
    
        child = self.paragraphs_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.paragraphs_box.remove(child)
            child = next_child
    
        self._paragraphs_to_add = list(self.current_project.paragraphs)
        self._existing_widgets = existing_widgets

        GLib.idle_add(self._process_next_paragraph)

    def _process_next_paragraph(self):
        """Process next paragraph for asynchronous loading"""
        if not self._paragraphs_to_add:
            return False

        paragraph = self._paragraphs_to_add.pop(0)
        if paragraph.id in self._existing_widgets:
            widget = self._existing_widgets[paragraph.id]
            self.paragraphs_box.append(widget)
        else:
            paragraph_editor = ParagraphEditor(paragraph, config=self.config)
            paragraph_editor.connect('content-changed', self._on_paragraph_changed)
            paragraph_editor.connect('remove-requested', self._on_paragraph_remove_requested)
            paragraph_editor.connect('paragraph-reorder', self._on_paragraph_reorder)
            self.paragraphs_box.append(paragraph_editor)
            self._existing_widgets[paragraph.id] = paragraph_editor

        return True

    def _get_focused_text_view(self):
        """Get the currently focused TextView widget"""
        focus_widget = self.get_focus()
        
        current_widget = focus_widget
        while current_widget:
            if isinstance(current_widget, Gtk.TextView):
                return current_widget
            current_widget = current_widget.get_parent()
        
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
        """Handle global undo action"""
        focused_text_view = self._get_focused_text_view()
        if focused_text_view:
            buffer = focused_text_view.get_buffer()
            if buffer and hasattr(buffer, 'get_can_undo'):
                if buffer.get_can_undo():
                    buffer.undo()
                    self._show_toast(_("Undo"))
                    return
            
            # Fallback: Try Ctrl+Z key simulation
            try:
                focused_text_view.emit('key-pressed', Gdk.KEY_z, Gdk.ModifierType.CONTROL_MASK, 0)
                return
            except:
                pass
        
        self._show_toast(_("Nothing to undo"))

    def _action_redo(self, action, param):
        """Handle global redo action"""
        focused_text_view = self._get_focused_text_view()
        if focused_text_view:
            buffer = focused_text_view.get_buffer()
            if buffer and hasattr(buffer, 'get_can_redo'):
                if buffer.get_can_redo():
                    buffer.redo()
                    self._show_toast(_("Redo"))
                    return
            
            # Fallback: Try Ctrl+Shift+Z key simulation
            try:
                focused_text_view.emit('key-pressed', Gdk.KEY_z, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK, 0)
                return
            except:
                pass
        
        self._show_toast(_("Nothing to redo"))

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
            self.current_project._update_modified_time()
            self._update_header_for_view("editor")
            # Update sidebar project list in real-time with current statistics
            current_stats = self.current_project.get_statistics()
            self.project_list.update_project_statistics(self.current_project.id, current_stats)
            
            # Schedule auto-save if enabled
            self._schedule_auto_save()

    def _on_paragraph_remove_requested(self, paragraph_editor, paragraph_id):
        """Handle paragraph removal request"""
        if self.current_project:
            self.current_project.remove_paragraph(paragraph_id)
            self._refresh_paragraphs()
            self._update_header_for_view("editor")
            # Update sidebar project list in real-time with current statistics
            current_stats = self.current_project.get_statistics()
            self.project_list.update_project_statistics(self.current_project.id, current_stats)

    def _on_paragraph_reorder(self, paragraph_editor, dragged_id, target_id, position):
        """Handle paragraph reordering"""
        if not self.current_project:
            return

        dragged_paragraph = self.current_project.get_paragraph(dragged_id)
        target_paragraph = self.current_project.get_paragraph(target_id)

        if not dragged_paragraph or not target_paragraph:
            return
        
        current_position = self.current_project.paragraphs.index(dragged_paragraph)
        target_position = self.current_project.paragraphs.index(target_paragraph)

        if position == "after":
            new_position = target_position + 1 if current_position < target_position else target_position
        else: # "before"
            new_position = target_position if current_position > target_position else target_position -1
        
        self.current_project.move_paragraph(dragged_id, new_position)
        self._refresh_paragraphs()
        self._update_header_for_view("editor")
        self._show_toast(_("Paragraph reordered"))

    def _on_close_request(self, window):
        """Handle window close request"""
        # Cancel any pending auto-save timer
        if self.auto_save_timeout_id is not None:
            GLib.source_remove(self.auto_save_timeout_id)
            self.auto_save_timeout_id = None
        
        # If there's a pending auto-save, perform final save now
        if self.auto_save_pending and self.current_project:
            self.project_manager.save_project(self.current_project)
        
        # Save window state
        self._save_window_state()
        
        # Check if project needs saving (optional confirmation)
        if self.current_project and self.config.get('confirm_on_close', True):
            # Could add unsaved changes dialog here
            pass
        
        return False

    def _on_window_state_changed(self, window, pspec):
        """Handle window state changes"""
        self._save_window_state()

    def _on_pomodoro_clicked(self, button):
        """Handle pomodoro button click"""
        if not self.pomodoro_dialog:
            from ui.components import PomodoroDialog
            self.pomodoro_dialog = PomodoroDialog(self, self.timer)
        self.pomodoro_dialog.show_dialog()

    # Action handlers
    def _action_toggle_sidebar(self, action, param):
        """Toggle sidebar visibility"""
        pass

    def _action_add_paragraph(self, action, param):
        """Add paragraph action"""
        if param:
            paragraph_type = ParagraphType(param.get_string())
            self._add_paragraph(paragraph_type)

    def _action_show_welcome(self, action, param):
        """Handle show welcome action"""
        self.show_welcome_dialog()
        
    def _action_backup_manager(self, action, param):
        """Handle backup manager action"""
        self.show_backup_manager_dialog()

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

        projects_dir = self.project_manager.projects_dir
        if projects_dir.exists():
            file_chooser.set_current_folder(Gio.File.new_for_path(str(projects_dir)))

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
                    project = self.project_manager.load_project(file_path)
                    if project:
                        self.current_project = project
                        self._show_editor_view()
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
            self.project_list.refresh_projects()
            self.config.add_recent_project(self.current_project.id)
        else:
            self._show_toast(_("Failed to save project"), Adw.ToastPriority.HIGH)

        return success
    
    def _schedule_auto_save(self):
        """Schedule an auto-save operation after a delay"""
        # Check if auto-save is enabled
        if not self.config.get('auto_save', True):
            return
        
        # Cancel existing timeout if any
        if self.auto_save_timeout_id is not None:
            GLib.source_remove(self.auto_save_timeout_id)
            self.auto_save_timeout_id = None
        
        # Get auto-save interval (default 120 seconds = 2 minutes)
        interval_seconds = self.config.get('auto_save_interval', 120)
        interval_ms = interval_seconds * 1000
        
        # Mark that auto-save is pending
        self.auto_save_pending = True
        
        # Schedule new auto-save
        self.auto_save_timeout_id = GLib.timeout_add(interval_ms, self._perform_auto_save)

    def _perform_auto_save(self):
        """Perform the actual auto-save operation"""
        # Reset timeout ID since this callback is executing
        self.auto_save_timeout_id = None
        self.auto_save_pending = False
        
        # Only save if there's a current project
        if not self.current_project:
            return False  # Don't repeat timeout
        
        # Perform save (this will trigger backup creation)
        success = self.project_manager.save_project(self.current_project)
        
        if success:
            # Silent save - no toast for auto-save to avoid interrupting user
            self.project_list.refresh_projects()
            self.config.add_recent_project(self.current_project.id)
            
            # Update header to show saved state (remove asterisk if you have one)
            self._update_header_for_view("editor")
        else:
            # Only show toast on failure
            self._show_toast(_("Auto-save failed"), Adw.ToastPriority.HIGH)
        
        return False  # Don't repeat the timeout

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

    def show_welcome_dialog(self):
        """Show the welcome dialog"""
        dialog = WelcomeDialog(self, self.config)
        dialog.present()

    def show_backup_manager_dialog(self):
        """Show the backup manager dialog"""
        dialog = BackupManagerDialog(self, self.project_manager)
        dialog.connect('database-imported', self._on_database_imported)
        dialog.present()

    def _on_database_imported(self, dialog):
        """Handle database import completion"""
        # Refresh project list
        self.project_list.refresh_projects()
        
        # Clear current project if one is open
        self.current_project = None
        
        # Show welcome view
        self._show_welcome_view()
        
        # Show success toast
        self._show_toast(_("Database imported successfully"), Adw.ToastPriority.HIGH)

    def _load_project(self, project_id: str):
        """Load a project by ID"""
        self._show_loading_state()

        try:
            project = self.project_manager.load_project(project_id)
            self._on_project_loaded(project, None)
        except Exception as e:
            self._on_project_loaded(None, str(e))

    def _add_paragraph(self, paragraph_type: ParagraphType):
        """Add a new paragraph"""
        if not self.current_project:
            return

        paragraph = self.current_project.add_paragraph(paragraph_type)

        paragraph_editor = ParagraphEditor(paragraph, config=self.config)
        paragraph_editor.connect('content-changed', self._on_paragraph_changed)
        paragraph_editor.connect('remove-requested', self._on_paragraph_remove_requested)
        paragraph_editor.connect('paragraph-reorder', self._on_paragraph_reorder)
        self.paragraphs_box.append(paragraph_editor)

        self._update_header_for_view("editor")
        # Update sidebar project list in real-time with current statistics
        current_stats = self.current_project.get_statistics()
        self.project_list.update_project_statistics(self.current_project.id, current_stats)

    def _on_project_created(self, dialog, project):
        """Handle new project creation"""
        self.current_project = project
        self._show_editor_view()

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

    def _maybe_show_welcome_dialog(self):
        """Show welcome dialog if enabled in config"""
        if self.config.get('show_welcome_dialog', True):
            self.show_welcome_dialog()
        return False

    def _update_header_for_view(self, view_name: str):
        """Update header bar for current view"""
        title_widget = self.header_bar.get_title_widget()
        if view_name == "welcome":
            title_widget.set_title("TAC")
            title_widget.set_subtitle(_("Continuous Argumentation Technique"))
            self.save_button.set_sensitive(False)
            self.pomodoro_button.set_sensitive(False)

        elif view_name == "editor" and self.current_project:
            title_widget.set_title(self.current_project.name)
            # Force recalculation of statistics
            stats = self.current_project.get_statistics()
            subtitle = FormatHelper.format_project_stats(stats['total_words'], stats['total_paragraphs'])
            title_widget.set_subtitle(subtitle)
            self.save_button.set_sensitive(True)
            self.pomodoro_button.set_sensitive(True)

    def _show_loading_state(self):
        """Show loading indicator"""
        # Create loading spinner if it doesn't exist
        if not hasattr(self, 'loading_spinner'):
            self.loading_spinner = Gtk.Spinner()
            self.loading_spinner.set_size_request(48, 48)
            
        # Add to stack if not there
        if not self.main_stack.get_child_by_name("loading"):
            loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            loading_box.set_valign(Gtk.Align.CENTER)
            loading_box.set_halign(Gtk.Align.CENTER)
            
            self.loading_spinner.start()
            loading_box.append(self.loading_spinner)
            
            loading_label = Gtk.Label()
            loading_label.set_text(_("Loading project..."))
            loading_label.add_css_class("dim-label")
            loading_box.append(loading_label)
            
            self.main_stack.add_named(loading_box, "loading")
        
        # Show loading
        self.main_stack.set_visible_child_name("loading")
        self._update_header_for_view("loading")

    def _on_project_loaded(self, project, error):
        """Callback when project finishes loading"""
        # Stop loading spinner
        if hasattr(self, 'loading_spinner'):
            self.loading_spinner.stop()
        
        if error:
            self._show_toast(_("Failed to open project: {}").format(error), Adw.ToastPriority.HIGH)
            self._show_welcome_view()
            return False
        
        if project:
            self.current_project = project
            # Show editor optimized
            self._show_editor_view_optimized()
            self._show_toast(_("Opened project: {}").format(project.name))
        else:
            self._show_toast(_("Failed to open project"), Adw.ToastPriority.HIGH)
            self._show_welcome_view()
        
        return False 

    def _show_editor_view_optimized(self):
        """Show editor view with optimizations"""
        if not self.current_project:
            return
        
        # Check if editor view already exists
        editor_page = self.main_stack.get_child_by_name("editor")
        
        if not editor_page:
            # Create editor view only if it doesn't exist
            self.editor_view = self._create_editor_view()
            self.main_stack.add_named(self.editor_view, "editor")
        else:
            # Reuse existing view and only do incremental refresh
            self.editor_view = editor_page
            self._refresh_paragraphs()  # Now uses incremental update
        
        self.main_stack.set_visible_child_name("editor")
        self._update_header_for_view("editor")

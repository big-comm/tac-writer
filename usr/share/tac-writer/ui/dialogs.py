"""
TAC UI Dialogs
Dialog windows for the TAC application using GTK4 and libadwaita
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GObject, Gio, Gdk, Pango, GLib

import sqlite3
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

from core.models import Project, DEFAULT_TEMPLATES, Paragraph
from core.services import ProjectManager, ExportService
from core.config import Config
from utils.helpers import ValidationHelper, FileHelper
from utils.i18n import _


def get_system_fonts():
    """Get list of system fonts using multiple fallback methods"""
    font_names = []
    
    try:
        # Method 1: Try PangoCairo
        gi.require_version('PangoCairo', '1.0')
        from gi.repository import PangoCairo
        font_map = PangoCairo.font_map_get_default()
        families = font_map.list_families()
        for family in families:
            font_names.append(family.get_name())
    except:
        try:
            # Method 2: Try Pango context
            context = Pango.Context()
            font_map = context.get_font_map()
            families = font_map.list_families()
            for family in families:
                font_names.append(family.get_name())
        except:
            try:
                # Method 3: Use fontconfig command
                result = subprocess.run(['fc-list', ':', 'family'], capture_output=True, text=True)
                if result.returncode == 0:
                    font_names = set()
                    for line in result.stdout.strip().split('\n'):
                        if line:
                            family = line.split(',')[0].strip()
                            font_names.add(family)
                    font_names = sorted(list(font_names))
            except:
                # Fallback fonts
                font_names = ["Liberation Serif", "DejaVu Sans", "Ubuntu", "Cantarell"]
    
    if not font_names:
        font_names = ["Liberation Serif"]
    
    return sorted(font_names)


class NewProjectDialog(Adw.Window):
    """Dialog for creating new projects"""

    __gtype_name__ = 'TacNewProjectDialog'

    __gsignals__ = {
        'project-created': (GObject.SIGNAL_RUN_FIRST, None, (object,)),
    }

    def __init__(self, parent, **kwargs):
        super().__init__(**kwargs)
        self.set_title(_("New Project"))
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(600, 700)
        self.set_resizable(True)

        # Get project manager from parent
        self.project_manager = parent.project_manager

        # Create UI
        self._create_ui()

    def _create_ui(self):
        """Create the dialog UI"""
        # Main content
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(content_box)

        # Header bar
        header_bar = Adw.HeaderBar()
        header_bar.set_show_end_title_buttons(False)

        # Cancel button
        cancel_button = Gtk.Button()
        cancel_button.set_label(_("Cancel"))
        cancel_button.connect('clicked', lambda x: self.destroy())
        header_bar.pack_start(cancel_button)

        # Create button
        self.create_button = Gtk.Button()
        self.create_button.set_label(_("Create"))
        self.create_button.add_css_class("suggested-action")
        self.create_button.set_sensitive(False)
        self.create_button.connect('clicked', self._on_create_clicked)
        header_bar.pack_end(self.create_button)

        content_box.append(header_bar)

        # Scrolled window for content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(600)
        content_box.append(scrolled)

        # Main content
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_spacing(32)
        scrolled.set_child(main_box)

        # Project details section
        self._create_details_section(main_box)

        # Template selection section
        self._create_template_section(main_box)

    def _create_details_section(self, parent):
        """Create project details section"""
        details_group = Adw.PreferencesGroup()
        details_group.set_title(_("Project Details"))

        # Project name row
        name_row = Adw.ActionRow()
        name_row.set_title(_("Project Name"))
        self.name_entry = Gtk.Entry()
        self.name_entry.set_placeholder_text(_("Enter project name..."))
        self.name_entry.set_text(_("My New Project"))
        self.name_entry.set_size_request(200, -1)
        self.name_entry.connect('changed', self._on_name_changed)
        self.name_entry.connect('activate', self._on_name_activate)

        # Initial validation check
        self._on_name_changed(self.name_entry)

        # Focus and select all text for easy replacement
        self.name_entry.grab_focus()
        self.name_entry.select_region(0, -1)

        name_row.add_suffix(self.name_entry)
        details_group.add(name_row)

        # Author row
        author_row = Adw.ActionRow()
        author_row.set_title(_("Author"))
        self.author_entry = Gtk.Entry()
        self.author_entry.set_placeholder_text(_("Your name..."))
        self.author_entry.set_size_request(200, -1)
        author_row.add_suffix(self.author_entry)
        details_group.add(author_row)

        parent.append(details_group)

        # Description section
        desc_group = Adw.PreferencesGroup()
        desc_group.set_title(_("Description"))

        # Description text view in a frame
        desc_frame = Gtk.Frame()
        desc_frame.set_margin_start(12)
        desc_frame.set_margin_end(12)
        desc_frame.set_margin_top(8)
        desc_frame.set_margin_bottom(12)

        desc_scrolled = Gtk.ScrolledWindow()
        desc_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        desc_scrolled.set_size_request(-1, 120)

        self.description_view = Gtk.TextView()
        self.description_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.description_view.set_margin_start(8)
        self.description_view.set_margin_end(8)
        self.description_view.set_margin_top(8)
        self.description_view.set_margin_bottom(8)

        desc_scrolled.set_child(self.description_view)
        desc_frame.set_child(desc_scrolled)

        desc_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        desc_box.append(desc_group)
        desc_box.append(desc_frame)

        parent.append(desc_box)

    def _create_template_section(self, parent):
        """Create template selection section"""
        template_group = Adw.PreferencesGroup()
        template_group.set_title(_("Template"))
        template_group.set_description(_("Choose a template to start with"))

        # Template selection
        self.template_combo = Gtk.ComboBoxText()
        for template in DEFAULT_TEMPLATES:
            self.template_combo.append(template.name, template.name)
        self.template_combo.set_active(0)

        template_row = Adw.ActionRow()
        template_row.set_title(_("Document Template"))
        template_row.add_suffix(self.template_combo)
        template_group.add(template_row)

        # Template description
        self.template_desc_label = Gtk.Label()
        self.template_desc_label.set_wrap(True)
        self.template_desc_label.set_halign(Gtk.Align.START)
        self.template_desc_label.add_css_class("caption")
        self.template_desc_label.set_margin_start(12)
        self.template_desc_label.set_margin_end(12)
        self.template_desc_label.set_margin_bottom(12)

        # Update description
        self.template_combo.connect('changed', self._on_template_changed)
        self._on_template_changed(self.template_combo)

        template_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        template_box.append(template_group)
        template_box.append(self.template_desc_label)

        parent.append(template_box)

    def _on_name_activate(self, entry):
        """Handle Enter key in name field"""
        if self.create_button.get_sensitive():
            self._on_create_clicked(self.create_button)

    def _on_name_changed(self, entry):
        """Handle project name changes"""
        name = entry.get_text().strip()
        is_valid, error_msg = ValidationHelper.is_valid_project_name(name)
        
        self.create_button.set_sensitive(is_valid)
        
        if not is_valid and name:
            entry.add_css_class("error")
            entry.set_tooltip_text(error_msg)
        else:
            entry.remove_css_class("error")
            entry.set_tooltip_text("")

    def _on_template_changed(self, combo):
        """Handle template selection changes"""
        template_name = combo.get_active_id()
        for template in DEFAULT_TEMPLATES:
            if template.name == template_name:
                self.template_desc_label.set_text(template.description)
                break

    def _on_create_clicked(self, button):
        """Handle create button click"""
        # Get form data
        name = self.name_entry.get_text().strip()
        author = self.author_entry.get_text().strip()
        template_name = self.template_combo.get_active_id()

        # Get description
        desc_buffer = self.description_view.get_buffer()
        start_iter = desc_buffer.get_start_iter()
        end_iter = desc_buffer.get_end_iter()
        description = desc_buffer.get_text(start_iter, end_iter, False).strip()

        try:
            # Create project
            project = self.project_manager.create_project(name, template_name)
            
            # Update metadata
            project.update_metadata({
                'author': author,
                'description': description
            })
            
            # Save project
            self.project_manager.save_project(project)
            
            # Emit signal and close
            self.emit('project-created', project)
            self.destroy()
            
        except Exception as e:
            # Show error
            error_dialog = Adw.MessageDialog.new(
                self,
                _("Error Creating Project"),
                str(e)
            )
            error_dialog.add_response("ok", _("OK"))
            error_dialog.present()


class ExportDialog(Adw.Window):
    """Dialog for exporting projects"""

    __gtype_name__ = 'TacExportDialog'

    def __init__(self, parent, project: Project, export_service: ExportService, **kwargs):
        super().__init__(**kwargs)
        self.set_title(_("Export Project"))
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(550, 550)
        self.set_resizable(True)

        self.project = project
        self.export_service = export_service

        self._create_ui()

    def _create_ui(self):
        """Create the dialog UI"""
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(content_box)

        # Header bar
        header_bar = Adw.HeaderBar()

        cancel_button = Gtk.Button()
        cancel_button.set_label(_("Cancel"))
        cancel_button.connect('clicked', lambda x: self.destroy())
        header_bar.pack_start(cancel_button)

        export_button = Gtk.Button()
        export_button.set_label(_("Export"))
        export_button.add_css_class("suggested-action")
        export_button.connect('clicked', self._on_export_clicked)
        header_bar.pack_end(export_button)

        content_box.append(header_bar)

        # Preferences page
        prefs_page = Adw.PreferencesPage()
        content_box.append(prefs_page)

        # Project info
        info_group = Adw.PreferencesGroup()
        info_group.set_title(_("Project Information"))
        prefs_page.add(info_group)

        name_row = Adw.ActionRow()
        name_row.set_title(_("Project Name"))
        name_row.set_subtitle(self.project.name)
        info_group.add(name_row)

        stats = self.project.get_statistics()
        stats_row = Adw.ActionRow()
        stats_row.set_title(_("Statistics"))
        stats_row.set_subtitle(_("{} words, {} paragraphs").format(stats['total_words'], stats['total_paragraphs']))
        info_group.add(stats_row)

        # Export options
        export_group = Adw.PreferencesGroup()
        export_group.set_title(_("Export Options"))
        prefs_page.add(export_group)

        # Format selection
        self.format_row = Adw.ComboRow()
        self.format_row.set_title(_("Format"))
        format_model = Gtk.StringList()

        formats = [
            ("ODT", "odt"),
            ("TXT", "txt"),
            ("PDF", "pdf")
        ]

        self.format_data = []
        for display_name, format_code in formats:
            format_model.append(display_name)
            self.format_data.append(format_code)

        self.format_row.set_model(format_model)
        self.format_row.set_selected(0)
        export_group.add(self.format_row)

        # Include metadata
        self.metadata_row = Adw.SwitchRow()
        self.metadata_row.set_title(_("Include Metadata"))
        self.metadata_row.set_subtitle(_("Include author, creation date, and other project information"))
        self.metadata_row.set_active(True)
        export_group.add(self.metadata_row)

        # File location
        location_group = Adw.PreferencesGroup()
        location_group.set_title(_("Output Location"))
        prefs_page.add(location_group)

        self.location_row = Adw.ActionRow()
        self.location_row.set_title(_("Save Location"))
        self.location_row.set_subtitle(_("Click to choose location"))

        choose_button = Gtk.Button()
        choose_button.set_label(_("Choose..."))
        choose_button.set_valign(Gtk.Align.CENTER)
        choose_button.connect('clicked', self._on_choose_location)
        self.location_row.add_suffix(choose_button)

        location_group.add(self.location_row)

        # Initialize with default location - TAC Projects subfolder
        documents_dir = self._get_documents_directory()
        default_location = documents_dir / "TAC Projects"
        default_location.mkdir(parents=True, exist_ok=True)  # Create if doesn't exist
        self.selected_location = default_location
        self.location_row.set_subtitle(str(default_location))

    def _get_documents_directory(self) -> Path:
        """Get user's Documents directory in a language-aware way"""
        home = Path.home()
        
        # Try XDG user dirs first (Linux)
        try:
            import subprocess
            result = subprocess.run(['xdg-user-dir', 'DOCUMENTS'], 
                                capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                documents_path = Path(result.stdout.strip())
                if documents_path.exists():
                    return documents_path
        except:
            pass
        
        # Try common localized directory names
        possible_names = [
            'Documents',    # English, French
            'Documentos',   # Portuguese, Spanish
            'Dokumente',    # German
            'Documenti',    # Italian
            'Документы',    # Russian
            'Документи',    # Bulgarian, Ukrainian
            'Dokumenty',    # Czech, Polish, Slovak
            'Dokumenter',   # Danish, Norwegian
            'Έγγραφα',      # Greek
            'Dokumendid',   # Estonian
            'Asiakirjat',   # Finnish
            'מסמכים',       # Hebrew
            'Dokumenti',    # Croatian
            'Dokumentumok', # Hungarian
            'Skjöl',        # Icelandic
            'ドキュメント',     # Japanese
            '문서',          # Korean
            'Documenten',   # Dutch
            'Documente',    # Romanian
            'Dokument',     # Swedish
            'Belgeler',     # Turkish
            '文档',          # Chinese
        ]
        
        for name in possible_names:
            candidate = home / name
            if candidate.exists() and candidate.is_dir():
                return candidate
        
        # Fallback: create Documents if none exist
        documents_dir = home / 'Documentos'  # Default to Portuguese
        documents_dir.mkdir(exist_ok=True)
        return documents_dir

    def _on_choose_location(self, button):
        """Handle location selection"""
        file_chooser = Gtk.FileChooserNative.new(
            _("Choose Export Location"),
            self,
            Gtk.FileChooserAction.SELECT_FOLDER,
            _("Select"),
            _("Cancel")
        )

        file_chooser.set_current_folder(Gio.File.new_for_path(str(self.selected_location)))
        file_chooser.connect('response', self._on_location_selected)
        file_chooser.show()

    def _on_location_selected(self, dialog, response):
        """Handle location selection response"""
        if response == Gtk.ResponseType.ACCEPT:
            folder = dialog.get_file()
            if folder:
                self.selected_location = folder.get_path()
                self.location_row.set_subtitle(str(self.selected_location))

    def _on_export_clicked(self, button):
        """Handle export button click"""
        button.set_sensitive(False)
        button.set_label(_("Exporting..."))
        
        # Get selected format
        selected_index = self.format_row.get_selected()
        format_code = self.format_data[selected_index]

        # Generate filename
        safe_name = FileHelper.get_safe_filename(self.project.name)
        filename = FileHelper.ensure_extension(safe_name, format_code)

        output_path = Path(self.selected_location) / filename

        # Ensure unique filename
        output_path = FileHelper.find_available_filename(output_path)

        # Store reference to button for cleanup
        self.export_button = button

        # Execute export in separate thread
        def export_thread():
            try:
                success = self.export_service.export_project(
                    self.project,
                    str(output_path),
                    format_code
                )
                
                # Use idle_add_once to prevent multiple callbacks
                GLib.idle_add(self._export_finished, success, str(output_path), None)
                
            except Exception as e:
                GLib.idle_add(self._export_finished, False, str(output_path), str(e))
        
        thread = threading.Thread(target=export_thread, daemon=True)
        thread.start()
    
    def _export_finished(self, success, output_path, error_message):
        """Callback executed in main thread when export finishes"""
        header = self.get_titlebar()
        if header:
            child = header.get_last_child()
            while child:
                if isinstance(child, Gtk.Button):
                    child.set_sensitive(True)
                    child.set_label(_("Export"))
                    break
                child = child.get_prev_sibling()
        
        if success:
            success_dialog = Adw.MessageDialog.new(
                self,
                _("Export Successful"),
                _("Project exported to:\n{}").format(output_path)
            )
            success_dialog.add_response("ok", _("OK"))
            
            def on_success_response(dialog, response):
                dialog.destroy()
                self.destroy()
            
            success_dialog.connect('response', on_success_response)
            success_dialog.present()
            
        else:
            error_msg = error_message if error_message else _("An error occurred while exporting the project.")
            error_dialog = Adw.MessageDialog.new(
                self,
                _("Export Failed"),
                error_msg
            )
            error_dialog.add_response("ok", _("OK"))
            error_dialog.present()
        
        return False


class PreferencesDialog(Adw.PreferencesWindow):
    """Preferences dialog"""

    __gtype_name__ = 'TacPreferencesDialog'

    def __init__(self, parent, config: Config, **kwargs):
        super().__init__(**kwargs)
        self.set_title(_("Preferences"))
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(700, 600)
        self.set_resizable(True)

        self.config = config

        self._create_ui()
        self._load_preferences()

    def _create_ui(self):
        """Create the preferences UI"""
        # General page
        general_page = Adw.PreferencesPage()
        general_page.set_title(_("General"))
        general_page.set_icon_name("preferences-system-symbolic")
        self.add(general_page)

        # Appearance group
        appearance_group = Adw.PreferencesGroup()
        appearance_group.set_title(_("Appearance"))
        general_page.add(appearance_group)

        # Dark theme
        self.dark_theme_row = Adw.SwitchRow()
        self.dark_theme_row.set_title(_("Dark Theme"))
        self.dark_theme_row.set_subtitle(_("Use dark theme for the application"))
        self.dark_theme_row.connect('notify::active', self._on_dark_theme_changed)
        appearance_group.add(self.dark_theme_row)

        # Editor page
        editor_page = Adw.PreferencesPage()
        editor_page.set_title(_("Editor"))
        editor_page.set_icon_name("accessories-text-editor-symbolic")
        self.add(editor_page)

        # Font group
        font_group = Adw.PreferencesGroup()
        font_group.set_title(_("Default Font"))
        editor_page.add(font_group)

        # Font family
        self.font_family_row = Adw.ComboRow()
        self.font_family_row.set_title(_("Font Family"))
        font_model = Gtk.StringList()

        # Get system fonts
        font_names = get_system_fonts()
        for font_name in font_names:
            font_model.append(font_name)

        self.font_family_row.set_model(font_model)
        self.font_family_row.connect('notify::selected', self._on_font_family_changed)
        font_group.add(self.font_family_row)

        # Font size
        adjustment = Gtk.Adjustment(value=12, lower=8, upper=72, step_increment=1, page_increment=2)
        self.font_size_row = Adw.SpinRow()
        self.font_size_row.set_title(_("Font Size"))
        self.font_size_row.set_adjustment(adjustment)
        self.font_size_row.connect('notify::value', self._on_font_size_changed)
        font_group.add(self.font_size_row)

        # Behavior group
        behavior_group = Adw.PreferencesGroup()
        behavior_group.set_title(_("Behavior"))
        editor_page.add(behavior_group)

        # Auto save
        self.auto_save_row = Adw.SwitchRow()
        self.auto_save_row.set_title(_("Auto Save"))
        self.auto_save_row.set_subtitle(_("Automatically save projects while editing"))
        self.auto_save_row.connect('notify::active', self._on_auto_save_changed)
        behavior_group.add(self.auto_save_row)

        # Word wrap
        self.word_wrap_row = Adw.SwitchRow()
        self.word_wrap_row.set_title(_("Word Wrap"))
        self.word_wrap_row.set_subtitle(_("Wrap text to fit the editor width"))
        self.word_wrap_row.connect('notify::active', self._on_word_wrap_changed)
        behavior_group.add(self.word_wrap_row)

        # Show line numbers
        self.line_numbers_row = Adw.SwitchRow()
        self.line_numbers_row.set_title(_("Show Line Numbers"))
        self.line_numbers_row.set_subtitle(_("Display line numbers in the editor"))
        self.line_numbers_row.connect('notify::active', self._on_line_numbers_changed)
        behavior_group.add(self.line_numbers_row)

    def _load_preferences(self):
        """Load preferences from config"""
        # Appearance
        self.dark_theme_row.set_active(self.config.get('use_dark_theme', False))

        # Font
        font_family = self.config.get('font_family', 'Liberation Serif')
        model = self.font_family_row.get_model()
        for i in range(model.get_n_items()):
            if model.get_string(i) == font_family:
                self.font_family_row.set_selected(i)
                break

        self.font_size_row.set_value(self.config.get('font_size', 12))

        # Behavior
        self.auto_save_row.set_active(self.config.get('auto_save', True))
        self.word_wrap_row.set_active(self.config.get('word_wrap', True))
        self.line_numbers_row.set_active(self.config.get('show_line_numbers', True))

    def _on_dark_theme_changed(self, switch, pspec):
        """Handle dark theme toggle"""
        self.config.set('use_dark_theme', switch.get_active())

        # Apply theme immediately
        style_manager = Adw.StyleManager.get_default()
        if switch.get_active():
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

    def _on_font_family_changed(self, combo, pspec):
        """Handle font family change"""
        model = combo.get_model()
        selected_font = model.get_string(combo.get_selected())
        self.config.set('font_family', selected_font)

    def _on_font_size_changed(self, spin, pspec):
        """Handle font size change"""
        self.config.set('font_size', int(spin.get_value()))

    def _on_auto_save_changed(self, switch, pspec):
        """Handle auto save toggle"""
        self.config.set('auto_save', switch.get_active())

    def _on_word_wrap_changed(self, switch, pspec):
        """Handle word wrap toggle"""
        self.config.set('word_wrap', switch.get_active())

    def _on_line_numbers_changed(self, switch, pspec):
        """Handle line numbers toggle"""
        self.config.set('show_line_numbers', switch.get_active())


class WelcomeDialog(Adw.Window):
    """Welcome dialog explaining TAC Writer and CAT technique"""

    __gtype_name__ = 'TacWelcomeDialog'

    def __init__(self, parent, config: Config, **kwargs):
        super().__init__(**kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_resizable(True)
        self.config = config

        # Smaller window size since we removed content
        self.set_default_size(600, 450)

        # Create UI
        self._create_ui()

    def _create_ui(self):
        """Create the welcome dialog UI"""
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # HeaderBar with custom style
        headerbar = Adw.HeaderBar()
        headerbar.set_show_title(False)
        headerbar.add_css_class("flat")

        # Apply custom CSS to reduce header padding
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
        headerbar {
            min-height: 24px;
            padding: 2px 6px;
        }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        main_box.append(headerbar)

        # ScrolledWindow for content
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_vexpand(True)

        # Content container
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content_box.set_margin_top(8)
        content_box.set_margin_bottom(16)
        content_box.set_margin_start(20)
        content_box.set_margin_end(20)

        # Icon and title
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        title_box.set_halign(Gtk.Align.CENTER)

        # App icon
        icon = Gtk.Image.new_from_icon_name("document-edit-symbolic")
        icon.set_pixel_size(56)
        icon.add_css_class("accent")
        title_box.append(icon)

        # Title
        title_label = Gtk.Label()
        title_label.set_markup("<span size='large' weight='bold'>" + _("What is TAC Writer?") + "</span>")
        title_label.set_halign(Gtk.Align.CENTER)
        title_box.append(title_label)

        content_box.append(title_box)

        # Content text
        content_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        # CAT explanation
        cat_label = Gtk.Label()
        cat_label.set_markup("<b>" + _("Continuous Argumentation Technique (TAC in Portuguese):") + "</b>")
        cat_label.set_halign(Gtk.Align.START)
        content_text_box.append(cat_label)

        cat_desc = Gtk.Label()
        cat_desc.set_text(_("Tac Writer is a tool based on the TAC technique (Continued Argumentation Technique) and the Pomodoro method. Developed by Narayan Silva, the TAC technique helps writers develop an idea or explain a concept in an organized manner, separating the paragraph into different stages: introduction, argument, citation, and conclusion."))
        cat_desc.set_wrap(True)
        cat_desc.set_halign(Gtk.Align.START)
        cat_desc.set_justify(Gtk.Justification.LEFT)
        cat_desc.set_max_width_chars(60)
        content_text_box.append(cat_desc)

        # Wiki link section
        wiki_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        wiki_box.set_halign(Gtk.Align.CENTER)
        wiki_box.set_margin_top(16)

        wiki_button = Gtk.Button()
        wiki_button.set_label(_("Learn More - Online Documentation"))
        wiki_button.set_icon_name("help-browser-symbolic")
        wiki_button.add_css_class("suggested-action")
        wiki_button.add_css_class("wiki-help-button")
        wiki_button.set_tooltip_text(_("Access the complete guide and tutorials"))
        wiki_button.connect('clicked', self._on_wiki_clicked)
        wiki_box.append(wiki_button)

        content_text_box.append(wiki_box)
        content_box.append(content_text_box)

        # Separator before switch
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(8)
        content_box.append(separator)

        # Show on startup toggle
        toggle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        toggle_box.set_margin_top(8)

        toggle_label = Gtk.Label()
        toggle_label.set_text(_("Show this dialog on startup"))
        toggle_label.set_hexpand(True)
        toggle_label.set_halign(Gtk.Align.START)
        toggle_box.append(toggle_label)

        self.show_switch = Gtk.Switch()
        self.show_switch.set_active(self.config.get('show_welcome_dialog', True))
        self.show_switch.connect('notify::active', self._on_switch_toggled)
        self.show_switch.set_valign(Gtk.Align.CENTER)
        toggle_box.append(self.show_switch)
        content_box.append(toggle_box)

        # Start button
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.set_margin_top(16)

        start_button = Gtk.Button()
        start_button.set_label(_("Let's Start"))
        start_button.add_css_class("suggested-action")
        start_button.connect('clicked', self._on_start_clicked)
        button_box.append(start_button)

        content_box.append(button_box)

        # Add content_box to ScrolledWindow
        scrolled_window.set_child(content_box)
        main_box.append(scrolled_window)

        # Set the content
        self.set_content(main_box)

    def _on_switch_toggled(self, switch, gparam):
        """Handle switch toggle"""
        self.config.set('show_welcome_dialog', switch.get_active())
        self.config.save()

    def _on_start_clicked(self, button):
        """Handle start button click"""
        self.destroy()
        
    def _on_wiki_clicked(self, button):
        """Handle wiki button click - open external browser"""
        import subprocess
        import webbrowser
        
        wiki_url = "https://github.com/big-comm/comm-tac-writer/wiki"
        
        try:
            # Try to open with default browser
            webbrowser.open(wiki_url)
        except Exception:
            # Fallback: try xdg-open on Linux
            try:
                subprocess.run(['xdg-open', wiki_url], check=False)
            except Exception as e:
                print(f"Could not open wiki URL: {e}")


def AboutDialog(parent):
    """Create and show about dialog"""
    dialog = Adw.AboutWindow()
    dialog.set_transient_for(parent)
    dialog.set_modal(True)

    # Get config instance to access version info
    config = Config()

    # Application information
    dialog.set_application_name(config.APP_NAME)
    dialog.set_application_icon("tac-writer")
    dialog.set_version(config.APP_VERSION)
    dialog.set_developer_name(_(config.APP_DESCRIPTION))
    dialog.set_website(config.APP_WEBSITE)

    # Description
    dialog.set_comments(_(config.APP_DESCRIPTION))

    # License
    dialog.set_license_type(Gtk.License.GPL_3_0)

    # Credits
    dialog.set_developers([
        f"{', '.join(config.APP_DEVELOPERS)} {config.APP_WEBSITE}"
    ])
    dialog.set_designers(config.APP_DESIGNERS)

    dialog.set_copyright(config.APP_COPYRIGHT)

    return dialog

def AboutDialog(parent):
    """Create and show about dialog"""
    dialog = Adw.AboutWindow()
    dialog.set_transient_for(parent)
    dialog.set_modal(True)

    # Get config instance to access version info
    config = Config()

    # Application information
    dialog.set_application_name(config.APP_NAME)
    dialog.set_application_icon("tac-writer")
    dialog.set_version(config.APP_VERSION)
    dialog.set_developer_name(_(config.APP_DESCRIPTION))
    dialog.set_website(config.APP_WEBSITE)

    # Description
    dialog.set_comments(_(config.APP_DESCRIPTION))

    # License
    dialog.set_license_type(Gtk.License.GPL_3_0)

    # Credits
    dialog.set_developers([
        f"{', '.join(config.APP_DEVELOPERS)} {config.APP_WEBSITE}"
    ])
    dialog.set_designers(config.APP_DESIGNERS)

    dialog.set_copyright(config.APP_COPYRIGHT)

    return dialog


class BackupManagerDialog(Adw.Window):
    """Dialog for managing database backups"""

    __gtype_name__ = 'TacBackupManagerDialog'

    __gsignals__ = {
        'database-imported': (GObject.SIGNAL_RUN_FIRST, None, ()),
    }

    def __init__(self, parent, project_manager: ProjectManager, **kwargs):
        super().__init__(**kwargs)
        self.set_title(_("Backup Manager"))
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(700, 500)
        self.set_resizable(True)

        self.project_manager = project_manager
        self.backups_list = []

        self._create_ui()
        self._refresh_backups()

    def _create_ui(self):
        """Create the backup manager UI"""
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(content_box)

        # Header bar
        header_bar = Adw.HeaderBar()
        
        # Close button
        close_button = Gtk.Button()
        close_button.set_label(_("Close"))
        close_button.connect('clicked', lambda x: self.destroy())
        header_bar.pack_start(close_button)

        # Create backup button
        create_backup_button = Gtk.Button()
        create_backup_button.set_label(_("Create Backup"))
        create_backup_button.add_css_class("suggested-action")
        create_backup_button.connect('clicked', self._on_create_backup)
        header_bar.pack_end(create_backup_button)

        # Import button
        import_button = Gtk.Button()
        import_button.set_label(_("Import Database"))
        import_button.connect('clicked', self._on_import_database)
        header_bar.pack_end(import_button)

        content_box.append(header_bar)

        # Main content
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_spacing(16)

        # Status group
        status_group = Adw.PreferencesGroup()
        status_group.set_title(_("Current Database"))
        
        db_info = self.project_manager.get_database_info()
        
        # Database path
        path_row = Adw.ActionRow()
        path_row.set_title(_("Database Location"))
        path_row.set_subtitle(db_info['database_path'])
        status_group.add(path_row)

        # Database stats
        stats_row = Adw.ActionRow()
        stats_row.set_title(_("Statistics"))
        stats_text = _("{} projects, {} MB").format(
            db_info['project_count'],
            round(db_info['database_size_bytes'] / (1024*1024), 2)
        )
        stats_row.set_subtitle(stats_text)
        status_group.add(stats_row)

        main_box.append(status_group)

        # Backups list
        backups_group = Adw.PreferencesGroup()
        backups_group.set_title(_("Available Backups"))
        backups_group.set_description(_("Backups are stored in Documents/TAC Projects/database_backups"))

        # Scrolled window for backups
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(200)

        self.backups_listbox = Gtk.ListBox()
        self.backups_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.backups_listbox.add_css_class("boxed-list")

        scrolled.set_child(self.backups_listbox)
        
        backups_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        backups_box.append(backups_group)
        backups_box.append(scrolled)
        
        main_box.append(backups_box)
        
        scrolled_main = Gtk.ScrolledWindow()
        scrolled_main.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_main.set_child(main_box)
        content_box.append(scrolled_main)

    def _refresh_backups(self):
        """Refresh the backups list"""
        # Clear existing items
        child = self.backups_listbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.backups_listbox.remove(child)
            child = next_child

        # Load backups
        self.backups_list = self.project_manager.list_available_backups()

        if not self.backups_list:
            # Show empty state
            empty_row = Adw.ActionRow()
            empty_row.set_title(_("No backups found"))
            empty_row.set_subtitle(_("Create a backup or import an existing database file"))
            self.backups_listbox.append(empty_row)
            return

        # Add backup rows
        for backup in self.backups_list:
            row = self._create_backup_row(backup)
            self.backups_listbox.append(row)

    def _create_backup_row(self, backup: Dict[str, Any]):
        """Create a row for a backup"""
        row = Adw.ActionRow()
        
        # Title and subtitle
        row.set_title(backup['name'])
        
        size_mb = backup['size'] / (1024 * 1024)
        created_str = backup['created_at'].strftime('%Y-%m-%d %H:%M')
        subtitle = _("{:.1f} MB • {} projects • {}").format(
            size_mb, backup['project_count'], created_str
        )
        row.set_subtitle(subtitle)

        # Status indicator
        if backup['is_valid']:
            status_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            status_icon.set_tooltip_text(_("Valid backup"))
        else:
            status_icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            status_icon.set_tooltip_text(_("Invalid or corrupted backup"))
            status_icon.add_css_class("warning")
            
        row.add_prefix(status_icon)

        # Action buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # Restore button
        if backup['is_valid']:
            restore_button = Gtk.Button()
            restore_button.set_icon_name("document-revert-symbolic")
            restore_button.set_tooltip_text(_("Import this backup"))
            restore_button.add_css_class("flat")
            restore_button.connect('clicked', lambda btn, b=backup: self._on_restore_backup(b))
            button_box.append(restore_button)

        # Delete button
        delete_button = Gtk.Button()
        delete_button.set_icon_name("user-trash-symbolic")
        delete_button.set_tooltip_text(_("Delete backup"))
        delete_button.add_css_class("flat")
        delete_button.add_css_class("destructive-action")
        delete_button.connect('clicked', lambda btn, b=backup: self._on_delete_backup(b))
        button_box.append(delete_button)

        row.add_suffix(button_box)
        return row

    def _on_create_backup(self, button):
        """Handle create backup button"""
        button.set_sensitive(False)
        button.set_label(_("Creating..."))

        def backup_thread():
            backup_path = self.project_manager.create_manual_backup()
            GLib.idle_add(self._backup_created, backup_path, button)

        thread = threading.Thread(target=backup_thread, daemon=True)
        thread.start()

    def _backup_created(self, backup_path, button):
        """Callback when backup is created"""
        button.set_sensitive(True)
        button.set_label(_("Create Backup"))

        if backup_path:
            # Show success toast in parent window
            parent_window = self.get_transient_for()
            if parent_window and hasattr(parent_window, '_show_toast'):
                parent_window._show_toast(_("Backup created successfully"))
            self._refresh_backups()
        else:
            # Show error dialog
            error_dialog = Adw.MessageDialog.new(
                self,
                _("Backup Failed"),
                _("Could not create backup. Check the console for details.")
            )
            error_dialog.add_response("ok", _("OK"))
            error_dialog.present()

        return False

    def _on_import_database(self, button):
        """Handle import database button"""
        file_chooser = Gtk.FileChooserNative.new(
            _("Import Database"),
            self,
            Gtk.FileChooserAction.OPEN,
            _("Import"),
            _("Cancel")
        )

        # Set filter for database files
        filter_db = Gtk.FileFilter()
        filter_db.set_name(_("Database files (*.db)"))
        filter_db.add_pattern("*.db")
        file_chooser.add_filter(filter_db)

        filter_all = Gtk.FileFilter()
        filter_all.set_name(_("All files"))
        filter_all.add_pattern("*")
        file_chooser.add_filter(filter_all)

        file_chooser.connect('response', self._on_import_file_selected)
        file_chooser.show()

    def _on_import_file_selected(self, dialog, response):
        """Handle file selection for import"""
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                backup_path = Path(file.get_path())
                self._confirm_import(backup_path)
        dialog.destroy()

    def _on_restore_backup(self, backup):
        """Handle restore backup button"""
        self._confirm_import(backup['path'])

    def _confirm_import(self, backup_path: Path):
        """Show confirmation dialog for import"""
        # Validate backup first
        if not self.project_manager._validate_backup_file(backup_path):
            error_dialog = Adw.MessageDialog.new(
                self,
                _("Invalid Backup"),
                _("The selected file is not a valid TAC database backup.")
            )
            error_dialog.add_response("ok", _("OK"))
            error_dialog.present()
            return

        # Get backup info
        try:
            with sqlite3.connect(backup_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM projects")
                project_count = cursor.fetchone()[0]
        except:
            project_count = 0

        # Show confirmation
        dialog = Adw.MessageDialog.new(
            self,
            _("Import Database?"),
            _("This will replace your current database with the selected backup.\n\n"
              "The backup contains {} projects.\n\n"
              "Your current database will be backed up before importing.").format(project_count)
        )

        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("import", _("Import"))
        dialog.set_response_appearance("import", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")

        dialog.connect('response', lambda d, r, path=backup_path: self._import_confirmed(d, r, path))
        dialog.present()

    def _import_confirmed(self, dialog, response, backup_path):
        """Handle import confirmation"""
        dialog.destroy()
        
        if response == "import":
            self._perform_import(backup_path)

    def _perform_import(self, backup_path: Path):
        """Perform the database import"""
        # Show loading state
        loading_dialog = Adw.MessageDialog.new(
            self,
            _("Importing Database"),
            _("Please wait while the database is being imported...")
        )
        loading_dialog.present()

        def import_thread():
            success = self.project_manager.import_database(backup_path)
            GLib.idle_add(self._import_finished, success, loading_dialog)

        thread = threading.Thread(target=import_thread, daemon=True)
        thread.start()

    def _import_finished(self, success, loading_dialog):
        """Callback when import is finished"""
        loading_dialog.destroy()

        if success:
            # Show success and emit signal
            success_dialog = Adw.MessageDialog.new(
                self,
                _("Import Successful"),
                _("Database imported successfully. The application will refresh to show the imported projects.")
            )
            success_dialog.add_response("ok", _("OK"))
            
            def on_success_response(dialog, response):
                dialog.destroy()
                self.emit('database-imported')
                self.destroy()
            
            success_dialog.connect('response', on_success_response)
            success_dialog.present()
        else:
            # Show error
            error_dialog = Adw.MessageDialog.new(
                self,
                _("Import Failed"),
                _("Could not import the database. Your current database remains unchanged.")
            )
            error_dialog.add_response("ok", _("OK"))
            error_dialog.present()

        return False

    def _on_delete_backup(self, backup):
        """Handle delete backup button"""
        dialog = Adw.MessageDialog.new(
            self,
            _("Delete Backup?"),
            _("Are you sure you want to delete '{}'?\n\nThis action cannot be undone.").format(backup['name'])
        )

        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")

        dialog.connect('response', lambda d, r, b=backup: self._delete_confirmed(d, r, b))
        dialog.present()

    def _delete_confirmed(self, dialog, response, backup):
        """Handle delete confirmation"""
        if response == "delete":
            success = self.project_manager.delete_backup(backup['path'])
            if success:
                self._refresh_backups()
        dialog.destroy()
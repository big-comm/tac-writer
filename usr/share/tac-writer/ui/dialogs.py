"""
TAC UI Dialogs
Dialog windows for the TAC application using GTK4 and libadwaita
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GObject, Gio, Gdk, Pango, GLib

import threading
from pathlib import Path
from datetime import datetime

from core.models import Project, DEFAULT_TEMPLATES, Paragraph
from core.services import ProjectManager, ExportService
from core.config import Config
from utils.helpers import ValidationHelper, FileHelper
from utils.i18n import _


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
        self.set_default_size(600, 700) # Increased size significantly
        self.set_resizable(True) # Allow resizing

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
        scrolled.set_min_content_height(600) # Ensure minimum height
        content_box.append(scrolled)

        # Main content
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_spacing(32) # Increased spacing between sections
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
        self.name_entry.set_text(_("My New Project")) # Default name
        self.name_entry.set_size_request(200, -1)
        self.name_entry.connect('changed', self._on_name_changed)
        self.name_entry.connect('activate', self._on_name_activate) # Enter key support

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

        # Description section (separate)
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
        desc_scrolled.set_size_request(-1, 120) # Increased height for description

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
        self.template_combo.set_active(0) # Select first template by default

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

class FormatDialog(Adw.Window):
    """Dialog for text formatting options"""

    __gtype_name__ = 'TacFormatDialog'

    def __init__(self, parent, paragraphs: list = None, **kwargs):
        super().__init__(**kwargs)
        self.set_title(_("Format Text"))
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(500, 600) # Increased height
        self.set_resizable(True)

        self.paragraphs = paragraphs or [] # List of paragraphs to be formatted

        # If we have paragraphs, use the first one's formatting as default
        if self.paragraphs:
            self.formatting = self.paragraphs[0].formatting.copy()
        else:
            self.formatting = {
                'font_family': 'Liberation Sans',
                'font_size': 12,
                'bold': False,
                'italic': False,
                'underline': False,
                'line_spacing': 1.5,
                'indent_first_line': 1.25,
                'indent_left': 0.0,
                'indent_right': 0.0,
                'alignment': 'left'
            }

        # Create UI
        self._create_ui()
        self._load_current_formatting()

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

        apply_button = Gtk.Button()
        apply_button.set_label(_("Apply"))
        apply_button.add_css_class("suggested-action")
        apply_button.connect('clicked', self._on_apply_clicked)
        header_bar.pack_end(apply_button)

        content_box.append(header_bar)

        # Preferences page
        prefs_page = Adw.PreferencesPage()
        content_box.append(prefs_page)

        # Font group
        font_group = Adw.PreferencesGroup()
        font_group.set_title(_("Font"))
        prefs_page.add(font_group)

        # Font family
        self.font_row = Adw.ComboRow()
        self.font_row.set_title(_("Font Family"))
        font_model = Gtk.StringList()

        # Get system fonts
        try:
            # Method 1: Try PangoCairo
            gi.require_version('PangoCairo', '1.0')
            from gi.repository import PangoCairo
            font_map = PangoCairo.font_map_get_default()
            families = font_map.list_families()
        except:
            try:
                # Method 2: Try Pango context
                context = Pango.Context()
                font_map = context.get_font_map()
                families = font_map.list_families()
            except:
                try:
                    # Method 3: Use fontconfig command
                    import subprocess
                    result = subprocess.run(['fc-list', ':', 'family'], capture_output=True, text=True)
                    if result.returncode == 0:
                        font_names = set()
                        for line in result.stdout.strip().split('\n'):
                            if line:
                                family = line.split(',')[0].strip()
                                font_names.add(family)
                        font_names = sorted(list(font_names))
                        for font_name in font_names:
                            font_model.append(font_name)
                        families = None # Skip the normal processing below
                    else:
                        families = []
                except:
                    families = []

        # Process Pango families if we got them
        if families is not None:
            font_names = []
            for family in families:
                font_names.append(family.get_name())
            font_names.sort()
            for font_name in font_names:
                font_model.append(font_name)

        # If still no fonts, use fallback
        if font_model.get_n_items() == 0:
            print("Using fallback fonts in FormatDialog")
            basic_fonts = ["Liberation Sans", "Liberation Serif", "DejaVu Sans", "Ubuntu", "Cantarell"]
            for font in basic_fonts:
                font_model.append(font)

        self.font_row.set_model(font_model)
        font_group.add(self.font_row)

        # Font size
        size_adjustment = Gtk.Adjustment(value=12, lower=8, upper=72, step_increment=1, page_increment=2)
        self.size_row = Adw.SpinRow()
        self.size_row.set_title(_("Font Size"))
        self.size_row.set_adjustment(size_adjustment)
        font_group.add(self.size_row)

        # Style group
        style_group = Adw.PreferencesGroup()
        style_group.set_title(_("Style"))
        prefs_page.add(style_group)

        # Bold
        self.bold_row = Adw.SwitchRow()
        self.bold_row.set_title(_("Bold"))
        style_group.add(self.bold_row)

        # Italic
        self.italic_row = Adw.SwitchRow()
        self.italic_row.set_title(_("Italic"))
        style_group.add(self.italic_row)

        # Underline
        self.underline_row = Adw.SwitchRow()
        self.underline_row.set_title(_("Underline"))
        style_group.add(self.underline_row)

        # Spacing group
        spacing_group = Adw.PreferencesGroup()
        spacing_group.set_title(_("Spacing & Alignment"))
        prefs_page.add(spacing_group)

        # Line spacing
        line_spacing_adj = Gtk.Adjustment(value=1.5, lower=1.0, upper=3.0, step_increment=0.1, page_increment=0.5)
        self.line_spacing_row = Adw.SpinRow()
        self.line_spacing_row.set_title(_("Line Spacing"))
        self.line_spacing_row.set_subtitle(_("Space between lines"))
        self.line_spacing_row.set_adjustment(line_spacing_adj)
        self.line_spacing_row.set_digits(1)
        spacing_group.add(self.line_spacing_row)

        # First line indent
        indent_adj = Gtk.Adjustment(value=1.25, lower=0.0, upper=5.0, step_increment=0.1, page_increment=0.5)
        self.indent_row = Adw.SpinRow()
        self.indent_row.set_title(_("First Line Indent (cm)"))
        self.indent_row.set_subtitle(_("Indentation of the first line"))
        self.indent_row.set_adjustment(indent_adj)
        self.indent_row.set_digits(1)
        spacing_group.add(self.indent_row)

        # Left margin
        left_margin_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=10.0, step_increment=0.1, page_increment=0.5)
        self.left_margin_row = Adw.SpinRow()
        self.left_margin_row.set_title(_("Left Margin (cm)"))
        self.left_margin_row.set_subtitle(_("Left side margin"))
        self.left_margin_row.set_adjustment(left_margin_adj)
        self.left_margin_row.set_digits(1)
        spacing_group.add(self.left_margin_row)

        # Right margin
        right_margin_adj = Gtk.Adjustment(value=0.0, lower=0.0, upper=10.0, step_increment=0.1, page_increment=0.5)
        self.right_margin_row = Adw.SpinRow()
        self.right_margin_row.set_title(_("Right Margin (cm)"))
        self.right_margin_row.set_subtitle(_("Right side margin"))
        self.right_margin_row.set_adjustment(right_margin_adj)
        self.right_margin_row.set_digits(1)
        spacing_group.add(self.right_margin_row)

        # Text alignment
        self.alignment_row = Adw.ComboRow()
        self.alignment_row.set_title(_("Text Alignment"))
        alignment_model = Gtk.StringList()
        alignments = [_("Left"), _("Center"), _("Right"), _("Justify")]
        for alignment in alignments:
            alignment_model.append(alignment)
        self.alignment_row.set_model(alignment_model)
        spacing_group.add(self.alignment_row)

    def _load_current_formatting(self):
        """Load current formatting into controls"""
        if not self.formatting:
            return

        # Font family
        font_family = self.formatting.get('font_family', 'Liberation Sans')
        model = self.font_row.get_model()
        for i in range(model.get_n_items()):
            if model.get_string(i) == font_family:
                self.font_row.set_selected(i)
                break

        # Font size
        self.size_row.set_value(self.formatting.get('font_size', 12))

        # Style
        self.bold_row.set_active(self.formatting.get('bold', False))
        self.italic_row.set_active(self.formatting.get('italic', False))
        self.underline_row.set_active(self.formatting.get('underline', False))

        # Spacing
        self.line_spacing_row.set_value(self.formatting.get('line_spacing', 1.5))
        self.indent_row.set_value(self.formatting.get('indent_first_line', 1.25))
        self.left_margin_row.set_value(self.formatting.get('indent_left', 0.0))
        self.right_margin_row.set_value(self.formatting.get('indent_right', 0.0))

        # Alignment
        alignment = self.formatting.get('alignment', 'left')
        alignment_map = {'left': 0, 'center': 1, 'right': 2, 'justify': 3}
        self.alignment_row.set_selected(alignment_map.get(alignment, 0))

    def _on_apply_clicked(self, button):
        """Apply formatting changes to all paragraphs"""
        # Update formatting dictionary
        model = self.font_row.get_model()
        selected_font = model.get_string(self.font_row.get_selected())

        # Map alignment
        alignment_names = ['left', 'center', 'right', 'justify']
        selected_alignment = alignment_names[self.alignment_row.get_selected()]

        new_formatting = {
            'font_family': selected_font,
            'font_size': int(self.size_row.get_value()),
            'bold': self.bold_row.get_active(),
            'italic': self.italic_row.get_active(),
            'underline': self.underline_row.get_active(),
            'line_spacing': self.line_spacing_row.get_value(),
            'indent_first_line': self.indent_row.get_value(),
            'indent_left': self.left_margin_row.get_value(),
            'indent_right': self.right_margin_row.get_value(),
            'alignment': selected_alignment
        }

        # Apply to all paragraphs
        for paragraph in self.paragraphs:
            paragraph.update_formatting(new_formatting)

        # Notify main window to update view
        if hasattr(self.get_transient_for(), '_refresh_paragraph_formatting'):
            self.get_transient_for()._refresh_paragraph_formatting()

        self.destroy()

class ExportDialog(Adw.Window):
    """Dialog for exporting projects"""

    __gtype_name__ = 'TacExportDialog'

    def __init__(self, parent, project: Project, export_service: ExportService, **kwargs):
        super().__init__(**kwargs)
        self.set_title(_("Export Project"))
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(550, 500) # Better proportions
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
        self.format_row.set_selected(0) # ODT as default
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

        # Initialize with default location
        from pathlib import Path
        default_location = Path.home() / 'Documents'
        self.selected_location = default_location
        self.location_row.set_subtitle(str(default_location))

    def _on_choose_location(self, button):
        """Handle location selection"""
        # Create file chooser dialog
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
        # Disable button to avoid multiple clicks
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

        # Execute export in separate thread
        def export_thread():
            try:
                # Export project
                success = self.export_service.export_project(
                    self.project,
                    str(output_path),
                    format_code
                )
                
                # Return to main thread to update UI
                GLib.idle_add(self._export_finished, success, str(output_path), None)
                
            except Exception as e:
                # Return to main thread to show error
                GLib.idle_add(self._export_finished, False, str(output_path), str(e))
        
        # Start export thread
        thread = threading.Thread(target=export_thread)
        thread.daemon = True
        thread.start()
    
    def _export_finished(self, success, output_path, error_message):
        """Callback executed in main thread when export finishes"""
        # Re-enable button first (for both cases)
        header = self.get_titlebar()
        if header:
            # Simple method: get the last button of the header (which is the export button)
            child = header.get_last_child()
            while child:
                if isinstance(child, Gtk.Button):
                    child.set_sensitive(True)
                    child.set_label(_("Export"))
                    break
                child = child.get_prev_sibling()
        
        if success:
            # Show success message
            success_dialog = Adw.MessageDialog.new(
                self,
                _("Export Successful"),
                _("Project exported to:\n{}").format(output_path)
            )
            success_dialog.add_response("ok", _("OK"))
            
            # Connect callback to only close AFTER user clicks OK
            def on_success_response(dialog, response):
                dialog.destroy()
                self.destroy()  # Only destroy AFTER user response
            
            success_dialog.connect('response', on_success_response)
            success_dialog.present()
            
            # DON'T call self.destroy() here!
        else:
            # Show error message
            error_msg = error_message if error_message else _("An error occurred while exporting the project.")
            error_dialog = Adw.MessageDialog.new(
                self,
                _("Export Failed"),
                error_msg
            )
            error_dialog.add_response("ok", _("OK"))
            error_dialog.present()
        
        return False  # Remove from idle callbacks

class PreferencesDialog(Adw.PreferencesWindow):
    """Preferences dialog"""

    __gtype_name__ = 'TacPreferencesDialog'

    def __init__(self, parent, config: Config, **kwargs):
        super().__init__(**kwargs)
        self.set_title(_("Preferences"))
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(700, 600) # Larger for preferences
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
        try:
            # Method 1: Try PangoCairo
            gi.require_version('PangoCairo', '1.0')
            from gi.repository import PangoCairo
            font_map = PangoCairo.font_map_get_default()
            families = font_map.list_families()
        except:
            try:
                # Method 2: Try Pango context
                context = Pango.Context()
                font_map = context.get_font_map()
                families = font_map.list_families()
            except:
                try:
                    # Method 3: Use fontconfig command
                    import subprocess
                    result = subprocess.run(['fc-list', ':', 'family'], capture_output=True, text=True)
                    if result.returncode == 0:
                        font_names = set()
                        for line in result.stdout.strip().split('\n'):
                            if line:
                                family = line.split(',')[0].strip()
                                font_names.add(family)
                        font_names = sorted(list(font_names))
                        for font_name in font_names:
                            font_model.append(font_name)
                        families = None # Skip the normal processing below
                    else:
                        families = []
                except:
                    families = []

        # Process Pango families if we got them
        if families is not None:
            font_names = []
            for family in families:
                font_names.append(family.get_name())
            font_names.sort()
            for font_name in font_names:
                font_model.append(font_name)

        # If still no fonts, use fallback
        if font_model.get_n_items() == 0:
            print("Using fallback fonts")
            basic_fonts = ["Liberation Sans", "Liberation Serif", "DejaVu Sans", "Ubuntu", "Cantarell"]
            for font in basic_fonts:
                font_model.append(font)

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
        font_family = self.config.get('font_family', 'Liberation Sans')
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

        # Calculate size based on screen
        display = Gdk.Display.get_default()
        monitor = display.get_monitors().get_item(0)
        geometry = monitor.get_geometry()
        
        # Use 70% of screen width and 80% of screen height, with limits
        width = min(800, int(geometry.width * 0.7))
        height = min(600, int(geometry.height * 0.8))
        
        self.set_default_size(width, height)

        # Create UI
        self._create_ui()

    def _create_ui(self):
        """Create the welcome dialog UI"""
        # Main container
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

        # Content container (now inside ScrolledWindow)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)  # Reduced from 12
        content_box.set_margin_top(8)      # Reduced from 12
        content_box.set_margin_bottom(16)  # Reduced from 24
        content_box.set_margin_start(20)   # Reduced from 24
        content_box.set_margin_end(20)     # Reduced from 24

        # Icon and title
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)  # Reduced from 8
        title_box.set_halign(Gtk.Align.CENTER)

        # App icon
        icon = Gtk.Image.new_from_icon_name("document-edit-symbolic")
        icon.set_pixel_size(56)  # Reduced from 64
        icon.add_css_class("accent")
        title_box.append(icon)

        # Title
        title_label = Gtk.Label()
        title_label.set_markup("<span size='large' weight='bold'>" + _("What is TAC Writer?") + "</span>")
        title_label.set_halign(Gtk.Align.CENTER)
        title_box.append(title_label)

        content_box.append(title_box)

        # Content text
        content_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)  # Reduced from 16

        # CAT explanation
        cat_label = Gtk.Label()
        cat_label.set_markup("<b>" + _("Continuous Argumentation Technique (CAT, TAC in Portuguese):") + "</b>")
        cat_label.set_halign(Gtk.Align.START)
        content_text_box.append(cat_label)

        cat_desc = Gtk.Label()
        cat_desc.set_text(_("CAT consists of paragraphs that interact with each other. The idea is that some topics, when explained, cannot be concluded with just one paragraph. This is a technique that aims to organize a text and make it easier to understand."))
        cat_desc.set_wrap(True)
        cat_desc.set_halign(Gtk.Align.START)
        cat_desc.set_justify(Gtk.Justification.LEFT)
        cat_desc.set_max_width_chars(60)
        content_text_box.append(cat_desc)

        # Structure explanation
        structure_label = Gtk.Label()
        structure_label.set_markup("<b>" + _("This is the writing structure:") + "</b>")
        structure_label.set_halign(Gtk.Align.START)
        structure_label.set_margin_top(8)
        content_text_box.append(structure_label)

        # Structure list - More compact layout
        structure_text = _("• <b>Introduction:</b> a sentence at the beginning of the paragraph that summarizes the topic that will be addressed.\n• <b>Argumentation:</b> development of the topic.\n• <b>Quote:</b> quote that supports the argument.\n• <b>Argumentative Resumption:</b> beginning of the next paragraph that indicates a resumption of the argument from the previous paragraph.\n• <b>Conclusion:</b> closing of the idea presented.")

        structure_items_label = Gtk.Label()
        structure_items_label.set_markup(structure_text)
        structure_items_label.set_wrap(True)
        structure_items_label.set_halign(Gtk.Align.START)
        structure_items_label.set_justify(Gtk.Justification.LEFT)
        structure_items_label.set_margin_start(12)
        content_text_box.append(structure_items_label)

        content_box.append(content_text_box)

        # Separator before switch
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(8)  # Reduced from 12
        content_box.append(separator)

        # Show on startup toggle
        toggle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        toggle_box.set_margin_top(8)  # Reduced from 12

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

        # Let's Start button
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.set_margin_top(16)  # Reduced from 24

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

def AboutDialog(parent):
    """Create and show about dialog"""
    dialog = Adw.AboutWindow()
    dialog.set_transient_for(parent)
    dialog.set_modal(True)

    # Application information
    dialog.set_application_name("TAC")
    dialog.set_application_icon("com.github.tac")
    dialog.set_version("1.0.0")
    dialog.set_developer_name(_("TAC Development Team"))
    dialog.set_website("https://github.com/big-comm/comm-tac-writer")
    # dialog.set_issue_url("https://github.com/big-comm/comm-tac-writer/issues")

    # Description
    dialog.set_comments(_("Continuous Argumentation Technique - Academic Writing Assistant"))

    # License
    dialog.set_license_type(Gtk.License.GPL_3_0)

    # Credits
    dialog.set_developers([
        _("Main Developer") + " https://github.com/big-comm/comm-tac-writer"
    ])
    dialog.set_designers([
        _("Design Team")
    ])

    dialog.set_copyright("© 2025 " + _("TAC Development Team"))

    return dialog
"""
TAC UI Components
Reusable UI components for the TAC application
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

# Try to load PyGTKSpellcheck
try:
    import gtkspellcheck
    SPELL_CHECK_AVAILABLE = True
    print("PyGTKSpellcheck available - spell checking enabled")
except ImportError:
    SPELL_CHECK_AVAILABLE = False
    print("PyGTKSpellcheck not available - spell checking disabled")

from gi.repository import Gtk, Adw, GObject, Gdk, GLib
from core.models import Paragraph, ParagraphType, DEFAULT_TEMPLATES
from core.services import ProjectManager
from utils.helpers import TextHelper, FormatHelper
from utils.i18n import _

class PomodoroTimer(GObject.Object):
    """Timer Pomodoro para ajudar na concentração durante a escrita"""
    
    __gtype_name__ = 'TacPomodoroTimer'
    
    __gsignals__ = {
        'timer-finished': (GObject.SIGNAL_RUN_FIRST, None, (str,)), # Tipo: work/break
        'timer-tick': (GObject.SIGNAL_RUN_FIRST, None, (int,)), # Segundos restantes
        'session-changed': (GObject.SIGNAL_RUN_FIRST, None, (int, str)), # Sessão, tipo
    }
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Estado do timer
        self.current_session = 1
        self.is_running = False
        self.is_work_time = True # True = trabalho, False = descanso
        self.timer_id = None
        
        # Tempos em segundos
        self.work_duration = 25 * 60 # 25 minutos
        self.short_break_duration = 5 * 60 # 5 minutos
        self.long_break_duration = 15 * 60 # 15 minutos
        self.max_sessions = 4
        
        # Tempo restante atual
        self.time_remaining = self.work_duration
        
        print("PomodoroTimer inicializado")
    
    def start_timer(self):
        """Inicia o timer"""
        if not self.is_running:
            self.is_running = True
            self._start_countdown()
            print(f"Timer iniciado - Sessão {self.current_session}, {'Trabalho' if self.is_work_time else 'Descanso'}, Tempo: {self.time_remaining}")
    
    def stop_timer(self):
        """Para o timer"""
        if self.is_running:
            self.is_running = False
            if self.timer_id:
                GLib.source_remove(self.timer_id)
                self.timer_id = None
            print("Timer parado")
    
    def reset_timer(self):
        """Reseta o timer para o estado inicial"""
        self.stop_timer()
        self.current_session = 1
        self.is_work_time = True
        self.time_remaining = self.work_duration
        self.emit('session-changed', self.current_session, 'work')
        print("Timer resetado")
    
    def _start_countdown(self):
        """Inicia a contagem regressiva"""
        if self.timer_id:
            GLib.source_remove(self.timer_id)
        self.timer_id = GLib.timeout_add(1000, self._countdown_tick)
    
    def _countdown_tick(self):
        """Executa a cada segundo da contagem regressiva"""
        if not self.is_running:
            return False
        
        self.time_remaining -= 1
        
        # Verificar se terminou ANTES de emitir timer-tick
        if self.time_remaining <= 0:
            # NÃO emitir timer-tick quando o timer termina
            # Isso evita a race condition com _update_time_display
            self._timer_finished()
            return False
        
        # Só emitir timer-tick se o timer continuar rodando
        self.emit('timer-tick', self.time_remaining)
        return True
    
    def _timer_finished(self):
        """Chamado quando o timer termina"""
        # Parar o timer atual
        self.is_running = False
        if self.timer_id:
            GLib.source_remove(self.timer_id)
            self.timer_id = None
        
        if self.is_work_time:
            # Acabou período de trabalho, configurar descanso
            print(f"Trabalho da sessão {self.current_session} terminado")
            self.is_work_time = False
            
            # Determinar duração do descanso
            if self.current_session >= self.max_sessions:
                # Descanso longo após 4ª sessão
                self.time_remaining = self.long_break_duration
                print(f"Configurando descanso longo: {self.long_break_duration} segundos")
            else:
                # Descanso curto
                self.time_remaining = self.short_break_duration
                print(f"Configurando descanso curto: {self.short_break_duration} segundos")
            
            # DEBUG: Imprimir estado após mudanças
            print(f"Estado após transição: is_work_time={self.is_work_time}, time_remaining={self.time_remaining}")
            
            # Emitir sinais na ordem correta
            self.emit('timer-finished', 'work')
            self.emit('session-changed', self.current_session, 'break')
            
        else:
            # Acabou período de descanso
            print(f"Descanso da sessão {self.current_session} terminado")
            self.emit('timer-finished', 'break')
            
            if self.current_session >= self.max_sessions:
                # Completou todas as sessões - resetar tudo
                print("Pomodoro completo! Todas as 4 sessões foram finalizadas.")
                self.current_session = 1
                self.is_work_time = True
                self.time_remaining = self.work_duration
                self.emit('session-changed', self.current_session, 'work')
            else:
                # Próxima sessão de trabalho
                self.current_session += 1
                self.is_work_time = True
                self.time_remaining = self.work_duration
                self.emit('session-changed', self.current_session, 'work')
                print(f"Próxima sessão: {self.current_session}, tempo: {self.time_remaining}")
    
    def get_time_string(self):
        """Retorna o tempo formatado como string MM:SS"""
        # Garantir que nunca seja negativo
        time_to_display = max(0, self.time_remaining)
        minutes = time_to_display // 60
        seconds = time_to_display % 60
        return f"{minutes:02d}:{seconds:02d}"
    
    def get_session_info(self):
        """Retorna informações da sessão atual"""
        if self.is_work_time:
            return {
                'title': _("Session {}").format(self.current_session),
                'type': 'work',
                'session': self.current_session
            }
        else:
            if self.current_session >= self.max_sessions:
                return {
                    'title': _("Long Break"),
                    'type': 'long_break',
                    'session': self.current_session
                }
            else:
                return {
                    'title': _("Rest Time"),
                    'type': 'short_break',
                    'session': self.current_session
                }



class PomodoroDialog(Adw.Window):
    """Dialog do timer Pomodoro"""
    
    def __init__(self, parent, timer, **kwargs):
        super().__init__(**kwargs)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_title(_("Pomodoro Timer"))
        self.set_default_size(400, 300)
        self.set_resizable(False)
        
        self.timer = timer
        self.parent_window = parent
        
        # Conectar sinais do timer
        timer_id1 = self.timer.connect('timer-tick', self._on_timer_tick)
        timer_id2 = self.timer.connect('timer-finished', self._on_timer_finished)
        timer_id3 = self.timer.connect('session-changed', self._on_session_changed)
        
        print(f"DEBUG: Conectado aos sinais - IDs: {timer_id1}, {timer_id2}, {timer_id3}")
        
        self._setup_ui()
        self._update_display()
        
        # Conectar sinal de fechamento
        self.connect('close-request', self._on_close_request)
    
    def _setup_ui(self):
        """Configura a interface do usuário"""
        # Container principal
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)
        
        # Header com título da sessão
        self.session_label = Gtk.Label()
        self.session_label.add_css_class('title-1')
        self.session_label.set_halign(Gtk.Align.CENTER)
        main_box.append(self.session_label)
        
        # Display do tempo
        self.time_label = Gtk.Label()
        self.time_label.add_css_class('display-1')
        self.time_label.set_halign(Gtk.Align.CENTER)
        main_box.append(self.time_label)
        
        # Botões de controle
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)
        
        # Botão Start/Stop
        self.start_stop_button = Gtk.Button()
        self.start_stop_button.add_css_class('suggested-action')
        self.start_stop_button.connect('clicked', self._on_start_stop_clicked)
        button_box.append(self.start_stop_button)
        
        # Botão Reset
        self.reset_button = Gtk.Button(label=_("Reset"))
        self.reset_button.add_css_class('destructive-action')
        self.reset_button.connect('clicked', self._on_reset_clicked)
        button_box.append(self.reset_button)
        
        # Botão Close (minimizar)
        self.close_button = Gtk.Button(label=_("Minimize"))
        self.close_button.connect('clicked', self._on_minimize_clicked)
        button_box.append(self.close_button)
        
        main_box.append(button_box)
        
        # Adicionar ao window
        self.set_content(main_box)
        
        # Atualizar estado inicial dos botões
        self._update_buttons()
    
    def _update_display(self):
        """Atualiza o display do dialog com informações atuais do timer"""
        session_info = self.timer.get_session_info()
        time_str = self.timer.get_time_string()
        
        print(f"DEBUG: _update_display chamado")
        print(f"DEBUG: session_info = {session_info}")
        print(f"DEBUG: time_str = {time_str}")
        print(f"DEBUG: timer.is_work_time = {self.timer.is_work_time}")
        print(f"DEBUG: timer.time_remaining = {self.timer.time_remaining}")
        
        self.session_label.set_text(session_info['title'])
        self.time_label.set_text(time_str)
    
    def _force_display_update(self):
        """Força atualização completa do display"""
        print("DEBUG: Forçando atualização do display")
        
        # Obter informações atuais do timer
        session_info = self.timer.get_session_info()
        time_str = self.timer.get_time_string()
        
        print(f"DEBUG: session_info obtido: {session_info}")
        print(f"DEBUG: time_str obtido: {time_str}")
        
        # Atualizar labels diretamente
        self.session_label.set_text(session_info['title'])
        self.time_label.set_text(time_str)
        
        # Forçar redesenho da interface
        self.session_label.queue_draw()
        self.time_label.queue_draw()
        self.queue_draw()
        
        print(f"DEBUG: Labels atualizados - session: '{session_info['title']}', time: '{time_str}'")
        
        return False  # Remove from idle queue
    
    def _update_buttons(self):
        """Atualiza o estado dos botões"""
        if self.timer.is_running:
            self.start_stop_button.set_label(_("Stop"))
            self.start_stop_button.remove_css_class('suggested-action')
            self.start_stop_button.add_css_class('destructive-action')
        else:
            self.start_stop_button.set_label(_("Start"))
            self.start_stop_button.remove_css_class('destructive-action')
            self.start_stop_button.add_css_class('suggested-action')
    
    def _on_timer_tick(self, timer, time_remaining):
        """Atualiza apenas o tempo durante a execução"""
        if time_remaining > 0:  # Só atualizar se ainda há tempo
            time_str = self.timer.get_time_string()
            self.time_label.set_text(time_str)
    
    def _on_timer_finished(self, timer, timer_type):
        """Handle timer finished - mostra a janela novamente"""
        print(f"DEBUG: Dialog received timer-finished signal: {timer_type}")
        print(f"DEBUG: Timer state - is_work_time: {timer.is_work_time}, time_remaining: {timer.time_remaining}")
        
        # Forçar atualização imediata do display
        GLib.idle_add(self._force_display_update)
        GLib.idle_add(self._show_timer_finished, timer_type)
    
    def _on_session_changed(self, timer, session, session_type):
        """Handle session change - ESTE É O MÉTODO CRÍTICO"""
        print(f"DEBUG: Session changed - session: {session}, type: {session_type}")
        print(f"DEBUG: Timer state na mudança - is_work_time: {timer.is_work_time}, time_remaining: {timer.time_remaining}")
        
        # FORÇAR atualização imediata do display
        GLib.idle_add(self._force_display_update)
        GLib.idle_add(self._update_buttons)
    
    def _show_timer_finished(self, timer_type):
        """Mostra a janela quando o timer termina"""
        print(f"DEBUG: Mostrando janela para timer tipo: {timer_type}")
        
        # Forçar atualização do display antes de mostrar
        self._force_display_update()
        self._update_buttons()
        
        # Mostrar a janela
        self.present()
        
        # Opcional: Reproduzir som de notificação
        # self._play_notification_sound()
        
        return False  # Remove from idle queue
    
    def _on_start_stop_clicked(self, button):
        """Handle do botão Start/Stop"""
        if self.timer.is_running:
            self.timer.stop_timer()
        else:
            self.timer.start_timer()
        
        self._update_buttons()
    
    def _on_reset_clicked(self, button):
        """Handle do botão Reset"""
        self.timer.reset_timer()
        self._force_display_update()
        self._update_buttons()
    
    def _on_minimize_clicked(self, button):
        """Handle do botão Minimize"""
        self.set_visible(False)
    
    def _on_close_request(self, window):
        """Handle do fechamento da janela"""
        # Não destruir a janela, apenas esconder
        self.set_visible(False)
        return True  # Previne destruição da janela
    
    def show_dialog(self):
        """Mostra o dialog"""
        self._force_display_update()
        self._update_buttons()
        self.present()



class SpellCheckHelper:
    """Helper class for spell checking functionality using PyGTKSpellcheck"""

    def __init__(self, config=None):
        self.config = config
        self.available_languages = []
        self.spell_checkers = {}
        self._load_available_languages()

    def _load_available_languages(self):
        """Load available spell check languages"""
        if not SPELL_CHECK_AVAILABLE:
            return

        try:
            import enchant
            self.available_languages = []
            for lang in ['pt_BR', 'en_US', 'en_GB', 'es_ES', 'fr_FR', 'de_DE', 'it_IT']:
                try:
                    if enchant.dict_exists(lang):
                        self.available_languages.append(lang)
                except:
                    pass

            print(f"Available spell check languages: {self.available_languages}")
        except ImportError as e:
            print(f"Error loading spell check languages: {e}")
            self.available_languages = ['pt_BR', 'en_US', 'es_ES', 'fr_FR', 'de_DE']

    def setup_spell_check(self, text_view, language=None):
        """Setup spell checking for a TextView using PyGTKSpellcheck"""
        if not SPELL_CHECK_AVAILABLE:
            return None

        try:
            if language:
                spell_language = language
            elif self.config:
                spell_language = self.config.get_spell_check_language()
            else:
                spell_language = 'pt_BR'

            print(f"Setting up spell check with language: {spell_language}")

            spell_checker = gtkspellcheck.SpellChecker(text_view, language=spell_language)

            checker_id = id(text_view)
            self.spell_checkers[checker_id] = spell_checker

            print(f"✓ Spell check setup successful for TextView with language: {spell_language}")
            return spell_checker

        except Exception as e:
            print(f"✗ Error setting up spell check: {e}")
            return None

    def enable_spell_check(self, text_view, enabled=True):
        """Enable or disable spell checking for a TextView"""
        if not SPELL_CHECK_AVAILABLE:
            return

        try:
            checker_id = id(text_view)
            spell_checker = self.spell_checkers.get(checker_id)

            if spell_checker:
                if enabled:
                    spell_checker.enable()
                else:
                    spell_checker.disable()
                print(f"✓ Spell check {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            print(f"✗ Error toggling spell check: {e}")

        return

class WelcomeView(Gtk.Box):
    """Welcome view shown when no project is open"""

    __gtype_name__ = 'TacWelcomeView'

    __gsignals__ = {
        'create-project': (GObject.SIGNAL_RUN_FIRST, None, (str,)),
        'open-project': (GObject.SIGNAL_RUN_FIRST, None, (object,)),
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)
        self.set_spacing(24)

        # Main welcome content
        self._create_welcome_content()
        # Template selection
        self._create_template_section()
        # Recent projects (if any)
        self._create_recent_section()

    def _create_welcome_content(self):
        """Create main welcome content"""
        # App icon and title
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content_box.set_halign(Gtk.Align.CENTER)

        # Icon
        icon = Gtk.Image.new_from_icon_name("document-edit-symbolic")
        icon.set_pixel_size(96)
        icon.add_css_class("welcome-icon")
        content_box.append(icon)

        # Title
        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>" + _("Welcome to TAC") + "</span>")
        title.set_halign(Gtk.Align.CENTER)
        content_box.append(title)

        # Subtitle
        subtitle = Gtk.Label()
        subtitle.set_markup("<span size='medium'>" + _("Continuous Argumentation Technique") + "</span>")
        subtitle.set_halign(Gtk.Align.CENTER)
        subtitle.add_css_class("dim-label")
        content_box.append(subtitle)

        # Description
        description = Gtk.Label()
        description.set_text(_("Create structured academic texts with guided paragraph types"))
        description.set_halign(Gtk.Align.CENTER)
        description.set_wrap(True)
        description.set_max_width_chars(50)
        content_box.append(description)

        self.append(content_box)

        # Note
        note = Gtk.Label()
        note.set_markup("<span size='small'><i>" + _("Note:") + " " + _("exporting to ODT might require some adjustment in your Office Suite.") + "</i></span>")
        note.set_halign(Gtk.Align.CENTER)
        content_box.append(note)

        # Tips
        tips = Gtk.Label()
        tips.set_markup("<span size='small'><i>" + _("Tip:") + " " + _("for direct quotes with less than 4 lines, use argument box.") + "</i></span>")
        tips.set_halign(Gtk.Align.CENTER)
        content_box.append(tips)

    def _create_template_section(self):
        """Create template selection section"""
        template_group = Adw.PreferencesGroup()
        template_group.set_title(_("Start Writing"))
        template_group.set_description(_("Choose a template to get started"))

        # Template cards
        for template in DEFAULT_TEMPLATES:
            row = Adw.ActionRow()
            row.set_title(template.name)
            row.set_subtitle(template.description)

            # Start button
            start_button = Gtk.Button()
            start_button.set_label(_("Start"))
            start_button.add_css_class("suggested-action")
            start_button.set_valign(Gtk.Align.CENTER)
            start_button.connect('clicked', lambda btn, tmpl=template.name: self.emit('create-project', tmpl))
            row.add_suffix(start_button)

            template_group.add(row)

        self.append(template_group)

    def _create_recent_section(self):
        """Create recent projects section"""
        # TODO: Implement recent projects display
        # This would show recently opened projects
        pass

class ProjectListWidget(Gtk.Box):
    """Widget for displaying and selecting projects"""

    __gtype_name__ = 'TacProjectListWidget'

    __gsignals__ = {
        'project-selected': (GObject.SIGNAL_RUN_FIRST, None, (object,)),
    }

    def __init__(self, project_manager: ProjectManager, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.project_manager = project_manager
        self.set_vexpand(True)

        # Search entry
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Search projects..."))
        self.search_entry.set_hexpand(False)  # NOVO: Evita expansão horizontal
        self.search_entry.set_margin_top(10)     # Superior
        self.search_entry.set_margin_bottom(5)   # Inferior
        self.search_entry.set_margin_start(25)   # Esquerda
        self.search_entry.set_margin_end(25)     # Direita
        self.search_entry.connect('search-changed', self._on_search_changed)
        self.append(self.search_entry)

        # Scrolled window for project list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        # Project list
        self.project_list = Gtk.ListBox()
        self.project_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.project_list.connect('row-activated', self._on_project_activated)
        self.project_list.set_filter_func(self._filter_projects)

        scrolled.set_child(self.project_list)
        self.append(scrolled)

        # Load projects
        self.refresh_projects()

    def refresh_projects(self):
        """Refresh the project list"""
        # Clear existing projects
        child = self.project_list.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.project_list.remove(child)
            child = next_child

        # Load projects
        projects = self.project_manager.list_projects()

        for project_info in projects:
            row = self._create_project_row(project_info)
            self.project_list.append(row)

    def _create_project_row(self, project_info):
        """Create a row for a project"""
        row = Gtk.ListBoxRow()
        row.project_info = project_info

        # Main box
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        # Header with name and date
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        # Project name
        name_label = Gtk.Label()
        name_label.set_text(project_info['name'])
        name_label.set_halign(Gtk.Align.START)
        name_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END = 3
        name_label.add_css_class("heading")
        header_box.append(name_label)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header_box.append(spacer)

        # Action buttons (initially hidden)
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        actions_box.set_visible(False)

        # Edit button (pencil)
        edit_button = Gtk.Button()
        edit_button.set_icon_name("edit-symbolic")
        edit_button.set_tooltip_text(_("Rename project"))
        edit_button.add_css_class("flat")
        edit_button.add_css_class("circular")
        edit_button.connect('clicked', lambda b: self._on_edit_project(project_info))
        actions_box.append(edit_button)

        # Delete button (trash)
        delete_button = Gtk.Button()
        delete_button.set_icon_name("user-trash-symbolic")
        delete_button.set_tooltip_text(_("Delete project"))
        delete_button.add_css_class("flat")
        delete_button.add_css_class("circular")
        delete_button.connect('clicked', lambda b: self._on_delete_project(project_info))
        actions_box.append(delete_button)

        header_box.append(actions_box)

        # Modification date
        if project_info.get('modified_at'):
            from datetime import datetime
            try:
                modified_dt = datetime.fromisoformat(project_info['modified_at'])
                date_label = Gtk.Label()
                date_label.set_text(FormatHelper.format_datetime(modified_dt, 'short'))
                date_label.add_css_class("caption")
                date_label.add_css_class("dim-label")
                header_box.append(date_label)
            except:
                pass

        box.append(header_box)

        # Statistics
        stats = project_info.get('statistics', {})
        if stats:
            stats_label = Gtk.Label()
            words = stats.get('total_words', 0)
            paragraphs = stats.get('total_paragraphs', 0)
            stats_text = _("{} words • {} paragraphs").format(words, paragraphs)
            stats_label.set_text(stats_text)
            stats_label.set_halign(Gtk.Align.START)
            stats_label.add_css_class("caption")
            stats_label.add_css_class("dim-label")
            box.append(stats_label)

        # Setup hover effect
        hover_controller = Gtk.EventControllerMotion()
        hover_controller.connect('enter', lambda c, x, y: actions_box.set_visible(True))
        hover_controller.connect('leave', lambda c: actions_box.set_visible(False))
        row.add_controller(hover_controller)

        row.set_child(box)
        return row

    def _on_project_activated(self, listbox, row):
        """Handle project activation"""
        if row and hasattr(row, 'project_info'):
            self.emit('project-selected', row.project_info)

    def _on_search_changed(self, search_entry):
        """Handle search text change"""
        self.project_list.invalidate_filter()

    def _filter_projects(self, row):
        """Filter projects based on search text"""
        search_text = self.search_entry.get_text().lower()
        if not search_text:
            return True

        if hasattr(row, 'project_info'):
            project_name = row.project_info.get('name', '').lower()
            project_desc = row.project_info.get('description', '').lower()
            return search_text in project_name or search_text in project_desc

        return True

    def _on_edit_project(self, project_info):
        """Handle project rename"""
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            _("Rename Project"),
            _("Enter new name for '{}'").format(project_info['name'])
        )

        # Add entry for new name
        entry = Gtk.Entry()
        entry.set_text(project_info['name'])
        entry.set_margin_start(20)
        entry.set_margin_end(20)
        entry.set_margin_top(10)
        entry.set_margin_bottom(10)

        # Select all text for easy replacement
        entry.grab_focus()
        entry.select_region(0, -1)

        dialog.set_extra_child(entry)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("rename", _("Rename"))
        dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("rename")

        def save_name():
            """Save the new name"""
            new_name = entry.get_text().strip()
            if new_name and new_name != project_info['name']:
                # Load, rename and save project
                project = self.project_manager.load_project(project_info['id'])
                if project:
                    project.name = new_name
                    self.project_manager.save_project(project)
                    self.refresh_projects()
            dialog.destroy()

        def on_response(dialog, response):
            if response == "rename":
                save_name()
            else:
                dialog.destroy()

        # Handle Enter key in entry
        def on_entry_activate(entry):
            save_name()

        entry.connect('activate', on_entry_activate)
        dialog.connect('response', on_response)
        dialog.present()

    def _on_delete_project(self, project_info):
        """Handle project deletion"""
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            _("Delete '{}'?").format(project_info['name']),
            _("This project will be moved to trash and can be recovered.")
        )

        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")

        def on_response(dialog, response):
            if response == "delete":
                success = self.project_manager.delete_project(project_info['id'])
                if success:
                    self.refresh_projects()
            dialog.destroy()

        dialog.connect('response', on_response)
        dialog.present()

class ParagraphEditor(Gtk.Box):
    """Editor for individual paragraphs"""

    __gtype_name__ = 'TacParagraphEditor'

    __gsignals__ = {
        'content-changed': (GObject.SIGNAL_RUN_FIRST, None, ()),
        'remove-requested': (GObject.SIGNAL_RUN_FIRST, None, (str,)),
        'paragraph-reorder': (GObject.SIGNAL_RUN_FIRST, None, (str, str, str)),  # (dragged_id, target_id, position)
    }

    def __init__(self, paragraph: Paragraph, config=None, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.paragraph = paragraph
        self.config = config  # ADD CONFIG PARAMETER
        self.text_view = None
        self.text_buffer = None
        self.is_dragging = False
        
        # ADD SPELL CHECK COMPONENTS
        self.spell_checker = None
        self.spell_helper = SpellCheckHelper(config) if config else None
        
        self.set_spacing(8)
        self.add_css_class("card")
        self.set_margin_start(4)
        self.set_margin_end(4)
        self.set_margin_top(4)
        self.set_margin_bottom(4)

        # Create text editor
        self._create_text_editor()
        # Create header
        self._create_header()
        # Setup drag and drop
        self._setup_drag_and_drop()
        # Apply initial formatting
        self._apply_formatting()
        
        # Aplicar tanto formatação quanto spell check com delay
        GLib.idle_add(self._setup_delayed_initialization)

    def _setup_delayed_initialization(self):
        """Setup both formatting and spell check after widget is realized"""
        # Aplicar formatação primeiro
        self._apply_formatting()
    
        # Depois configurar spell check
        if self.spell_helper and self.text_view and self.config and self.config.get_spell_check_enabled():
            try:
                self.spell_checker = self.spell_helper.setup_spell_check(self.text_view)
                if self.spell_checker:
                    print(f"✓ Spell check enabled for paragraph: {self.paragraph.type.value}")
            except Exception as e:
                print(f"✗ Error setting up spell check: {e}")
    
        return False


    def _setup_spell_check_delayed(self):
        """Setup spell checking after widget is realized"""
        if not self.spell_helper or not self.text_view:
            return False
        
        if self.config and self.config.get_spell_check_enabled():
            try:
                self.spell_checker = self.spell_helper.setup_spell_check(self.text_view)
                if self.spell_checker:
                    print(f"✓ Spell check enabled for paragraph: {self.paragraph.type.value}")
            except Exception as e:
                print(f"✗ Error setting up spell check: {e}")
        
        return False

    def _create_header(self):
        """Create paragraph header with type and controls"""
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header_box.set_margin_start(12)
        header_box.set_margin_end(12)
        header_box.set_margin_top(8)
        header_box.set_margin_bottom(4)

        # Type label
        type_label = Gtk.Label()
        type_label.set_text(self._get_type_label())
        type_label.add_css_class("caption")
        type_label.add_css_class("accent")
        type_label.set_halign(Gtk.Align.START)
        header_box.append(type_label)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header_box.append(spacer)

        # ADD SPELL CHECK BUTTON
        if SPELL_CHECK_AVAILABLE and self.config:
            self.spell_button = Gtk.ToggleButton()
            self.spell_button.set_icon_name("tools-check-spelling-symbolic")
            self.spell_button.set_tooltip_text(_("Toggle spell checking"))
            self.spell_button.add_css_class("flat")
            self.spell_button.set_active(self.config.get_spell_check_enabled())
            self.spell_button.connect('toggled', self._on_spell_check_toggled)
            header_box.append(self.spell_button)

        # Word count
        self.word_count_label = Gtk.Label()
        self.word_count_label.add_css_class("caption")
        self.word_count_label.add_css_class("dim-label")
        self._update_word_count()
        header_box.append(self.word_count_label)

        # Remove button
        remove_button = Gtk.Button()
        remove_button.set_icon_name("edit-delete-symbolic")
        remove_button.set_tooltip_text(_("Remove paragraph"))
        remove_button.add_css_class("flat")
        remove_button.connect('clicked', self._on_remove_clicked)
        header_box.append(remove_button)

        self.append(header_box)

    def _on_spell_check_toggled(self, button):
        """Handle spell check toggle"""
        if not self.spell_helper:
            return
        
        enabled = button.get_active()
        
        if enabled and not self.spell_checker:
            try:
                self.spell_checker = self.spell_helper.setup_spell_check(self.text_view)
                if self.spell_checker:
                    print("✓ Spell check enabled via button")
            except Exception as e:
                print(f"✗ Error enabling spell check: {e}")
        elif self.spell_checker:
            try:
                self.spell_helper.enable_spell_check(self.text_view, enabled)
                print(f"✓ Spell check {'enabled' if enabled else 'disabled'} via button")
            except Exception as e:
                print(f"✗ Error toggling spell check: {e}")
        
        if self.config:
            self.config.set_spell_check_enabled(enabled)

    def _create_text_editor(self):
        """Create the text editing area"""
        # Text buffer
        self.text_buffer = Gtk.TextBuffer()
        self.text_buffer.set_text(self.paragraph.content)
        self.text_buffer.connect('changed', self._on_text_changed)

        # Text view
        self.text_view = Gtk.TextView()
        self.text_view.set_buffer(self.text_buffer)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.text_view.set_accepts_tab(False)
        self.text_view.set_margin_start(12)
        self.text_view.set_margin_end(12)
        self.text_view.set_margin_top(8)
        self.text_view.set_margin_bottom(12)

        # Scrolled window
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(100)
        scrolled.set_max_content_height(300)
        scrolled.set_child(self.text_view)

        self.append(scrolled)

    def _setup_drag_and_drop(self):
        """Setup drag and drop functionality for reordering paragraphs"""
        # Create drag source
        drag_source = Gtk.DragSource()
        drag_source.set_actions(Gdk.DragAction.MOVE)

        # Connect drag signals
        drag_source.connect('prepare', self._on_drag_prepare)
        drag_source.connect('drag-begin', self._on_drag_begin)
        drag_source.connect('drag-end', self._on_drag_end)

        # Add drag source to the widget
        self.add_controller(drag_source)

        # Create drop target
        drop_target = Gtk.DropTarget()
        drop_target.set_gtypes([GObject.TYPE_STRING])
        drop_target.set_actions(Gdk.DragAction.MOVE)

        # Connect drop signals
        drop_target.connect('accept', self._on_drop_accept)
        drop_target.connect('enter', self._on_drop_enter)
        drop_target.connect('leave', self._on_drop_leave)
        drop_target.connect('drop', self._on_drop)

        # Add drop target to the widget
        self.add_controller(drop_target)

    def _setup_drag_indicator(self):
        """Setup visual drag indicator"""
        # Add motion controller for hover effects
        motion_controller = Gtk.EventControllerMotion()
        motion_controller.connect('enter', self._on_mouse_enter)
        motion_controller.connect('leave', self._on_mouse_leave)

        # Add to the text view area
        self.text_view.add_controller(motion_controller)

        # Set cursor to indicate draggable
        self.set_cursor_from_name("grab")

    def _on_mouse_enter(self, controller, x, y):
        """Handle mouse enter"""
        if not self.is_dragging:
            self.add_css_class("draggable-hover")
            self.set_cursor_from_name("grab")

    def _on_mouse_leave(self, controller):
        """Handle mouse leave"""
        if not self.is_dragging:
            self.remove_css_class("draggable-hover")
            self.set_cursor_from_name("default")

    def _on_drag_prepare(self, drag_source, x, y):
        """Prepare drag operation"""
        # Create content provider with paragraph ID
        content = Gdk.ContentProvider.new_for_value(self.paragraph.id)
        return content

    def _on_drag_begin(self, drag_source, drag):
        """Start drag operation"""
        self.is_dragging = True
        self.add_css_class("dragging")

        # Create drag icon (GTK4 way)
        try:
            paintable = Gtk.WidgetPaintable.new(self)
            drag_source.set_icon(paintable, 0, 0)
        except:
            # Fallback: no custom icon
            pass

    def _on_drag_end(self, drag_source, drag, delete_data):
        """End drag operation"""
        self.is_dragging = False
        self.remove_css_class("dragging")
        self.remove_css_class("drop-target")

    def _on_drop_accept(self, drop_target, drop):
        """Check if drop is acceptable"""
        # Accept drops of string type (paragraph IDs)
        return drop.get_formats().contain_gtype(GObject.TYPE_STRING)

    def _on_drop_enter(self, drop_target, x, y):
        """Handle drop enter"""
        self.add_css_class("drop-target")
        return Gdk.DragAction.MOVE

    def _on_drop_leave(self, drop_target):
        """Handle drop leave"""
        self.remove_css_class("drop-target")

    def _on_drop(self, drop_target, value, x, y):
        """Handle drop operation"""
        self.remove_css_class("drop-target")

        if isinstance(value, str):
            dragged_paragraph_id = value
            target_paragraph_id = self.paragraph.id

            # Don't drop on self
            if dragged_paragraph_id == target_paragraph_id:
                return False

            # Determine drop position based on y coordinate
            widget_height = self.get_allocated_height()
            drop_position = "after" if y > widget_height / 2 else "before"

            # Emit reorder signal
            self.emit('paragraph-reorder', dragged_paragraph_id, target_paragraph_id, drop_position)
            return True

        return False

    def _get_type_label(self) -> str:
        """Get display label for paragraph type"""
        type_labels = {
            ParagraphType.TITLE_1: _("Title 1"),
            ParagraphType.TITLE_2: _("Title 2"),
            ParagraphType.INTRODUCTION: _("Introduction"),
            ParagraphType.ARGUMENT: _("Argument"),
            ParagraphType.QUOTE: _("Quote"),
            ParagraphType.CONCLUSION: _("Conclusion")
        }
        return type_labels.get(self.paragraph.type, _("Paragraph"))

    def _apply_formatting(self):
        """Apply formatting using TextBuffer tags (GTK4 way)"""
        # Guard clause: ensure text_buffer is initialized
        if not self.text_buffer or not self.text_view:
            return

        # NOVO: Se widget não está realizado, aplicar com delay
        if not self.text_view.get_realized():
            GLib.idle_add(self._apply_formatting)
            return        
        
        formatting = self.paragraph.formatting

        # Create or get text tags
        tag_table = self.text_buffer.get_tag_table()

        # Remove existing "format" tag if it exists
        existing_tag = tag_table.lookup("format")
        if existing_tag:
            tag_table.remove(existing_tag)

        # Create new formatting tag
        format_tag = self.text_buffer.create_tag("format")

        # Apply font family and size
        font_family = formatting.get('font_family', 'Liberation Serif')
        font_size = formatting.get('font_size', 12)
        format_tag.set_property("family", font_family)
        format_tag.set_property("size-points", float(font_size))

        # Apply bold/italic/underline
        if formatting.get('bold', False):
            format_tag.set_property("weight", 700)  # Pango.Weight.BOLD

        if formatting.get('italic', False):
            format_tag.set_property("style", 2)  # Pango.Style.ITALIC

        if formatting.get('underline', False):
            format_tag.set_property("underline", 1)  # Pango.Underline.SINGLE

        # Apply tag to all text
        start_iter = self.text_buffer.get_start_iter()
        end_iter = self.text_buffer.get_end_iter()
        self.text_buffer.apply_tag(format_tag, start_iter, end_iter)

        # Apply margins
        left_margin = formatting.get('indent_left', 0.0)
        right_margin = formatting.get('indent_right', 0.0)
        self.text_view.set_left_margin(int(left_margin * 28))
        self.text_view.set_right_margin(int(right_margin * 28))

    def _update_word_count(self):
        """Update word count display"""
        word_count = self.paragraph.get_word_count()
        if word_count == 1:
            self.word_count_label.set_text(_("{count} word").format(count=word_count))
        else:
            self.word_count_label.set_text(_("{count} words").format(count=word_count))

    def _on_text_changed(self, buffer):
        """Handle text changes"""
        # Get text from buffer
        start_iter = buffer.get_start_iter()
        end_iter = buffer.get_end_iter()
        text = buffer.get_text(start_iter, end_iter, False)

        # Update paragraph content
        self.paragraph.update_content(text)

        # Update word count
        self._update_word_count()

        # Emit signal
        self.emit('content-changed')

    def _on_remove_clicked(self, button):
        """Handle remove button click"""
        # Show confirmation dialog
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            _("Remove Paragraph?"),
            _("This action cannot be undone.")
        )

        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("remove", _("Remove"))
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        dialog.connect('response', self._on_remove_confirmed)
        dialog.present()

    def _on_remove_confirmed(self, dialog, response):
        """Handle remove confirmation"""
        if response == "remove":
            self.emit('remove-requested', self.paragraph.id)
        dialog.destroy()

    def refresh_formatting(self):
        """Refresh visual formatting (called when formatting is changed externally)"""
        self._apply_formatting()

class TextEditor(Gtk.Box):
    """Advanced text editor component"""

    __gtype_name__ = 'TacTextEditor'

    __gsignals__ = {
        'content-changed': (GObject.SIGNAL_RUN_FIRST, None, (str,)),
    }

    def __init__(self, initial_text: str = "", config=None, **kwargs):  # ADD CONFIG PARAMETER
        super().__init__(orientation=Gtk.Orientation.VERTICAL, **kwargs)
        self.config = config  # ADD CONFIG
        
        # ADD SPELL CHECK COMPONENTS
        self.spell_checker = None
        self.spell_helper = SpellCheckHelper(config) if config else None

        # Text buffer and view
        self.text_buffer = Gtk.TextBuffer()
        self.text_buffer.set_text(initial_text)
        self.text_buffer.connect('changed', self._on_text_changed)

        self.text_view = Gtk.TextView()
        self.text_view.set_buffer(self.text_buffer)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.text_view.set_accepts_tab(True)

        # Scrolled window
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_child(self.text_view)
        scrolled.set_vexpand(True)

        self.append(scrolled)
        
        # ADD SPELL CHECK SETUP
        GLib.idle_add(self._setup_spell_check_delayed)

    def _setup_spell_check_delayed(self):
        """Setup spell checking after widget is realized"""
        if not self.spell_helper or not self.text_view:
            return False
        
        if self.config and self.config.get_spell_check_enabled():
            try:
                self.spell_checker = self.spell_helper.setup_spell_check(self.text_view)
                if self.spell_checker:
                    print(f"✓ Spell check enabled for text editor")
            except Exception as e:
                print(f"✗ Error setting up spell check: {e}")
        
        return False

    def _on_text_changed(self, buffer):
        """Handle text buffer changes"""
        text = self.get_text()
        self.emit('content-changed', text)

    def get_text(self) -> str:
        """Get current text content"""
        start_iter = self.text_buffer.get_start_iter()
        end_iter = self.text_buffer.get_end_iter()
        return self.text_buffer.get_text(start_iter, end_iter, False)

    def set_text(self, text: str):
        """Set text content"""
        self.text_buffer.set_text(text)

class FormatToolbar(Gtk.Box):
    """Toolbar for text formatting options"""

    __gtype_name__ = 'TacFormatToolbar'

    __gsignals__ = {
        'format-changed': (GObject.SIGNAL_RUN_FIRST, None, (str, object)),
    }

    def __init__(self, **kwargs):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, **kwargs)
        self.set_spacing(6)
        self.add_css_class("toolbar")

        # Font family
        self.font_combo = Gtk.ComboBoxText()
        fonts = ["Liberation Serif"] #"Times New Roman", "Arial", "Calibri"]
        for font in fonts:
            self.font_combo.append_text(font)
        self.font_combo.set_active(0)
        self.font_combo.connect('changed', lambda w: self.emit('format-changed', 'font_family', w.get_active_text()))
        self.append(self.font_combo)

        # Font size
        self.size_spin = Gtk.SpinButton()
        self.size_spin.set_range(8, 72)
        self.size_spin.set_value(12)
        self.size_spin.set_increments(1, 2)
        self.size_spin.connect('value-changed', lambda w: self.emit('format-changed', 'font_size', int(w.get_value())))
        self.append(self.size_spin)

        # Separator
        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # Bold button
        self.bold_button = Gtk.ToggleButton()
        self.bold_button.set_icon_name("format-text-bold-symbolic")
        self.bold_button.set_tooltip_text(_("Bold"))
        self.bold_button.connect('toggled', lambda w: self.emit('format-changed', 'bold', w.get_active()))
        self.append(self.bold_button)

        # Italic button
        self.italic_button = Gtk.ToggleButton()
        self.italic_button.set_icon_name("format-text-italic-symbolic")
        self.italic_button.set_tooltip_text(_("Italic"))
        self.italic_button.connect('toggled', lambda w: self.emit('format-changed', 'italic', w.get_active()))
        self.append(self.italic_button)

        # Underline button
        self.underline_button = Gtk.ToggleButton()
        self.underline_button.set_icon_name("format-text-underline-symbolic")
        self.underline_button.set_tooltip_text(_("Underline"))
        self.underline_button.connect('toggled', lambda w: self.emit('format-changed', 'underline', w.get_active()))
        self.append(self.underline_button)

    def update_from_formatting(self, formatting: dict):
        """Update toolbar state from formatting dictionary"""
        # Update font family
        font_family = formatting.get('font_family', 'Liberation Serif')
        for i in range(self.font_combo.get_model().iter_n_children(None)):
            model = self.font_combo.get_model()
            iter_val = model.iter_nth_child(None, i)
            if model.get_value(iter_val, 0) == font_family:
                self.font_combo.set_active(i)
                break

        # Update font size
        self.size_spin.set_value(formatting.get('font_size', 12))

        # Update toggle buttons
        self.bold_button.set_active(formatting.get('bold', False))
        self.italic_button.set_active(formatting.get('italic', False))
        self.underline_button.set_active(formatting.get('underline', False))


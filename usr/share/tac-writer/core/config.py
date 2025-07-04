"""
TAC Configuration Module
Application configuration management following XDG standards
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List

class Config:
    """Application configuration manager"""

    def __init__(self):
        self._setup_directories()
        self._load_defaults()
        self.load()

    def _setup_directories(self):
        """Setup application directories following XDG standards"""
        # Get XDG directories or fallback to defaults
        home = Path.home()

        # Data directory
        xdg_data_home = os.environ.get('XDG_DATA_HOME')
        if xdg_data_home:
            self.data_dir = Path(xdg_data_home) / 'tac'
        else:
            self.data_dir = home / '.local' / 'share' / 'tac'

        # Config directory
        xdg_config_home = os.environ.get('XDG_CONFIG_HOME')
        if xdg_config_home:
            self.config_dir = Path(xdg_config_home) / 'tac'
        else:
            self.config_dir = home / '.config' / 'tac'

        # Cache directory
        xdg_cache_home = os.environ.get('XDG_CACHE_HOME')
        if xdg_cache_home:
            self.cache_dir = Path(xdg_cache_home) / 'tac'
        else:
            self.cache_dir = home / '.cache' / 'tac'

        # Create directories if they don't exist
        for directory in [self.data_dir, self.config_dir, self.cache_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def _load_defaults(self):
        """Load default configuration values"""
        self._config = {
            # Window settings
            'window_width': 1200,
            'window_height': 800,
            'window_maximized': False,
            'window_position': None,

            # Editor settings
            'font_family': 'Liberation Serif',
            'font_size': 12,
            'line_spacing': 1.5,
            'show_line_numbers': True,
            'word_wrap': True,
            'highlight_current_line': True,
            'auto_save': True,
            'auto_save_interval': 120,  # 2 minutes

            # Spell checking settings
            'spell_check_enabled': True,
            'spell_check_language': 'pt_BR',  # Default to Portuguese Brazil
            'spell_check_show_language_menu': True,
            'spell_check_available_languages': ['pt_BR', 'en_US', 'es_ES', 'fr_FR', 'de_DE', 'it_IT', 'ru_RU', 'zh_CH'],
            'spell_check_personal_dictionary': str(self.config_dir / 'personal_dict.txt'),

            # Formatting defaults
            'default_paragraph_indent': 1.25,  # cm
            'quote_indent': 4.0,  # cm
            'page_margins': {
                'top': 2.5,
                'bottom': 2.5,
                'left': 3.0,
                'right': 3.0
            },

            # Application behavior
            'backup_files': True,
            'recent_files_limit': 10,
            'confirm_on_close': True,
            'restore_session': True,
            'show_welcome_dialog': True,

            # Theme and appearance
            'use_dark_theme': False,
            'adaptive_theme': True,  # Follow system theme
            'enable_animations': True,

            # Project defaults
            'default_project_location': str(self.data_dir / 'projects'),
            'project_template': 'academic_essay',

            # Export settings
            'export_location': str(Path.home() / 'Documents'),
            'default_export_format': 'odt',
            'include_metadata': True,

            # Recent projects list - CORRIGIDO: Adicionado campo ausente
            'recent_projects': []
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value"""
        self._config[key] = value

    def update(self, updates: Dict[str, Any]) -> None:
        """Update multiple configuration values"""
        self._config.update(updates)

    def reset(self, key: Optional[str] = None) -> None:
        """Reset configuration to defaults"""
        if key:
            # Reset specific key
            defaults = Config()._config
            if key in defaults:
                self._config[key] = defaults[key]
        else:
            # Reset all
            self._load_defaults()

    @property
    def config_file(self) -> Path:
        """Path to the configuration file"""
        return self.config_dir / 'config.json'

    @property
    def projects_dir(self) -> Path:
        """Path to the projects directory"""
        projects_path = Path(self.get('default_project_location'))
        projects_path.mkdir(parents=True, exist_ok=True)
        return projects_path

    def save(self) -> bool:
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False

    def load(self) -> bool:
        """Load configuration from file"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                self._config.update(saved_config)
            return True
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return False

    def get_recent_projects(self) -> list:
        """Get list of recent projects"""
        return self.get('recent_projects', [])

    def add_recent_project(self, project_path: str) -> None:
        """Add project to recent projects list"""
        recent = self.get_recent_projects()
        # Remove if already exists
        if project_path in recent:
            recent.remove(project_path)
        # Add to beginning
        recent.insert(0, project_path)
        # Limit size
        limit = self.get('recent_files_limit', 10)
        recent = recent[:limit]
        self.set('recent_projects', recent)

    def remove_recent_project(self, project_path: str) -> None:
        """Remove project from recent projects list"""
        recent = self.get_recent_projects()
        if project_path in recent:
            recent.remove(project_path)
            self.set('recent_projects', recent)  # CORRIGIDO: Salvar alteração

    def export_config(self, file_path: str) -> bool:
        """Export configuration to file"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error exporting configuration: {e}")
            return False

    def import_config(self, file_path: str) -> bool:
        """Import configuration from file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)
            self._config.update(imported_config)
            return True
        except Exception as e:
            print(f"Error importing configuration: {e}")
            return False

    # Spell checking convenience methods - CORRIGIDOS E MELHORADOS
    def get_spell_check_enabled(self) -> bool:
        """Get spell check enabled status"""
        return self.get('spell_check_enabled', True)

    def set_spell_check_enabled(self, enabled: bool) -> None:
        """Set spell check enabled status"""
        self.set('spell_check_enabled', enabled)
        print(f"Debug: Spell check {'enabled' if enabled else 'disabled'} globally")

    def get_spell_check_language(self) -> str:
        """Get current spell check language"""
        return self.get('spell_check_language', 'pt_BR')

    def set_spell_check_language(self, language: str) -> None:
        """Set spell check language with validation"""
        if self.is_spell_language_available(language):
            self.set('spell_check_language', language)
            print(f"Debug: Spell check language set to {language}")
        else:
            print(f"Warning: Language '{language}' is not available. Available languages: {self.get_available_spell_languages()}")

    def get_available_spell_languages(self) -> List[str]:
        """Get list of available spell check languages - CORRIGIDO"""
        return self.get('spell_check_available_languages', ['pt_BR', 'en_US', 'es_ES', 'fr_FR', 'de_DE', 'it_IT'])

    def is_spell_language_available(self, language: str) -> bool:
        """Check if a spell check language is available - NOVO MÉTODO"""
        return language in self.get_available_spell_languages()

    def get_spell_check_show_language_menu(self) -> bool:
        """Get whether to show language menu in spell check context"""
        return self.get('spell_check_show_language_menu', True)

    def set_spell_check_show_language_menu(self, show: bool) -> None:
        """Set whether to show language menu in spell check context"""
        self.set('spell_check_show_language_menu', show)

    def get_personal_dictionary_path(self) -> str:
        """Get path to personal dictionary file"""
        return self.get('spell_check_personal_dictionary', str(self.config_dir / 'personal_dict.txt'))

    def set_available_spell_languages(self, languages: List[str]) -> None:
        """Set list of available spell check languages - NOVO MÉTODO"""
        self.set('spell_check_available_languages', languages)
        print(f"Debug: Available spell languages updated to: {languages}")

    # NOVOS MÉTODOS DE DEBUG
    def debug_spell_config(self) -> None:
        """Print current spell check configuration for debugging"""
        print("=== Spell Check Configuration Debug ===")
        print(f"Enabled: {self.get_spell_check_enabled()}")
        print(f"Language: {self.get_spell_check_language()}")
        print(f"Available languages: {self.get_available_spell_languages()}")
        print(f"Show language menu: {self.get_spell_check_show_language_menu()}")
        print(f"Personal dictionary: {self.get_personal_dictionary_path()}")
        print("======================================")


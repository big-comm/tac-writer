#!/usr/bin/env python3
"""
TAC - Continuous Argumentation Technique
Main entry point for the application
GTK4 + libadwaita academic text writing assistant
"""

import sys
import os
from pathlib import Path

# Setup path for imports
app_dir = Path(__file__).parent.resolve()
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

# Import translation function
from utils.i18n import _


def setup_environment():
    """Setup the application environment and paths"""
    # Get the directory where this script is located
    app_directory = Path(__file__).parent.resolve()
    
    # Add the application directory to Python path if not already present
    if str(app_directory) not in sys.path:
        sys.path.insert(0, str(app_directory))
    
    return app_directory


def check_dependencies():
    """Check if required dependencies are available"""
    try:
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Adw', '1')
        from gi.repository import Gtk, Adw
        
        # Check GTK version
        gtk_version = f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"
        print(f"GTK version: {gtk_version}")
        
        if Gtk.get_major_version() < 4:
            print(_("Error: GTK 4.0 or higher is required"))
            return False
            
        return True
        
    except ImportError as e:
        print(_("Error: Required dependencies not found: {}").format(e))
        print(_("Please install: python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adwaita-1"))
        return False
    except Exception as e:
        print(_("Error checking dependencies: {}").format(e))
        return False


def main():
    """Main application entry point"""
    print("=== " + _("Starting TAC - Continuous Argumentation Technique") + " ===")
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")
    
    try:
        # Setup environment
        app_directory = setup_environment()
        print(_("Application directory: {}").format(app_directory))
        
        # Check dependencies
        if not check_dependencies():
            return 1
        
        # Import and run application
        print(_("Loading application modules..."))
        from application import TacApplication
        
        print(_("Creating application instance..."))
        app = TacApplication()
        
        print(_("Running TAC application..."))
        result = app.run(sys.argv)
        
        print(_("Application finished."))
        return result
        
    except KeyboardInterrupt:
        print("\n" + _("Application interrupted by user."))
        return 0
    except Exception as e:
        print(_("Critical error during startup: {}").format(e))
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
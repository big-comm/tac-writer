# Icon Implementation Guide - GTK IconTheme with Priority

This document describes the icon implementation strategy used in Big Video Converter and how to replicate it in other GTK4/libadwaita applications.

## Overview

This implementation provides:
- **Custom icons with guaranteed priority** over system icons
- **Automatic theme adaptation** (light/dark modes)
- **Flat directory structure** for easy icon management
- **FreeDesktop standard compliance**
- **Reusable pattern** for other applications

## The Problem

When using custom icons in GTK applications, there are two common approaches, each with limitations:

### Approach A: Direct File Loading
```python
# Using absolute paths
icon = Gtk.Image.new_from_file('/path/to/icon.svg')
```

**Problems:**
- ❌ Icons don't adapt to theme changes (light/dark)
- ❌ SVG files with `fill:currentColor` stay static
- ❌ No automatic color inversion for symbolic icons

### Approach B: GTK IconTheme (add_search_path)
```python
# Adding to search path
icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
icon_theme.add_search_path('/path/to/icons')
icon = Gtk.Image.new_from_icon_name('my-icon-symbolic')
```

**Problems:**
- ❌ System icons have priority (custom icons may be ignored)
- ❌ Name conflicts resolved in favor of system icons
- ❌ No guarantee your custom icon will be used

## The Solution: IconTheme with Priority

Use `set_search_path()` instead of `add_search_path()` to **prepend** custom icon directory to the search order.

### Benefits
- ✅ Custom icons guaranteed to be found first
- ✅ Automatic theme adaptation (light/dark)
- ✅ Symbolic icons get proper color treatment
- ✅ SVG `currentColor` works correctly
- ✅ FreeDesktop standard compliance

## Implementation Steps

### 1. Directory Structure

Create a flat icon directory:
```
your-app/
├── main.py
└── icons/
    ├── index.theme
    ├── icon-name-symbolic.svg
    ├── another-icon-symbolic.svg
    ├── app-icon.svg
    └── ...
```

**Important naming rules:**
- Keep `-symbolic` suffix for monochromatic icons (FreeDesktop standard)
- Use lowercase with hyphens (e.g., `edit-copy-symbolic`)
- Don't use `big-` or app-specific prefixes (IconTheme handles isolation)

### 2. Create index.theme File

Create `icons/index.theme` with this exact content:

```ini
[Icon Theme]
Name=BigVideoConverter
Comment=Custom icon theme for Big Video Converter
Inherits=hicolor
Directories=scalable

[scalable]
Context=Actions
Size=48
MinSize=1
MaxSize=512
Type=Scalable
```

**What each line means:**

| Line | Purpose |
|------|---------|
| `Name=BigVideoConverter` | Your app name (change to match your project) |
| `Comment=...` | Brief description of the icon theme |
| `Inherits=hicolor` | Falls back to system icons if yours is missing |
| `Directories=scalable` | Tells GTK icons are in current directory (flat structure) |
| `Context=Actions` | Icon category (Actions for UI buttons/controls) |
| `Size=48` | Nominal size in pixels |
| `Type=Scalable` | Icons are SVG (can be rendered at any size) |
| `MinSize=1, MaxSize=512` | Supports rendering from 1px to 512px |

**To use in your project:** Copy this file exactly, just change the `Name=` line to match your application name.

### 3. Setup IconTheme in Your Application

In your main application class (usually in `main.py`):

```python
import os
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk

class YourApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.example.yourapp')
        self._setup_icon_theme()

    def _setup_icon_theme(self):
        """Setup custom icon theme path with PRIORITY"""
        try:
            # Get application's directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            icons_dir = os.path.join(script_dir, 'icons')

            # Check if icons directory exists
            if os.path.exists(icons_dir):
                # Get default icon theme
                icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())

                # Get current search paths
                current_paths = icon_theme.get_search_path()

                # CRITICAL: Prepend (not append) to ensure priority
                new_paths = [icons_dir] + current_paths
                icon_theme.set_search_path(new_paths)

                print(f"✓ Custom icons loaded with priority: {icons_dir}")

        except Exception as e:
            print(f"⚠ Warning: Could not setup icon theme: {e}")
```

**Critical detail:** Use `set_search_path([icons_dir] + current_paths)`, **not** `add_search_path(icons_dir)`. This guarantees your icons are found **first**.

### 4. Use Icons in Your Code

Now use standard GTK icon methods:

```python
# For buttons
button = Gtk.Button.new_from_icon_name('edit-copy-symbolic')

# For images
image = Gtk.Image.new_from_icon_name('folder-symbolic')

# Changing icon dynamically
button.set_icon_name('media-playback-pause-symbolic')

# For menu items, list items, etc.
action_row.set_icon_name('trash-symbolic')
```

**No need for:**
- ❌ `icon_path()` helper functions
- ❌ Absolute path management
- ❌ Manual file loading
- ❌ Theme detection logic

GTK handles everything automatically!

## SVG Icon Requirements

For proper theme adaptation, your SVG icons should use `currentColor`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path fill="currentColor" d="M8 2L3 7h3v5h4V7h3z"/>
</svg>
```

**Key points:**
- Use `fill="currentColor"` instead of specific colors like `#000000`
- This allows GTK to apply theme colors automatically
- Works for both light and dark themes
- Symbolic icons will be recolored based on foreground color

## Testing Theme Adaptation

To verify icons adapt correctly:

1. **Run your application**
2. **Switch system theme** between light and dark:
   - GNOME: Settings → Appearance → Style
   - KDE: Settings → Appearance → Global Theme
3. **Verify icons change color** to match the theme

Expected behavior:
- Light theme: Icons appear dark (black/gray)
- Dark theme: Icons appear light (white/light gray)

## Migration Script

If you need to migrate from absolute paths to IconTheme, use this script:

```python
#!/usr/bin/env python3
import os
import re

def migrate_to_icon_theme(filepath):
    """Migrate Python code from icon_path() to IconTheme"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # Pattern 1: Gtk.Button(child=Gtk.Image.new_from_file(icon_path('xxx')))
    # Replace with: Gtk.Button.new_from_icon_name('xxx')
    content = re.sub(
        r"Gtk\.Button\(child=Gtk\.Image\.new_from_file\(icon_path\('([^']+)'\)\)\)",
        r"Gtk.Button.new_from_icon_name('\1')",
        content
    )

    # Pattern 2: button.set_child(Gtk.Image.new_from_file(icon_path('xxx')))
    # Replace with: button.set_icon_name('xxx')
    content = re.sub(
        r"([\w.]+)\.set_child\(Gtk\.Image\.new_from_file\(icon_path\('([^']+)'\)\)\)",
        r"\1.set_icon_name('\2')",
        content
    )

    # Pattern 3: Gtk.Image.new_from_file(icon_path('xxx'))
    # Replace with: Gtk.Image.new_from_icon_name('xxx')
    content = re.sub(
        r"Gtk\.Image\.new_from_file\(icon_path\('([^']+)'\)\)",
        r"Gtk.Image.new_from_icon_name('\1')",
        content
    )

    # Pattern 4: Remove icon_path imports
    content = re.sub(
        r'from constants import (.*), icon_path',
        r'from constants import \1',
        content
    )
    content = re.sub(
        r'from constants import icon_path, (.*)',
        r'from constants import \1',
        content
    )
    content = re.sub(
        r'from constants import icon_path\n',
        '',
        content
    )

    # Write back if changed
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

# Usage
base_dir = "/path/to/your/app"
for root, dirs, files in os.walk(base_dir):
    if '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            if migrate_to_icon_theme(filepath):
                print(f"✓ Migrated: {filepath}")
```

## Troubleshooting

### Icons not appearing
**Cause:** `index.theme` missing or icon names don't match files

**Solution:**
1. Verify `icons/index.theme` exists
2. Check icon file names match exactly (including `-symbolic`)
3. Run with debug: `GTK_DEBUG=icontheme your-app`

### Icons not changing with theme
**Cause:** Using direct file loading instead of IconTheme

**Solution:**
- Replace `new_from_file()` with `new_from_icon_name()`
- Verify SVG uses `fill="currentColor"`
- Ensure `_setup_icon_theme()` is called before UI construction

### System icons used instead of custom icons
**Cause:** Using `add_search_path()` instead of `set_search_path()`

**Solution:**
```python
# Wrong - system icons have priority
icon_theme.add_search_path(icons_dir)

# Correct - custom icons have priority
current_paths = icon_theme.get_search_path()
icon_theme.set_search_path([icons_dir] + current_paths)
```

### Icons missing in AppImage/Flatpak
**Cause:** Icon directory not bundled correctly

**Solution:**
- AppImage: Ensure icons/ is in the AppDir structure
- Flatpak: Add icons directory to manifest files list
- Verify path resolution works from bundle root

## AppImage/Flatpak Integration

### AppImage
In your AppRun script:
```bash
#!/bin/bash
export APPDIR="$(dirname "$(readlink -f "$0")")"
export PYTHONPATH="${APPDIR}/usr/lib/python3/dist-packages:${PYTHONPATH}"
cd "${APPDIR}/usr/share/your-app"
python3 main.py "$@"
```

Structure:
```
AppDir/
├── usr/
│   └── share/
│       └── your-app/
│           ├── main.py
│           └── icons/
│               ├── index.theme
│               └── *.svg
```

### Flatpak
In your manifest (YAML):
```yaml
modules:
  - name: your-app
    buildsystem: simple
    build-commands:
      - install -D main.py /app/share/your-app/main.py
      - cp -r icons /app/share/your-app/icons
```

## Real-World Example

This is the actual implementation from **Big Video Converter**:

**Directory structure:**
```
big-video-converter/usr/share/big-video-converter/
├── main.py
├── icons/
│   ├── index.theme
│   ├── edit-copy-symbolic.svg
│   ├── trash-symbolic.svg
│   ├── folder-symbolic.svg
│   └── ... (20+ icons)
```

**Code in main.py:**
```python
class VideoConverterApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self._setup_icon_theme()  # Called BEFORE UI setup
        # ... rest of initialization
```

**Usage in UI files:**
```python
# header_bar.py
self.menu_button = Gtk.Button.new_from_icon_name('open-menu-symbolic')

# conversion_page.py
play_btn = Gtk.Button.new_from_icon_name('media-playback-start-symbolic')
edit_btn = Gtk.Button.new_from_icon_name('document-edit-symbolic')
remove_btn = Gtk.Button.new_from_icon_name('trash-symbolic')
```

**Result:** All icons adapt perfectly to light/dark theme changes, custom icons always take priority over system icons.

## Key Takeaways

1. **Use IconTheme, not direct file loading** for theme adaptation
2. **Use `set_search_path()` with prepending** for guaranteed priority
3. **Keep `-symbolic` suffix** - it's part of FreeDesktop standard
4. **Create `index.theme`** even for flat directory structure
5. **Use `fill="currentColor"`** in SVG files for theme support
6. **Call `_setup_icon_theme()` early** in application initialization

## References

- [FreeDesktop Icon Theme Specification](https://specifications.freedesktop.org/icon-theme-spec/icon-theme-spec-latest.html)
- [GTK IconTheme Documentation](https://docs.gtk.org/gtk4/class.IconTheme.html)
- [GNOME Icon Design Guidelines](https://developer.gnome.org/hig/guidelines/icon-design.html)

## License

This implementation pattern is provided as-is for use in any GTK application. No attribution required.

---

**Last updated:** 2025-12-07
**Tested with:** GTK 4.x, Python 3.6+, libadwaita 1.x

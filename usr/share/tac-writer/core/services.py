"""
TAC Core Services
Business logic and data services for the TAC application
"""

import json
import shutil
import zipfile
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
# 'shutil' é usado no ExportService
from .config import Config
from utils.helpers import FileHelper

# ODT export dependencies
try:
    from xml.etree import ElementTree as ET
    ODT_AVAILABLE = True
except ImportError:
    ODT_AVAILABLE = False

# PDF export dependencies
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph as RLParagraph, Spacer
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

from .models import Project, Paragraph, ParagraphType
from .config import Config


class ProjectManager:
    """Manages project operations using a SQLite database"""
    
    def __init__(self):
        self.config = Config()
        self.db_path = self.config.database_path
        self._migration_lock = threading.Lock()
        self._init_db()
        self._run_migration_if_needed()
        
        print(f"ProjectManager initialized with database: {self.db_path}")

    def _get_db_connection(self):
        """Get a new database connection with optimized settings"""
        conn = sqlite3.connect(
            self.db_path, 
            timeout=30.0,  # 30 second timeout
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn
    
    def _project_exists(self, project_id: str) -> bool:
        """Check if project exists in database"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM projects WHERE id = ? LIMIT 1", (project_id,))
                return cursor.fetchone() is not None
        except Exception:
            return False

    def _validate_json_data(self, data: Dict[str, Any]) -> bool:
        """Validate that project data has required fields"""
        required_fields = ['id', 'name', 'created_at', 'modified_at']
        
        for field in required_fields:
            if field not in data:
                print(f"Invalid project data: missing field '{field}'")
                return False
        
        # Validate paragraphs if present
        if 'paragraphs' in data:
            for i, para_data in enumerate(data['paragraphs']):
                required_para_fields = ['id', 'type', 'content', 'order']
                for field in required_para_fields:
                    if field not in para_data:
                        print(f"Invalid paragraph {i}: missing field '{field}'")
                        return False
        
        return True

    def _create_migration_backup(self, json_files: List[Path]) -> Optional[Path]:
        """Create a backup of JSON files before migration"""
        try:
            backup_dir = self.config.data_dir / 'migration_backup'
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"projects_backup_{timestamp}.zip"
            
            with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                for json_file in json_files:
                    zf.write(json_file, json_file.name)
            
            print(f"Created migration backup: {backup_file}")
            return backup_file
            
        except Exception as e:
            print(f"Failed to create migration backup: {e}")
            return None

    def _run_migration_if_needed(self):
        """Check for old JSON files and migrate them to SQLite with full transaction support"""
        with self._migration_lock:
            old_projects_dir = self.config.data_dir / 'projects'
            if not old_projects_dir.exists():
                return

            json_files = list(old_projects_dir.glob("*.json"))
            if not json_files:
                return

            print(f"Found {len(json_files)} old JSON projects. Starting migration...")
            
            # Create backup first
            backup_file = self._create_migration_backup(json_files)
            if not backup_file:
                print("Migration aborted: Could not create backup")
                return
            
            # Load and validate all projects before migration
            projects_to_migrate = []
            invalid_files = []
            
            for project_file in json_files:
                try:
                    with open(project_file, 'r', encoding='utf-8') as f:
                        project_data = json.load(f)
                    
                    if not self._validate_json_data(project_data):
                        invalid_files.append(project_file)
                        continue
                        
                    project = Project.from_dict(project_data)
                    projects_to_migrate.append((project, project_file))
                    
                except Exception as e:
                    print(f"Error loading {project_file.name}: {e}")
                    invalid_files.append(project_file)
            
            if invalid_files:
                print(f"Warning: {len(invalid_files)} files have validation errors and will be skipped")
            
            if not projects_to_migrate:
                print("No valid projects to migrate")
                return
            
            # Perform migration in single transaction
            migrated_count = 0
            failed_projects = []
            
            try:
                with self._get_db_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Begin transaction
                    cursor.execute("BEGIN IMMEDIATE;")
                    
                    try:
                        for project, project_file in projects_to_migrate:
                            if self._save_project_to_db(cursor, project):
                                migrated_count += 1
                            else:
                                failed_projects.append(project_file)
                        
                        if failed_projects:
                            raise Exception(f"Failed to migrate {len(failed_projects)} projects")
                        
                        # Commit transaction
                        conn.commit()
                        print(f"Migration transaction committed successfully")
                        
                        # Mark files as migrated only after successful DB commit
                        for project, project_file in projects_to_migrate:
                            try:
                                migrated_file = project_file.with_suffix('.json.migrated')
                                project_file.rename(migrated_file)
                            except Exception as e:
                                print(f"Warning: Could not rename {project_file.name}: {e}")
                        
                    except Exception as e:
                        # Rollback transaction
                        conn.rollback()
                        print(f"Migration failed, transaction rolled back: {e}")
                        return
                        
            except Exception as e:
                print(f"Migration failed with database error: {e}")
                return
            
            print(f"Migration complete. {migrated_count} projects successfully migrated.")
            
            # Run database maintenance after migration
            self._vacuum_database()

    def _save_project_to_db(self, cursor: sqlite3.Cursor, project: Project) -> bool:
        """Save project using provided cursor (for transaction support)"""
        try:
            # Validate JSON serialization
            try:
                metadata_json = json.dumps(project.metadata)
                formatting_json = json.dumps(project.document_formatting)
            except Exception as e:
                print(f"JSON serialization error for project {project.name}: {e}")
                return False
            
            cursor.execute("""
                INSERT INTO projects (id, name, created_at, modified_at, metadata, document_formatting)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    modified_at=excluded.modified_at,
                    metadata=excluded.metadata,
                    document_formatting=excluded.document_formatting;
            """, (
                project.id,
                project.name,
                project.created_at.isoformat(),
                datetime.now().isoformat(),
                metadata_json,
                formatting_json
            ))

            # Delete existing paragraphs for this project
            cursor.execute("DELETE FROM paragraphs WHERE project_id = ?", (project.id,))

            # Insert paragraphs
            paragraphs_data = []
            for p in project.paragraphs:
                try:
                    formatting_json = json.dumps(p.formatting)
                except Exception as e:
                    print(f"JSON serialization error for paragraph {p.id}: {e}")
                    return False
                    
                paragraphs_data.append((
                    p.id, project.id, p.type.value, p.content,
                    p.created_at.isoformat(), p.modified_at.isoformat(),
                    p.order, formatting_json
                ))
            
            if paragraphs_data:
                cursor.executemany("""
                    INSERT INTO paragraphs (id, project_id, type, content, created_at, modified_at, "order", formatting)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """, paragraphs_data)
            
            return True
            
        except Exception as e:
            print(f"Error saving project {project.name} to database: {e}")
            return False

    def save_project(self, project: Project, is_migration: bool = False) -> bool:
        """Save project to the database (UPSERT)"""
        if is_migration:
            return True
        
        # Create database backup before saving
        self._create_database_backup()
            
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN IMMEDIATE;")
                
                try:
                    success = self._save_project_to_db(cursor, project)
                    if success:
                        conn.commit()
                        print(f"Saved project to database: {project.name}")
                        return True
                    else:
                        conn.rollback()
                        return False
                except Exception:
                    conn.rollback()
                    raise
                    
        except Exception as e:
            print(f"Error saving project to database: {e}")
            return False
        
    def _create_database_backup(self) -> bool:
        """Create backup of database file maintaining only 3 most recent backups"""
        if not self.config.get('backup_files', False):
            return True  # Backup disabled, consider success
        
        try:
            # Ensure database file exists
            if not self.db_path.exists():
                return False
            
            # Detect user's Documents directory (language-aware)
            documents_dir = self._get_documents_directory()
            backup_dir = documents_dir / "TAC Projects" / "database_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate backup filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"backup_{timestamp}.db"
            backup_path = backup_dir / backup_filename
            
            # Copy database file
            shutil.copy2(self.db_path, backup_path)
            
            # Clean old backups - keep only 3 most recent
            self._cleanup_old_backups(backup_dir)
            
            print(f"Database backup created: {backup_path}")
            return True
            
        except Exception as e:
            print(f"Warning: Database backup failed: {e}")
            return False

    def _cleanup_old_backups(self, backup_dir: Path):
        """Keep only 3 most recent database backups"""
        try:
            backup_files = list(backup_dir.glob("backup_*.db"))
            
            # Sort by modification time (most recent first)
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Remove files beyond the 3 most recent
            for old_backup in backup_files[3:]:
                old_backup.unlink()
                print(f"Removed old backup: {old_backup}")
                
        except Exception as e:
            print(f"Warning: Cleanup of old backups failed: {e}")
            
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
            'Documentos',  # Portuguese, Spanish
            'Documents',   # English
            'Dokumente',   # German
            'Documenti',   # Italian
            'Документы',   # Russian
            'Documents',   # French (same as English)
        ]
        
        for name in possible_names:
            candidate = home / name
            if candidate.exists() and candidate.is_dir():
                return candidate
        
        # Fallback: use data directory
        return self.config.data_dir

    def _calculate_word_count_python(self, content: str) -> int:
        """Calculate word count using Python (more accurate than SQL)"""
        if not content or not content.strip():
            return 0
        # Split on whitespace and filter empty strings
        words = [word for word in content.split() if word.strip()]
        return len(words)

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects from the database with optimized statistics"""
        projects_info = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Get all projects first
                cursor.execute("""
                    SELECT p.id, p.name, p.created_at, p.modified_at
                    FROM projects p
                    ORDER BY p.modified_at DESC;
                """)
                projects = cursor.fetchall()
                
                for project_row in projects:
                    project_id = project_row['id']
                    
                    # Get paragraphs for this project in correct order
                    cursor.execute("""
                        SELECT type, content FROM paragraphs 
                        WHERE project_id = ? ORDER BY "order" ASC
                    """, (project_id,))
                    paragraphs = cursor.fetchall()
                    
                    # Calculate statistics using same logic as Project.get_statistics()
                    total_words = 0
                    total_paragraphs = 0
                    is_in_paragraph = False
                    
                    for p_row in paragraphs:
                        content = p_row['content'] or ''
                        total_words += self._calculate_word_count_python(content)
                        
                        p_type = p_row['type']
                        
                        # Count logical paragraphs following TAC technique
                        if p_type == 'introduction':
                            total_paragraphs += 1
                            is_in_paragraph = True
                        elif p_type in ['argument', 'conclusion']:
                            if not is_in_paragraph:
                                total_paragraphs += 1
                                is_in_paragraph = False
                        # title_1, title_2, quote don't affect main paragraph counting
                    
                    stats = {
                        'total_paragraphs': total_paragraphs,
                        'total_words': total_words,
                    }
                    
                    projects_info.append({
                        'id': project_row['id'],
                        'name': project_row['name'],
                        'created_at': project_row['created_at'],
                        'modified_at': project_row['modified_at'],
                        'statistics': stats,
                        'file_path': None
                    })
                    
        except Exception as e:
            print(f"Error listing projects from database: {e}")
        
        return projects_info

    def _vacuum_database(self):
        """Perform database maintenance"""
        try:
            with self._get_db_connection() as conn:
                conn.execute("VACUUM;")
                conn.execute("ANALYZE;")
                print("Database maintenance completed")
        except Exception as e:
            print(f"Database maintenance failed: {e}")

    def get_database_info(self) -> Dict[str, Any]:
        """Get database statistics and health information"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Get table sizes
                cursor.execute("SELECT COUNT(*) as project_count FROM projects;")
                project_count = cursor.fetchone()['project_count']
                
                cursor.execute("SELECT COUNT(*) as paragraph_count FROM paragraphs;")
                paragraph_count = cursor.fetchone()['paragraph_count']
                
                # Get database file size
                db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
                
                return {
                    'database_path': str(self.db_path),
                    'database_size_bytes': db_size,
                    'project_count': project_count,
                    'paragraph_count': paragraph_count,
                    'health_status': 'healthy'
                }
                
        except Exception as e:
            return {
                'database_path': str(self.db_path),
                'health_status': f'error: {e}',
                'project_count': 0,
                'paragraph_count': 0
            }
    
    def _init_db(self):
        """Initialize the database and create tables if they don't exist"""
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    modified_at TEXT NOT NULL,
                    metadata TEXT,
                    document_formatting TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paragraphs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    content TEXT,
                    created_at TEXT NOT NULL,
                    modified_at TEXT NOT NULL,
                    "order" INTEGER NOT NULL,
                    formatting TEXT,
                    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
                );
            """)
            conn.commit()

    def create_project(self, name: str, template: str = "academic_essay") -> Project:
        """Create a new project"""
        project = Project(name)
        
        if template == "academic_essay":
            pass
        
        if self.save_project(project):
            print(f"Created project: {project.name} ({project.id})")
            return project
        else:
            raise Exception("Failed to save new project to database")

    def load_project(self, project_id: str) -> Optional[Project]:
        """Load project by ID from the database"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
                project_row = cursor.fetchone()
                
                if not project_row:
                    print(f"Project with ID {project_id} not found in database.")
                    return None
                
                project_data = dict(project_row)
                project_data['metadata'] = json.loads(project_data['metadata'])
                project_data['document_formatting'] = json.loads(project_data['document_formatting'])
                
                cursor.execute("SELECT * FROM paragraphs WHERE project_id = ? ORDER BY \"order\" ASC", (project_id,))
                paragraphs_rows = cursor.fetchall()
                
                paragraphs_data = []
                for p_row in paragraphs_rows:
                    p_data = dict(p_row)
                    p_data['formatting'] = json.loads(p_data['formatting'])
                    paragraphs_data.append(p_data)
                
                project_data['paragraphs'] = paragraphs_data
                
                project = Project.from_dict(project_data)
                print(f"Loaded project from database: {project.name}")
                return project
        except Exception as e:
            print(f"Error loading project from database: {e}")
            return None

    def delete_project(self, project_id: str) -> bool:
        """Delete project from the database"""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
                conn.commit()
                
                print(f"Deleted project from database: {project_id}")
                return True
        except Exception as e:
            print(f"Error deleting project from database: {e}")
            return False

    def create_manual_backup(self) -> Optional[Path]:
        """Create a manual backup of the database"""
        try:
            if not self.db_path.exists():
                return None
                
            # Get backup directory
            documents_dir = self._get_documents_directory()
            backup_dir = documents_dir / "TAC Projects" / "database_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate backup filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"manual_backup_{timestamp}.db"
            backup_path = backup_dir / backup_filename
            
            # Copy database file
            shutil.copy2(self.db_path, backup_path)
            
            # Clean old backups - keep only 10 most recent
            self._cleanup_old_backups(backup_dir, max_backups=10)
            
            print(f"Manual backup created: {backup_path}")
            return backup_path
            
        except Exception as e:
            print(f"Error creating manual backup: {e}")
            return None

    def list_available_backups(self) -> List[Dict[str, Any]]:
        """List available backup files with metadata"""
        backups = []
        try:
            documents_dir = self._get_documents_directory()
            backup_dir = documents_dir / "TAC Projects" / "database_backups"
            
            if not backup_dir.exists():
                return backups
                
            # Find all backup files
            backup_files = list(backup_dir.glob("*.db"))
            
            for backup_file in backup_files:
                try:
                    # Get file stats
                    stat = backup_file.stat()
                    
                    # Try to get project count from backup
                    project_count = 0
                    try:
                        with sqlite3.connect(backup_file) as conn:
                            cursor = conn.cursor()
                            cursor.execute("SELECT COUNT(*) FROM projects")
                            project_count = cursor.fetchone()[0]
                    except:
                        pass
                    
                    backups.append({
                        'path': backup_file,
                        'name': backup_file.name,
                        'size': stat.st_size,
                        'created_at': datetime.fromtimestamp(stat.st_mtime),
                        'project_count': project_count,
                        'is_valid': self._validate_backup_file(backup_file)
                    })
                except Exception as e:
                    print(f"Error reading backup file {backup_file}: {e}")
                    continue
            
            # Sort by creation date (newest first)
            backups.sort(key=lambda x: x['created_at'], reverse=True)
            
        except Exception as e:
            print(f"Error listing backups: {e}")
            
        return backups

    def _validate_backup_file(self, backup_path: Path) -> bool:
        """Validate if backup file is a valid TAC database"""
        try:
            with sqlite3.connect(backup_path) as conn:
                cursor = conn.cursor()
                
                # Check if required tables exist
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name IN ('projects', 'paragraphs')
                """)
                tables = cursor.fetchall()
                
                if len(tables) != 2:
                    return False
                
                # Check table structure
                cursor.execute("PRAGMA table_info(projects)")
                project_columns = [row[1] for row in cursor.fetchall()]
                required_project_columns = ['id', 'name', 'created_at', 'modified_at']
                
                for col in required_project_columns:
                    if col not in project_columns:
                        return False
                
                return True
                
        except Exception as e:
            print(f"Backup validation error: {e}")
            return False

    def import_database(self, backup_path: Path) -> bool:
        """Import database from backup file"""
        try:
            # Validate backup file
            if not self._validate_backup_file(backup_path):
                print("Invalid backup file")
                return False
            
            # Close all current connections
            # Note: In a real implementation, you'd want to notify all components
            # to close their connections first
            
            # Create backup of current database
            current_backup_path = None
            if self.db_path.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                current_backup_path = self.db_path.with_suffix(f'.backup_{timestamp}.db')
                shutil.copy2(self.db_path, current_backup_path)
                print(f"Current database backed up to: {current_backup_path}")
            
            try:
                # Replace current database
                shutil.copy2(backup_path, self.db_path)
                
                # Test the imported database
                with self._get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM projects")
                    project_count = cursor.fetchone()[0]
                    print(f"Successfully imported database with {project_count} projects")
                
                return True
                
            except Exception as e:
                # Restore backup if import failed
                if current_backup_path and current_backup_path.exists():
                    shutil.copy2(current_backup_path, self.db_path)
                    print("Import failed, restored previous database")
                raise e
                
        except Exception as e:
            print(f"Error importing database: {e}")
            return False

    def delete_backup(self, backup_path: Path) -> bool:
        """Delete a backup file"""
        try:
            if backup_path.exists():
                backup_path.unlink()
                print(f"Deleted backup: {backup_path}")
                return True
            return False
        except Exception as e:
            print(f"Error deleting backup: {e}")
            return False

    def _cleanup_old_backups(self, backup_dir: Path, max_backups: int = 3):
        """Keep only the most recent backups"""
        try:
            backup_files = list(backup_dir.glob("*.db"))
            
            # Sort by modification time (most recent first)
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Remove files beyond the limit
            for old_backup in backup_files[max_backups:]:
                old_backup.unlink()
                print(f"Removed old backup: {old_backup}")
                
        except Exception as e:
            print(f"Warning: Cleanup of old backups failed: {e}")

    @property
    def projects_dir(self) -> Path:
        """Get projects directory for compatibility"""
        return self.config.data_dir / 'projects'

class ExportService:
    """Handles document export operations"""
    
    def __init__(self):
        self.odt_available = ODT_AVAILABLE
        self.pdf_available = PDF_AVAILABLE
        
        if not self.odt_available:
            print("Warning: ODT export not available (missing xml dependencies)")
        if not self.pdf_available:
            print("Warning: PDF export not available (missing reportlab)")

    def get_available_formats(self) -> List[str]:
        """Get list of available export formats"""
        formats = ['txt']
        
        if self.odt_available:
            formats.append('odt')
        if self.pdf_available:
            formats.append('pdf')
            
        return formats

    def export_project(self, project: Project, file_path: str, format_type: str) -> bool:
        """Export project to specified format"""
        try:
            if format_type.lower() == 'txt':
                return self._export_txt(project, file_path)
            elif format_type.lower() == 'odt' and self.odt_available:
                return self._export_odt(project, file_path)
            elif format_type.lower() == 'pdf' and self.pdf_available:
                return self._export_pdf(project, file_path)
            else:
                print(f"Export format '{format_type}' not available")
                return False
                
        except Exception as e:
            print(f"Error exporting project: {e}")
            return False

    def _export_txt(self, project: Project, file_path: str) -> bool:
        """Export to plain text format"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                # Project title
                f.write(f"{project.name}\n")
                f.write("=" * len(project.name) + "\n\n")
                
                # Group and write content
                current_paragraph_content = []
                paragraph_starts_with_introduction = False
                last_was_quote = False
                
                for i, paragraph in enumerate(project.paragraphs):
                    content = paragraph.content.strip()
                    
                    if paragraph.type == ParagraphType.TITLE_1:
                        # Write any accumulated content first
                        if current_paragraph_content:
                            combined_content = " ".join(current_paragraph_content)
                            if paragraph_starts_with_introduction:
                                f.write(f"    {combined_content}\n\n")  # Indented
                            else:
                                f.write(f"{combined_content}\n\n")  # Not indented
                            current_paragraph_content = []
                            paragraph_starts_with_introduction = False
                        
                        f.write(f"\n{content}\n")
                        f.write("-" * len(content) + "\n\n")
                        last_was_quote = False
                        
                    elif paragraph.type == ParagraphType.TITLE_2:
                        # Write any accumulated content first
                        if current_paragraph_content:
                            combined_content = " ".join(current_paragraph_content)
                            if paragraph_starts_with_introduction:
                                f.write(f"    {combined_content}\n\n")  # Indented
                            else:
                                f.write(f"{combined_content}\n\n")  # Not indented
                            current_paragraph_content = []
                            paragraph_starts_with_introduction = False
                        
                        f.write(f"\n{content}\n\n")
                        last_was_quote = False
                        
                    elif paragraph.type == ParagraphType.QUOTE:
                        # Write any accumulated content first
                        if current_paragraph_content:
                            combined_content = " ".join(current_paragraph_content)
                            if paragraph_starts_with_introduction:
                                f.write(f"    {combined_content}\n\n")  # Indented
                            else:
                                f.write(f"{combined_content}\n\n")  # Not indented
                            current_paragraph_content = []
                            paragraph_starts_with_introduction = False
                        
                        # Write quote indented
                        f.write(f"        {content}\n\n")
                        last_was_quote = True
                        
                    elif paragraph.type in [ParagraphType.INTRODUCTION, ParagraphType.ARGUMENT, ParagraphType.CONCLUSION]:
                        # Determine if should start new paragraph
                        should_start_new_paragraph = False
                        
                        if paragraph.type == ParagraphType.INTRODUCTION:
                            should_start_new_paragraph = True
                        elif last_was_quote:
                            should_start_new_paragraph = True
                        elif not current_paragraph_content:
                            should_start_new_paragraph = True
                        
                        # Write accumulated content if starting new paragraph
                        if should_start_new_paragraph and current_paragraph_content:
                            combined_content = " ".join(current_paragraph_content)
                            if paragraph_starts_with_introduction:
                                f.write(f"    {combined_content}\n\n")  # Indented
                            else:
                                f.write(f"{combined_content}\n\n")  # Not indented
                            current_paragraph_content = []
                            paragraph_starts_with_introduction = False
                        
                        # Determine paragraph style
                        if not current_paragraph_content:
                            if paragraph.type == ParagraphType.INTRODUCTION:
                                paragraph_starts_with_introduction = True
                            elif last_was_quote:
                                paragraph_starts_with_introduction = False
                            # If it's not INTRODUCTION and not after quote, keep current state
                        
                        # Accumulate content
                        current_paragraph_content.append(content)
                        
                        # Check if should write now
                        next_is_new_paragraph = False
                        if i + 1 < len(project.paragraphs):
                            next_paragraph = project.paragraphs[i + 1]
                            if (next_paragraph.type == ParagraphType.INTRODUCTION or
                                next_paragraph.type in [ParagraphType.TITLE_1, ParagraphType.TITLE_2, ParagraphType.QUOTE]):
                                next_is_new_paragraph = True
                        else:
                            next_is_new_paragraph = True
                        
                        if next_is_new_paragraph:
                            combined_content = " ".join(current_paragraph_content)
                            if paragraph_starts_with_introduction:
                                f.write(f"    {combined_content}\n\n")  # Indented
                            else:
                                f.write(f"{combined_content}\n\n")  # Not indented
                            current_paragraph_content = []
                            paragraph_starts_with_introduction = False
                        
                        last_was_quote = False
                
                # Write any remaining content
                if current_paragraph_content:
                    combined_content = " ".join(current_paragraph_content)
                    if paragraph_starts_with_introduction:
                        f.write(f"    {combined_content}\n\n")  # Indented
                    else:
                        f.write(f"{combined_content}\n\n")  # Not indented
            
            return True
            
        except Exception as e:
            print(f"Error exporting to TXT: {e}")
            return False

    def _export_odt(self, project: Project, file_path: str) -> bool:
        """Export to OpenDocument Text format"""
        try:
            # Create ODT structure
            odt_path = Path(file_path)
            
            # Create temporary directory
            temp_dir = odt_path.parent / f"temp_odt_{project.id}"
            temp_dir.mkdir(exist_ok=True)
            
            try:
                # Create ODT directory structure
                (temp_dir / "META-INF").mkdir(exist_ok=True)
                
                # Create manifest.xml
                self._create_manifest(temp_dir / "META-INF" / "manifest.xml")
                
                # Create styles.xml
                self._create_styles(temp_dir / "styles.xml")
                
                # Create content.xml
                content_xml = self._generate_odt_content(project)
                with open(temp_dir / "content.xml", 'w', encoding='utf-8') as f:
                    f.write(content_xml)
                
                # Create meta.xml
                self._create_meta(temp_dir / "meta.xml", project)
                
                # Create ZIP archive
                with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    # Add mimetype first (uncompressed)
                    zf.writestr("mimetype", "application/vnd.oasis.opendocument.text", 
                              compress_type=zipfile.ZIP_STORED)
                    
                    # Add other files
                    for root, dirs, files in temp_dir.walk():
                        for file in files:
                            file_path_obj = root / file
                            arc_name = file_path_obj.relative_to(temp_dir)
                            zf.write(file_path_obj, arc_name)
                
                return True
                
            finally:
                # Clean up temp directory
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        except Exception as e:
            print(f"Error exporting to ODT: {e}")
            return False

    def _generate_odt_content(self, project: Project) -> str:
        """Generate content.xml for ODT with proper formatting - Fixed paragraph grouping"""
        
        content_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" 
                        xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" 
                        xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" 
                        xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0">
<office:automatic-styles/>
<office:body>
<office:text>'''

        # Title
        content_xml += f'<text:p text:style-name="Title">{project.name}</text:p>\n'

        # Group content - CORRIGIDO
        current_paragraph_content = []
        paragraph_starts_with_introduction = False
        last_was_quote = False

        for i, paragraph in enumerate(project.paragraphs):
            # Escape XML special characters
            content = paragraph.content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            if paragraph.type == ParagraphType.TITLE_1:
                # Write any accumulated content first
                if current_paragraph_content:
                    combined_content = " ".join(current_paragraph_content)
                    style_name = "Introduction" if paragraph_starts_with_introduction else "Normal"
                    content_xml += f'<text:p text:style-name="{style_name}">{combined_content}</text:p>\n'
                    current_paragraph_content = []
                    paragraph_starts_with_introduction = False

                content_xml += f'<text:p text:style-name="Title1">{content}</text:p>\n'
                last_was_quote = False

            elif paragraph.type == ParagraphType.TITLE_2:
                # Write any accumulated content first
                if current_paragraph_content:
                    combined_content = " ".join(current_paragraph_content)
                    style_name = "Introduction" if paragraph_starts_with_introduction else "Normal"
                    content_xml += f'<text:p text:style-name="{style_name}">{combined_content}</text:p>\n'
                    current_paragraph_content = []
                    paragraph_starts_with_introduction = False

                content_xml += f'<text:p text:style-name="Title2">{content}</text:p>\n'
                last_was_quote = False

            elif paragraph.type == ParagraphType.QUOTE:
                # Write any accumulated content first
                if current_paragraph_content:
                    combined_content = " ".join(current_paragraph_content)
                    style_name = "Introduction" if paragraph_starts_with_introduction else "Normal"
                    content_xml += f'<text:p text:style-name="{style_name}">{combined_content}</text:p>\n'
                    current_paragraph_content = []
                    paragraph_starts_with_introduction = False

                # Write quote as separate paragraph
                content_xml += f'<text:p text:style-name="Quote">{content}</text:p>\n'
                last_was_quote = True

            elif paragraph.type in [ParagraphType.INTRODUCTION, ParagraphType.ARGUMENT, ParagraphType.CONCLUSION]:
                # Determine if should start new paragraph
                should_start_new_paragraph = False
                
                if paragraph.type == ParagraphType.INTRODUCTION:
                    should_start_new_paragraph = True
                elif last_was_quote:
                    should_start_new_paragraph = True
                elif not current_paragraph_content:
                    should_start_new_paragraph = True

                # If should start new paragraph, write accumulated content first
                if should_start_new_paragraph and current_paragraph_content:
                    combined_content = " ".join(current_paragraph_content)
                    style_name = "Introduction" if paragraph_starts_with_introduction else "Normal"
                    content_xml += f'<text:p text:style-name="{style_name}">{combined_content}</text:p>\n'
                    current_paragraph_content = []
                    paragraph_starts_with_introduction = False

                # Determine if this paragraph should have indent
                if not current_paragraph_content:
                    if paragraph.type == ParagraphType.INTRODUCTION:
                        paragraph_starts_with_introduction = True
                    elif last_was_quote:
                        paragraph_starts_with_introduction = False
                    # If it's ARGUMENT or CONCLUSION and not after quote, keep current state

                # Accumulate content
                current_paragraph_content.append(content.strip())

                # Determine when to write the grouped paragraph
                next_is_new_paragraph = False
                if i + 1 < len(project.paragraphs):
                    next_paragraph = project.paragraphs[i + 1]
                    if (next_paragraph.type == ParagraphType.INTRODUCTION or
                        next_paragraph.type in [ParagraphType.TITLE_1, ParagraphType.TITLE_2, ParagraphType.QUOTE]):
                        next_is_new_paragraph = True
                else:
                    next_is_new_paragraph = True

                if next_is_new_paragraph:
                    combined_content = " ".join(current_paragraph_content)
                    style_name = "Introduction" if paragraph_starts_with_introduction else "Normal"
                    content_xml += f'<text:p text:style-name="{style_name}">{combined_content}</text:p>\n'
                    current_paragraph_content = []
                    paragraph_starts_with_introduction = False

                last_was_quote = False

        # Write any remaining content
        if current_paragraph_content:
            combined_content = " ".join(current_paragraph_content)
            style_name = "Introduction" if paragraph_starts_with_introduction else "Normal"
            content_xml += f'<text:p text:style-name="{style_name}">{combined_content}</text:p>\n'

        content_xml += '''</office:text>
</office:body>
</office:document-content>'''

        return content_xml

    def _create_manifest(self, file_path: Path):
        """Create manifest.xml for ODT"""
        manifest_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">
  <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
  <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>
</manifest:manifest>'''
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(manifest_xml)

    def _create_styles(self, file_path: Path):
        """Create styles.xml for ODT"""
        styles_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" 
                       xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" 
                       xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0">
<office:styles>
  <style:style style:name="Title" style:family="paragraph">
    <style:text-properties fo:font-size="18pt" fo:font-weight="bold"/>
    <style:paragraph-properties fo:text-align="center" fo:margin-bottom="0.5cm"/>
  </style:style>
  
  <style:style style:name="Title1" style:family="paragraph">
    <style:text-properties fo:font-size="16pt" fo:font-weight="bold"/>
    <style:paragraph-properties fo:margin-top="0.5cm" fo:margin-bottom="0.3cm"/>
  </style:style>
  
  <style:style style:name="Title2" style:family="paragraph">
    <style:text-properties fo:font-size="14pt" fo:font-weight="bold"/>
    <style:paragraph-properties fo:margin-top="0.4cm" fo:margin-bottom="0.2cm"/>
  </style:style>
  
  <style:style style:name="Introduction" style:family="paragraph">
    <style:text-properties fo:font-size="12pt"/>
    <style:paragraph-properties fo:text-align="justify" fo:text-indent="1.5cm" fo:margin-bottom="0.0cm" fo:line-height="150%"/>
  </style:style>
  
  <style:style style:name="Normal" style:family="paragraph">
    <style:text-properties fo:font-size="12pt"/>
    <style:paragraph-properties fo:text-align="justify" fo:margin-bottom="0.0cm" fo:line-height="150%"/>
  </style:style>
  
  <style:style style:name="Quote" style:family="paragraph">
    <style:text-properties fo:font-size="10pt" fo:font-style="italic"/>
    <style:paragraph-properties fo:text-align="justify" fo:margin-left="4cm" fo:margin-bottom="0.3cm" fo:line-height="100%"/>
  </style:style>
</office:styles>
</office:document-styles>'''
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(styles_xml)

    def _create_meta(self, file_path: Path, project: Project):
        """Create meta.xml for ODT"""
        meta_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                     xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
                     xmlns:dc="http://purl.org/dc/elements/1.1/">
<office:meta>
  <meta:generator>TAC - Continuous Argumentation Technique</meta:generator>
  <dc:title>{project.name}</dc:title>
  <dc:creator>{project.metadata.get('author', '')}</dc:creator>
  <dc:description>{project.metadata.get('description', '')}</dc:description>
  <meta:creation-date>{project.created_at.isoformat()}</meta:creation-date>
  <dc:date>{project.modified_at.isoformat()}</dc:date>
</office:meta>
</office:document-meta>'''
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(meta_xml)

    def _export_pdf(self, project: Project, file_path: str) -> bool:
        """Export to PDF format"""
        try:
            # Create document
            doc = SimpleDocTemplate(
                file_path,
                pagesize=A4,
                rightMargin=3*cm,
                leftMargin=3*cm,
                topMargin=2.5*cm,
                bottomMargin=2.5*cm
            )
            
            # Get styles
            styles = getSampleStyleSheet()
            
            # Create custom styles
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Title'],
                fontSize=18,
                spaceAfter=30,
                alignment=TA_CENTER,
                fontName='Times-Bold'
            )

            title1_style = ParagraphStyle(
                'CustomTitle1',
                parent=styles['Heading1'],
                fontSize=16,
                spaceBefore=24,
                spaceAfter=12,
                leftIndent=0,
                fontName='Times-Bold'
            )

            title2_style = ParagraphStyle(
                'CustomTitle2',
                parent=styles['Heading2'],
                fontSize=14,
                spaceBefore=18,
                spaceAfter=9,
                leftIndent=0,
                fontName='Times-Bold'
            )

            introduction_style = ParagraphStyle(
                'Introduction',
                parent=styles['Normal'],
                fontSize=12,
                leading=18,
                firstLineIndent=1.5*cm,
                spaceBefore=12,
                spaceAfter=12,
                alignment=TA_JUSTIFY,
                fontName='Times-Roman'
            )

            normal_style = ParagraphStyle(
                'Normal',
                parent=styles['Normal'],
                fontSize=12,
                leading=18,
                spaceBefore=12,
                spaceAfter=12,
                alignment=TA_JUSTIFY,
                fontName='Times-Roman'
            )

            quote_style = ParagraphStyle(
                'Quote',
                parent=styles['Normal'],
                fontSize=10,
                leading=12,
                leftIndent=4*cm,
                spaceBefore=12,
                spaceAfter=12,
                fontName='Times-Italic',
                alignment=TA_JUSTIFY
            )
            
            # Build content
            story = []
            
            # Add title
            story.append(RLParagraph(project.name, title_style))
            story.append(Spacer(1, 20))
            
            # Group content - CORRIGIDO
            current_paragraph_content = []
            current_paragraph_style = None
            paragraph_starts_with_introduction = False
            last_was_quote = False
            
            for i, paragraph in enumerate(project.paragraphs):
                content = paragraph.content.strip()
                
                if paragraph.type == ParagraphType.TITLE_1:
                    # Write any accumulated content first
                    if current_paragraph_content:
                        combined_content = " ".join(current_paragraph_content)
                        story.append(RLParagraph(combined_content, current_paragraph_style))
                        current_paragraph_content = []
                        current_paragraph_style = None
                        paragraph_starts_with_introduction = False
                    
                    story.append(RLParagraph(content, title1_style))
                    last_was_quote = False
                    
                elif paragraph.type == ParagraphType.TITLE_2:
                    # Write any accumulated content first
                    if current_paragraph_content:
                        combined_content = " ".join(current_paragraph_content)
                        story.append(RLParagraph(combined_content, current_paragraph_style))
                        current_paragraph_content = []
                        current_paragraph_style = None
                        paragraph_starts_with_introduction = False
                    
                    story.append(RLParagraph(content, title2_style))
                    last_was_quote = False
                    
                elif paragraph.type == ParagraphType.QUOTE:
                    # Write any accumulated content first
                    if current_paragraph_content:
                        combined_content = " ".join(current_paragraph_content)
                        story.append(RLParagraph(combined_content, current_paragraph_style))
                        current_paragraph_content = []
                        current_paragraph_style = None
                        paragraph_starts_with_introduction = False
                    
                    # Add quote
                    story.append(RLParagraph(content, quote_style))
                    last_was_quote = True
                    
                elif paragraph.type in [ParagraphType.INTRODUCTION, ParagraphType.ARGUMENT, ParagraphType.CONCLUSION]:
                    # Determine if should start new paragraph
                    should_start_new_paragraph = False
                    
                    if paragraph.type == ParagraphType.INTRODUCTION:
                        should_start_new_paragraph = True
                    elif last_was_quote:
                        should_start_new_paragraph = True
                    elif not current_paragraph_content:
                        should_start_new_paragraph = True

                    # If should start new paragraph, write accumulated content first
                    if should_start_new_paragraph and current_paragraph_content:
                        combined_content = " ".join(current_paragraph_content)
                        story.append(RLParagraph(combined_content, current_paragraph_style))
                        current_paragraph_content = []
                        current_paragraph_style = None
                        paragraph_starts_with_introduction = False

                    # Check if this is the start of a new grouped paragraph
                    if not current_paragraph_content:
                        if paragraph.type == ParagraphType.INTRODUCTION:
                            paragraph_starts_with_introduction = True
                            current_paragraph_style = introduction_style
                        elif last_was_quote:
                            paragraph_starts_with_introduction = False
                            current_paragraph_style = normal_style
                        else:
                            # If it's ARGUMENT or CONCLUSION and not after quote, keep current state
                            if current_paragraph_style is None:
                                current_paragraph_style = normal_style

                    # Accumulate content
                    current_paragraph_content.append(content)

                    # Check if next paragraph starts a new logical paragraph
                    next_is_new_paragraph = False
                    if i + 1 < len(project.paragraphs):
                        next_paragraph = project.paragraphs[i + 1]
                        if (next_paragraph.type == ParagraphType.INTRODUCTION or
                            next_paragraph.type in [ParagraphType.TITLE_1, ParagraphType.TITLE_2, ParagraphType.QUOTE]):
                            next_is_new_paragraph = True
                    else:
                        next_is_new_paragraph = True

                    if next_is_new_paragraph:
                        combined_content = " ".join(current_paragraph_content)
                        story.append(RLParagraph(combined_content, current_paragraph_style))
                        current_paragraph_content = []
                        current_paragraph_style = None
                        paragraph_starts_with_introduction = False

                    last_was_quote = False
            
            # Write any remaining content
            if current_paragraph_content:
                combined_content = " ".join(current_paragraph_content)
                story.append(RLParagraph(combined_content, current_paragraph_style))
            
            # Build PDF
            doc.build(story)
            return True
            
        except Exception as e:
            print(f"Error exporting to PDF: {e}")
            return False


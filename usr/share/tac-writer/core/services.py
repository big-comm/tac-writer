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
            # For migration, use the transaction-aware method
            return True  # This will be handled by _run_migration_if_needed
            
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN IMMEDIATE;")
                
                try:
                    success = self._save_project_to_db(cursor, project)
                    if success:
                        conn.commit()
                        if not is_migration:
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

    def _calculate_word_count_python(self, content: str) -> int:
        """Calculate word count using Python (more accurate than SQL)"""
        if not content or not content.strip():
            return 0
        # Split on whitespace and filter empty strings
        words = [word for word in content.split() if word.strip()]
        return len(words)

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects from the database with accurate statistics"""
        projects_info = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Get basic project info first
                cursor.execute("""
                    SELECT p.id, p.name, p.created_at, p.modified_at,
                           COUNT(par.id) as paragraph_count
                    FROM projects p
                    LEFT JOIN paragraphs par ON p.id = par.project_id
                    GROUP BY p.id
                    ORDER BY p.modified_at DESC;
                """)
                rows = cursor.fetchall()
                
                for row in rows:
                    # Calculate accurate word count by loading content
                    cursor.execute("SELECT content FROM paragraphs WHERE project_id = ?", (row['id'],))
                    paragraph_contents = cursor.fetchall()
                    
                    total_words = sum(
                        self._calculate_word_count_python(content['content'] or '')
                        for content in paragraph_contents
                    )
                    
                    stats = {
                        'total_paragraphs': row['paragraph_count'],
                        'total_words': total_words,
                    }
                    
                    projects_info.append({
                        'id': row['id'],
                        'name': row['name'],
                        'created_at': row['created_at'],
                        'modified_at': row['modified_at'],
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
                alignment=TA_CENTER
            )
            
            title1_style = ParagraphStyle(
                'CustomTitle1',
                parent=styles['Heading1'],
                fontSize=16,
                spaceBefore=24,
                spaceAfter=12,
                leftIndent=0
            )
            
            title2_style = ParagraphStyle(
                'CustomTitle2',
                parent=styles['Heading2'],
                fontSize=14,
                spaceBefore=18,
                spaceAfter=9,
                leftIndent=0
            )
            
            introduction_style = ParagraphStyle(
                'Introduction',
                parent=styles['Normal'],
                fontSize=12,
                leading=18,
                firstLineIndent=1.5*cm,
                spaceBefore=12,
                spaceAfter=12,
                alignment=TA_JUSTIFY
            )
            
            normal_style = ParagraphStyle(
                'Normal',
                parent=styles['Normal'],
                fontSize=12,
                leading=18,
                spaceBefore=12,
                spaceAfter=12,
                alignment=TA_JUSTIFY
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


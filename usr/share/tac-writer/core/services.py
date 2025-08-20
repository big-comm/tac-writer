"""
TAC Core Services
Business logic and data services for the TAC application
"""

import json
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import shutil
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
    """Manages project operations"""
    
    def __init__(self):
        self.config = Config()
        self.projects_dir = self.config.projects_dir
        
        # Ensure projects directory exists
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"ProjectManager initialized with projects dir: {self.projects_dir}")

    def create_project(self, name: str, template: str = "academic_essay") -> Project:
        """Create a new project"""
        project = Project(name)
        
        # Apply template if specified
        if template == "academic_essay":
            # Start with empty project - user will add paragraphs manually
            pass
        
        # Save project
        success = self.save_project(project)
        if success:
            print(f"Created project: {project.name} ({project.id})")
            return project
        else:
            raise Exception("Failed to save new project")

    def save_project(self, project: Project) -> bool:
        """Save project to file"""
        try:
            project_file = self.get_project_path(project)
            
            # Ensure project directory exists
            project_file.parent.mkdir(parents=True, exist_ok=True)

            # Backup logic
            if self.config.get('backup_files', False) and project_file.exists():
                try:
                    safe_project_name = "".join(c for c in project.name if c.isalnum() or c in (' ', '-', '_')).strip()
                    safe_project_name = safe_project_name.replace(' ', '_')
                    backup_filename = f"{safe_project_name}_backup.json"
                    backup_dir = Path.home() / "Documents" / "TAC Projects" / "backups"
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    final_backup_path = backup_dir / backup_filename
                    
                    shutil.copy2(project_file, final_backup_path)
                    print(f"Backup created in: {final_backup_path}")
                except Exception as backup_error:
                    print(f"Warning: It was not possible to create backup file: {backup_error}")
            
            # Convert to dict and save
            project_data = project.to_dict()
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(project_data, f, indent=2, ensure_ascii=False)
            
            print(f"Saved project: {project.name}")
            return True
            
        except Exception as e:
            print(f"Error saving project: {e}")
            return False

    def load_project(self, project_id: str) -> Optional[Project]:
        """Load project by ID or file path"""
        try:
            # Check if project_id is actually a file path
            if project_id.endswith('.json'):
                project_file = Path(project_id)
            else:
                project_file = self.projects_dir / f"{project_id}.json"
            
            if not project_file.exists():
                print(f"Project file not found: {project_file}")
                return None
            
            # Load project data
            with open(project_file, 'r', encoding='utf-8') as f:
                project_data = json.load(f)
            
            project = Project.from_dict(project_data)
            print(f"Loaded project: {project.name}")
            return project
            
        except Exception as e:
            print(f"Error loading project: {e}")
            return None

    def delete_project(self, project_id: str) -> bool:
        """Delete project (move to trash)"""
        try:
            project_file = self.projects_dir / f"{project_id}.json"
            
            if not project_file.exists():
                return False
            
            # Move to trash folder (create if doesn't exist)
            trash_dir = self.projects_dir / ".trash"
            trash_dir.mkdir(exist_ok=True)
            
            trash_file = trash_dir / f"{project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            shutil.move(str(project_file), str(trash_file))
            
            print(f"Moved project to trash: {project_id}")
            return True
            
        except Exception as e:
            print(f"Error deleting project: {e}")
            return False

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects"""
        projects = []
        
        try:
            for project_file in self.projects_dir.glob("*.json"):
                try:
                    # Load basic project info
                    with open(project_file, 'r', encoding='utf-8') as f:
                        project_data = json.load(f)
                    
                    # Extract essential info
                    project_info = {
                        'id': project_data.get('id'),
                        'name': project_data.get('name'),
                        'created_at': project_data.get('created_at'),
                        'modified_at': project_data.get('modified_at'),
                        'statistics': project_data.get('statistics', {}),
                        'file_path': str(project_file)
                    }
                    
                    projects.append(project_info)
                    
                except Exception as e:
                    print(f"Error reading project file {project_file}: {e}")
                    continue
            
            # Sort by modification date (newest first)
            projects.sort(key=lambda p: p.get('modified_at', ''), reverse=True)
            
        except Exception as e:
            print(f"Error listing projects: {e}")
        
        return projects

    def get_project_path(self, project: Project) -> Path:
        """Get file path for a project"""
        return self.projects_dir / f"{project.id}.json"

    def import_project(self, file_path: str) -> Optional[Project]:
        """Import project from file"""
        try:
            source_path = Path(file_path)
            if not source_path.exists():
                return None
            
            # Load project
            project = self.load_project(file_path)
            if not project:
                return None
            
            # Copy to projects directory if not already there
            target_path = self.get_project_path(project)
            if source_path != target_path:
                shutil.copy2(source_path, target_path)
            
            return project
            
        except Exception as e:
            print(f"Error importing project: {e}")
            return None

    def export_project(self, project: Project, target_path: str) -> bool:
        """Export project to file"""
        try:
            source_path = self.get_project_path(project)
            shutil.copy2(source_path, target_path)
            return True
        except Exception as e:
            print(f"Error exporting project: {e}")
            return False

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
        formats = ['txt']  # Text always available
        
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


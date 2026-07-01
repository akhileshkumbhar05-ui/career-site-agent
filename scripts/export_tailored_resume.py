import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from app.services.resume_render_service import ResumeRenderService

master_resume = json.loads(Path('data/master_resume/master_resume.json').read_text())
projects = master_resume.get('projects', [])[:3]
service = ResumeRenderService()
output = service.render_html(
    'data/outputs/tailored_resumes/sample_tailored_resume.html',
    master_resume['candidate'],
    projects,
    skills=master_resume.get('skills', {}),
    experience=master_resume.get('experience', []),
    education=master_resume.get('education', []),
    publications=master_resume.get('publications', []),
)
print(f'Rendered to {output}')

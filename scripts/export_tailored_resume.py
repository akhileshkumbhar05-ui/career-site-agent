import json
from pathlib import Path

from app.services.resume_render_service import ResumeRenderService

master_resume = json.loads(Path('data/master_resume/master_resume.json').read_text())
projects = master_resume.get('projects', [])[:3]
service = ResumeRenderService()
output = service.render_html('data/outputs/tailored_resumes/sample_tailored_resume.html', master_resume['candidate'], projects)
print(f'Rendered to {output}')

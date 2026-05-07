from pathlib import Path
from jinja2 import Template


class ResumeRenderService:
    def render_html(self, output_path: str, candidate: dict, selected_projects: list[dict]) -> str:
        template_path = Path("templates/resume_template.html")
        template = Template(template_path.read_text())
        rendered = template.render(candidate=candidate, projects=selected_projects)
        Path(output_path).write_text(rendered)
        return output_path

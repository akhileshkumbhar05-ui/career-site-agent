from pathlib import Path
import json

sample_dir = Path('data/sample_jobs')
for path in sample_dir.glob('sample_jd_*.json'):
    data = json.loads(path.read_text())
    print(f"Loaded {data['job_id']} - {data['title']}")

from app.schemas.job import JobLead


class DiscoveryService:
    def normalize(self, job: JobLead) -> JobLead:
        return JobLead(
            company=job.company.strip(),
            title=job.title.strip(),
            discovered_url=job.discovered_url.strip(),
            source=job.source.strip(),
            location=job.location,
            posted_date=job.posted_date,
        )

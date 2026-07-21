"""Deduplication tool based on content hash."""

import hashlib


def compute_content_hash(title: str, company: str, description: str = "") -> str:
    """Compute a content hash for deduplication."""
    content = f"{title.strip().lower()}:{company.strip().lower()}:{description.strip()[:200]}"
    return hashlib.sha256(content.encode()).hexdigest()


def dedup_jobs(jobs: list[dict]) -> list[dict]:
    """Deduplicate jobs based on content hash.

    Args:
        jobs: List of job dicts with at least 'title' and 'company' fields

    Returns:
        Deduplicated list of jobs
    """
    seen_hashes: set[str] = set()
    unique_jobs: list[dict] = []

    for job in jobs:
        content_hash = compute_content_hash(
            title=job.get("title", ""),
            company=job.get("company", ""),
            description=job.get("raw_description", ""),
        )
        if content_hash not in seen_hashes:
            seen_hashes.add(content_hash)
            job["content_hash"] = content_hash
            unique_jobs.append(job)

    return unique_jobs

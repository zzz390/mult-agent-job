"""Unit tests for deduplication tool."""

from job_agent_os.tools.common.dedup import compute_content_hash, dedup_jobs


class TestComputeContentHash:
    """Test content hash computation."""

    def test_same_input_same_hash(self):
        """Same inputs should produce the same hash."""
        hash1 = compute_content_hash("Java开发", "阿里巴巴")
        hash2 = compute_content_hash("Java开发", "阿里巴巴")
        assert hash1 == hash2

    def test_different_title_different_hash(self):
        """Different titles should produce different hashes."""
        hash1 = compute_content_hash("Java开发", "阿里巴巴")
        hash2 = compute_content_hash("Python开发", "阿里巴巴")
        assert hash1 != hash2

    def test_different_company_different_hash(self):
        """Different companies should produce different hashes."""
        hash1 = compute_content_hash("Java开发", "阿里巴巴")
        hash2 = compute_content_hash("Java开发", "腾讯")
        assert hash1 != hash2

    def test_case_insensitive(self):
        """Hash should be case-insensitive for title and company."""
        hash1 = compute_content_hash("Java Developer", "Alibaba")
        hash2 = compute_content_hash("java developer", "alibaba")
        assert hash1 == hash2

    def test_whitespace_trimmed(self):
        """Leading/trailing whitespace should be trimmed."""
        hash1 = compute_content_hash("  Java开发  ", "  阿里巴巴  ")
        hash2 = compute_content_hash("Java开发", "阿里巴巴")
        assert hash1 == hash2

    def test_description_truncated(self):
        """Description beyond 200 chars should not affect hash."""
        long_desc = "A" * 300
        short_desc = "A" * 200
        hash1 = compute_content_hash("Java", "公司", long_desc)
        hash2 = compute_content_hash("Java", "公司", short_desc)
        assert hash1 == hash2

    def test_hash_is_sha256_hex(self):
        """Hash should be a valid SHA256 hex string."""
        h = compute_content_hash("test", "company")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestDedupJobs:
    """Test job deduplication."""

    def test_no_duplicates(self):
        """Jobs with different content should all be kept."""
        jobs = [
            {"title": "Java开发", "company": "阿里巴巴"},
            {"title": "Python开发", "company": "腾讯"},
            {"title": "前端开发", "company": "字节跳动"},
        ]
        result = dedup_jobs(jobs)
        assert len(result) == 3

    def test_exact_duplicates_removed(self):
        """Exact duplicate jobs should be removed."""
        jobs = [
            {"title": "Java开发", "company": "阿里巴巴"},
            {"title": "Java开发", "company": "阿里巴巴"},
            {"title": "Python开发", "company": "腾讯"},
        ]
        result = dedup_jobs(jobs)
        assert len(result) == 2

    def test_case_insensitive_dedup(self):
        """Dedup should be case-insensitive."""
        jobs = [
            {"title": "Java Developer", "company": "Alibaba"},
            {"title": "java developer", "company": "alibaba"},
        ]
        result = dedup_jobs(jobs)
        assert len(result) == 1

    def test_content_hash_added_to_jobs(self):
        """Each deduplicated job should have a content_hash field."""
        jobs = [
            {"title": "Java开发", "company": "阿里巴巴"},
        ]
        result = dedup_jobs(jobs)
        assert "content_hash" in result[0]
        assert len(result[0]["content_hash"]) == 64

    def test_empty_list(self):
        """Empty input should return empty output."""
        result = dedup_jobs([])
        assert result == []

    def test_preserves_order(self):
        """First occurrence should be preserved."""
        jobs = [
            {"title": "Java开发", "company": "阿里巴巴", "source": "boss"},
            {"title": "Java开发", "company": "阿里巴巴", "source": "guopin"},
        ]
        result = dedup_jobs(jobs)
        assert len(result) == 1
        assert result[0]["source"] == "boss"

    def test_missing_fields_handled(self):
        """Jobs with missing fields should not crash."""
        jobs = [
            {"title": "Java开发"},
            {"company": "阿里巴巴"},
            {},
        ]
        result = dedup_jobs(jobs)
        assert len(result) == 3  # All different due to different field combos

    def test_description_affects_dedup(self):
        """Different descriptions should result in different hashes."""
        jobs = [
            {"title": "Java开发", "company": "阿里巴巴", "raw_description": "负责后端开发"},
            {"title": "Java开发", "company": "阿里巴巴", "raw_description": "负责数据平台"},
        ]
        result = dedup_jobs(jobs)
        assert len(result) == 2

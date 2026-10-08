import unittest

from job_alert_bot import filter_jobs, format_job


class JobAlertBotTests(unittest.TestCase):
    def setUp(self):
        self.jobs = [
            {
                "title": "Python Backend Engineer",
                "company_name": "Acme",
                "candidate_required_location": "Worldwide",
                "description": "Build APIs with Python and FastAPI",
                "url": "https://example.com/job1",
            },
            {
                "title": "Frontend Developer",
                "company_name": "Beta",
                "candidate_required_location": "US",
                "description": "React role",
                "url": "https://example.com/job2",
            },
        ]

    def test_filter_jobs_by_keyword(self):
        results = filter_jobs(self.jobs, keywords=["python"])
        self.assertEqual(1, len(results))
        self.assertEqual("Python Backend Engineer", results[0]["title"])

    def test_filter_jobs_by_location(self):
        results = filter_jobs(self.jobs, location="US")
        self.assertEqual(1, len(results))
        self.assertEqual("Frontend Developer", results[0]["title"])

    def test_filter_jobs_by_keyword_and_location(self):
        results = filter_jobs(self.jobs, keywords=["python"], location="world")
        self.assertEqual(1, len(results))
        self.assertEqual("Python Backend Engineer", results[0]["title"])

    def test_format_job(self):
        rendered = format_job(self.jobs[0])
        self.assertIn("Python Backend Engineer", rendered)
        self.assertIn("Acme", rendered)
        self.assertIn("https://example.com/job1", rendered)


if __name__ == "__main__":
    unittest.main()

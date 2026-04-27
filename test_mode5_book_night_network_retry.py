import unittest


class Mode5BookNightNetworkRetryTests(unittest.TestCase):
    def test_transient_error_detection_catches_dns_and_connection(self):
        from modes.mode5.book_night_generator import _is_transient_llm_error

        self.assertTrue(_is_transient_llm_error(Exception("Connection error.")))
        self.assertTrue(_is_transient_llm_error(Exception("[Errno 11001] getaddrinfo failed")))
        self.assertTrue(_is_transient_llm_error(Exception("HTTP 503 Service Unavailable")))

    def test_transient_error_detection_ignores_schema_failures(self):
        from modes.mode5.book_night_generator import _is_transient_llm_error

        self.assertFalse(_is_transient_llm_error(ValueError("Could not parse LLM JSON")))
        self.assertFalse(_is_transient_llm_error(RuntimeError("missing field chapters")))


if __name__ == "__main__":
    unittest.main()

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from app import create_app


class QuizApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "quiz.db"
        self.app = create_app(self.database_path)
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def get_questions(self):
        response = self.client.get("/api/questions")
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def make_answers(self, choices=None):
        questions = self.get_questions()
        choices = choices or [question["options"]["A"] for question in questions]
        return [
            {"question_id": question["id"], "answer": choice}
            for question, choice in zip(questions, choices)
        ]

    def test_health_and_questions_hide_answer_key(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json(), {"status": "ok", "database": "connected"})

        questions = self.get_questions()
        self.assertEqual(len(questions), 10)
        for question in questions:
            self.assertEqual(set(question["options"]), {"A", "B", "C", "D"})
            self.assertNotIn("correct_answer", question)
            self.assertNotIn("answer", question)
            self.assertNotIn("explanation", question)

    def test_submission_is_scored_and_persisted(self):
        choices = ["B", "C", "B", "B", "A", "C", "A", "B", "C", "A"]
        response = self.client.post(
            "/api/submit", json={"answers": self.make_answers(choices), "score": 0}
        )
        self.assertEqual(response.status_code, 201)
        result = response.get_json()
        self.assertEqual(result["score"], 10)
        self.assertEqual(result["total_questions"], 10)
        self.assertEqual(result["percentage"], 100)
        self.assertEqual(result["correct_answers"], 10)
        self.assertEqual(result["incorrect_answers"], 0)
        self.assertEqual(result["unanswered_questions"], 0)
        self.assertEqual(result["review"][0]["status"], "Correct")
        self.assertIn("<h1>", result["review"][0]["explanation"])
        self.assertEqual(self.client.get("/api/results").get_json()[0]["correct_answers"], 10)

        connection = sqlite3.connect(self.database_path)
        connection.execute(
            "UPDATE questions SET question = ? WHERE id = 1",
            ("Edited after this attempt",),
        )
        connection.commit()
        connection.close()

        self.app = create_app(self.database_path)
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()
        history = self.client.get("/api/results")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.get_json()), 1)
        self.assertEqual(history.get_json()[0]["score"], 10)
        self.assertTrue(history.get_json()[0]["review_available"])
        detail = self.client.get(f"/api/results/{result['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(
            detail.get_json()["review"][0]["question"],
            "Which HTML element represents the main heading of a page?",
        )
        self.assertEqual(detail.get_json()["review"][0]["correct_option"], "<h1>")

    def test_review_marks_selected_wrong_and_correct_options(self):
        answers = self.make_answers(["A"] * 10)
        response = self.client.post("/api/submit", json={"answers": answers})
        review = response.get_json()["review"]
        self.assertEqual(review[0]["status"], "Incorrect")
        self.assertEqual(review[0]["selected_answer"], "A")
        self.assertEqual(review[0]["correct_answer"], "B")
        self.assertEqual(review[0]["selected_option"], "<head>")
        self.assertEqual(review[0]["correct_option"], "<h1>")
        self.assertNotIn("correct_answer", self.get_questions()[0])

    def test_submission_calculates_partial_score(self):
        choices = ["A"] * 10
        response = self.client.post(
            "/api/submit", json={"answers": self.make_answers(choices)}
        )
        result = response.get_json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(result["score"], 3)
        self.assertEqual(result["correct_answers"], 3)
        self.assertEqual(result["incorrect_answers"], 7)
        self.assertEqual(result["unanswered_questions"], 0)
        self.assertEqual(result["percentage"], 30)

    def test_submission_calculates_fully_incorrect_result(self):
        choices = ["A" if answer != "A" else "B" for answer in ["B", "C", "B", "B", "A", "C", "A", "B", "C", "A"]]
        response = self.client.post(
            "/api/submit", json={"answers": self.make_answers(choices)}
        )
        result = response.get_json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(result["correct_answers"], 0)
        self.assertEqual(result["incorrect_answers"], 10)
        self.assertEqual(result["unanswered_questions"], 0)
        self.assertEqual(result["percentage"], 0)
        self.assertTrue(all(item["status"] == "Incorrect" for item in result["review"]))

    def test_submission_counts_unanswered_questions(self):
        choices = ["B", None, "B", "A", None, "C", None, "B", None, "A"]
        response = self.client.post(
            "/api/submit", json={"answers": self.make_answers(choices)}
        )
        result = response.get_json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(result["correct_answers"], 5)
        self.assertEqual(result["incorrect_answers"], 1)
        self.assertEqual(result["unanswered_questions"], 4)
        self.assertEqual(result["percentage"], 50)
        unanswered = [item for item in result["review"] if item["status"] == "Unanswered"]
        self.assertEqual(len(unanswered), 4)
        self.assertTrue(all(item["selected_option"] is None for item in unanswered))
        self.assertTrue(all(item["correct_option"] for item in unanswered))

    def test_all_questions_can_be_unanswered(self):
        response = self.client.post(
            "/api/submit", json={"answers": self.make_answers([None] * 10)}
        )
        result = response.get_json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["correct_answers"], 0)
        self.assertEqual(result["incorrect_answers"], 0)
        self.assertEqual(result["unanswered_questions"], 10)

    def test_pass_status_only_appears_when_configured(self):
        app_with_pass_mark = create_app(self.database_path, pass_mark_percent=70)
        app_with_pass_mark.config.update(TESTING=True)
        response = app_with_pass_mark.test_client().post(
            "/api/submit",
            json={"answers": self.make_answers(["A"] * 10)},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["pass_mark_percent"], 70)
        self.assertFalse(response.get_json()["passed"])

    def test_migrates_legacy_schema_and_missing_explanation(self):
        legacy_database_path = Path(self.temporary_directory.name) / "legacy.db"
        connection = sqlite3.connect(legacy_database_path)
        connection.executescript(
            """
            CREATE TABLE questions (
                id INTEGER PRIMARY KEY, category TEXT NOT NULL, question TEXT NOT NULL,
                option_a TEXT NOT NULL, option_b TEXT NOT NULL, option_c TEXT NOT NULL,
                option_d TEXT NOT NULL, correct_answer TEXT NOT NULL
            );
            INSERT INTO questions VALUES (1, 'Custom', 'Legacy question?', 'One', 'Two', 'Three', 'Four', 'B');
            CREATE TABLE quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, score INTEGER NOT NULL,
                total_questions INTEGER NOT NULL, percentage REAL NOT NULL, attempted_at TEXT NOT NULL
            );
            INSERT INTO quiz_attempts VALUES (1, 1, 1, 100, '2024-01-01T00:00:00+00:00');
            """
        )
        connection.commit()
        connection.close()

        migrated_app = create_app(legacy_database_path)
        migrated_app.config.update(TESTING=True)
        client = migrated_app.test_client()
        legacy_attempt = client.get("/api/results").get_json()[0]
        self.assertEqual(legacy_attempt["correct_answers"], 1)
        self.assertFalse(legacy_attempt["review_available"])

        submission = client.post(
            "/api/submit", json={"answers": [{"question_id": 1, "answer": None}]}
        )
        self.assertEqual(submission.status_code, 201)
        review = submission.get_json()["review"][0]
        self.assertEqual(review["explanation"], "Explanation not available")
        self.assertEqual(review["status"], "Unanswered")
        self.assertEqual(client.get("/api/results/1").status_code, 404)
        self.assertEqual(client.get(f"/api/results/{submission.get_json()['id']}").status_code, 200)

    def test_unknown_attempt_review_returns_404(self):
        response = self.client.get("/api/results/9999")
        self.assertEqual(response.status_code, 404)

    def test_admin_viewer_lists_every_discovered_table(self):
        connection = sqlite3.connect(self.database_path)
        expected_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        expected_counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in expected_tables
        }
        connection.close()

        response = self.client.get("/api/admin/tables")
        self.assertEqual(response.status_code, 200)
        tables = response.get_json()["tables"]
        self.assertEqual({table["name"] for table in tables}, expected_tables)
        self.assertEqual(
            {table["name"]: table["record_count"] for table in tables},
            expected_counts,
        )

        for table_name in expected_tables:
            table_response = self.client.get(f"/api/admin/tables/{table_name}")
            self.assertEqual(table_response.status_code, 200)
            table_data = table_response.get_json()
            self.assertTrue(table_data["columns"])
            self.assertEqual(table_data["total_records"], expected_counts[table_name])
            self.assertEqual(len(table_data["records"]), expected_counts[table_name])
            self.assertEqual(table_data["page"], 1)

    def test_admin_viewer_paginates_with_parameterized_limits(self):
        first_page = self.client.get("/api/admin/tables/questions?page=1&page_size=4")
        third_page = self.client.get("/api/admin/tables/questions?page=3&page_size=4")
        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(third_page.status_code, 200)
        self.assertEqual(len(first_page.get_json()["records"]), 4)
        self.assertEqual(len(third_page.get_json()["records"]), 2)
        self.assertEqual(third_page.get_json()["total_records"], 10)
        self.assertEqual(third_page.get_json()["total_pages"], 3)
        self.assertEqual(first_page.get_json()["records"][0]["id"], 1)
        self.assertEqual(third_page.get_json()["records"][0]["id"], 9)

    def test_admin_viewer_reports_empty_tables_and_keeps_database_read_only(self):
        before = self.client.get("/api/admin/tables").get_json()
        attempts = self.client.get("/api/admin/tables/quiz_attempts").get_json()
        reviews = self.client.get("/api/admin/tables/quiz_attempt_reviews").get_json()
        after = self.client.get("/api/admin/tables").get_json()

        self.assertEqual(attempts["total_records"], 0)
        self.assertEqual(attempts["records"], [])
        self.assertEqual(reviews["total_records"], 0)
        self.assertEqual(reviews["records"], [])
        self.assertEqual(before, after)
        self.assertEqual(self.client.get("/api/results").get_json(), [])

    def test_admin_viewer_rejects_unknown_tables_and_invalid_pagination(self):
        unknown = self.client.get("/api/admin/tables/questions%3BDROP%20TABLE%20questions")
        invalid_page = self.client.get("/api/admin/tables/questions?page=0")
        invalid_page_size = self.client.get("/api/admin/tables/questions?page_size=101")
        invalid_number = self.client.get("/api/admin/tables/questions?page=one")
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(invalid_page.status_code, 400)
        self.assertEqual(invalid_page_size.status_code, 400)
        self.assertEqual(invalid_number.status_code, 400)

    def test_admin_viewer_redacts_sensitive_columns(self):
        connection = sqlite3.connect(self.database_path)
        connection.execute(
            "CREATE TABLE admin_test (id INTEGER PRIMARY KEY, user_id INTEGER, password_hash TEXT, email TEXT, api_key TEXT, note TEXT)"
        )
        connection.execute(
            "INSERT INTO admin_test (user_id, password_hash, email, api_key, note) VALUES (?, ?, ?, ?, ?)",
            (42, "hashed-value", "person@example.test", "secret-token", "visible"),
        )
        connection.commit()
        connection.close()

        response = self.client.get("/api/admin/tables/admin_test")
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(
            result["records"][0],
            {
                "id": 1,
                "user_id": "[REDACTED]",
                "password_hash": "[REDACTED]",
                "email": "[REDACTED]",
                "api_key": "[REDACTED]",
                "note": "visible",
            },
        )
        self.assertTrue(all(column["redacted"] for column in result["columns"] if column["name"] in {"user_id", "password_hash", "email", "api_key"}))

    def test_admin_viewer_endpoints_are_loopback_only(self):
        tables_response = self.client.get(
            "/api/admin/tables", environ_overrides={"REMOTE_ADDR": "203.0.113.10"}
        )
        records_response = self.client.get(
            "/api/admin/tables/questions", environ_overrides={"REMOTE_ADDR": "203.0.113.10"}
        )
        page_response = self.client.get(
            "/admin/database", environ_overrides={"REMOTE_ADDR": "203.0.113.10"}
        )
        self.assertEqual(tables_response.status_code, 403)
        self.assertEqual(records_response.status_code, 403)
        self.assertEqual(page_response.status_code, 403)
        page_response = self.client.get("/admin/database")
        self.assertEqual(page_response.status_code, 200)
        page_response.close()

    def test_admin_viewer_reports_database_errors(self):
        self.app.config["DATABASE_PATH"] = str(
            Path(self.temporary_directory.name) / "unavailable.db"
        )
        response = self.client.get("/api/admin/tables")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.get_json(),
            {"error": "The quiz database is temporarily unavailable."},
        )

    def test_rejects_non_json_and_malformed_json(self):
        non_json = self.client.post("/api/submit", data="answers")
        malformed = self.client.post(
            "/api/submit", data="{", content_type="application/json"
        )
        self.assertEqual(non_json.status_code, 400)
        self.assertEqual(malformed.status_code, 400)

    def test_rejects_missing_answers_and_duplicate_ids(self):
        answers = self.make_answers()
        missing = self.client.post("/api/submit", json={"answers": answers[:-1]})
        duplicate_answers = answers.copy()
        duplicate_answers[-1] = dict(duplicate_answers[0])
        duplicate = self.client.post(
            "/api/submit", json={"answers": duplicate_answers}
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(duplicate.status_code, 400)

    def test_rejects_unknown_question_and_invalid_answer(self):
        unknown_answers = self.make_answers()
        unknown_answers[0]["question_id"] = 9999
        unknown = self.client.post(
            "/api/submit", json={"answers": unknown_answers}
        )

        invalid_answers = self.make_answers()
        invalid_answers[0]["answer"] = "Z"
        invalid = self.client.post(
            "/api/submit", json={"answers": invalid_answers}
        )
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(invalid.status_code, 400)

    def test_non_object_json_is_rejected(self):
        response = self.client.post(
            "/api/submit", data=json.dumps([{"answer": "A"}]),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
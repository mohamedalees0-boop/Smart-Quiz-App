from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from flask import Flask, jsonify, request, send_from_directory


BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
DEFAULT_DATABASE_PATH = BACKEND_DIR / "quiz.db"
ANSWER_LETTERS = ("A", "B", "C", "D")

SEED_QUESTIONS = (
    (
        "HTML",
        "Which HTML element represents the main heading of a page?",
        "<head>",
        "<h1>",
        "<header>",
        "<title>",
        "B",
        "The <h1> element marks the page's top-level heading. A page should usually have one main h1 describing its primary content.",
    ),
    (
        "CSS",
        "Which CSS property changes the color of text?",
        "font-style",
        "background-color",
        "color",
        "text-decoration",
        "C",
        "The color property sets text color. background-color changes the element's background, while the other options control different text styling.",
    ),
    (
        "JavaScript",
        "Which keyword declares a block-scoped variable that can be reassigned?",
        "const",
        "let",
        "static",
        "define",
        "B",
        "let declares a block-scoped variable that can be reassigned. const is also block-scoped but cannot be reassigned.",
    ),
    (
        "Python",
        "What is the output of len([4, 8, 12]) in Python?",
        "2",
        "3",
        "4",
        "An error",
        "B",
        "len() returns the number of items in a collection. This list contains three values, so its length is 3.",
    ),
    (
        "Artificial intelligence",
        "What does a machine-learning model learn from during training?",
        "Examples in data",
        "A fixed set of if-statements",
        "The computer's wallpaper",
        "Only its file name",
        "A",
        "Machine-learning models learn patterns from examples in training data, then use those patterns to make predictions or generate content.",
    ),
    (
        "HTML",
        "Which attribute provides alternative text for an image?",
        "title",
        "src",
        "alt",
        "href",
        "C",
        "The alt attribute provides a text alternative for an image. Screen readers can announce it, and browsers can show it if the image fails to load.",
    ),
    (
        "CSS",
        "Which layout system is designed for arranging items in rows or columns?",
        "Flexbox",
        "Float-only layout",
        "Text transform",
        "Z-index",
        "A",
        "Flexbox arranges items along one dimension, either as a row or a column, and helps distribute space between them.",
    ),
    (
        "JavaScript",
        "Which method selects an element by its CSS selector?",
        "document.find()",
        "document.querySelector()",
        "document.getStyle()",
        "window.select()",
        "B",
        "document.querySelector() accepts a CSS selector and returns the first matching element in the document.",
    ),
    (
        "Python",
        "Which Python keyword starts a function definition?",
        "func",
        "function",
        "def",
        "make",
        "C",
        "The def keyword begins a function definition in Python, followed by the function name and its parameters.",
    ),
    (
        "Artificial intelligence",
        "What is a common goal of generative AI?",
        "Create new content from learned patterns",
        "Replace every computer program",
        "Guarantee every answer is correct",
        "Work without any input or data",
        "A",
        "Generative AI learns patterns from training examples and uses them to create new content, such as text or images.",
    ),
)


def connect_database(database_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(database_path: str) -> None:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    connection = connect_database(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                question TEXT NOT NULL,
                option_a TEXT NOT NULL,
                option_b TEXT NOT NULL,
                option_c TEXT NOT NULL,
                option_d TEXT NOT NULL,
                correct_answer TEXT NOT NULL CHECK (correct_answer IN ('A', 'B', 'C', 'D')),
                explanation TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                score INTEGER NOT NULL CHECK (score >= 0),
                total_questions INTEGER NOT NULL CHECK (total_questions > 0),
                correct_answers INTEGER NOT NULL DEFAULT 0,
                incorrect_answers INTEGER NOT NULL DEFAULT 0,
                unanswered_questions INTEGER NOT NULL DEFAULT 0,
                percentage REAL NOT NULL CHECK (percentage >= 0 AND percentage <= 100),
                attempted_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS quiz_attempt_reviews (
                attempt_id INTEGER NOT NULL REFERENCES quiz_attempts(id) ON DELETE CASCADE,
                question_number INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                question_text TEXT NOT NULL,
                option_a TEXT NOT NULL,
                option_b TEXT NOT NULL,
                option_c TEXT NOT NULL,
                option_d TEXT NOT NULL,
                selected_answer TEXT,
                correct_answer TEXT NOT NULL,
                explanation TEXT NOT NULL,
                PRIMARY KEY (attempt_id, question_number)
            );
            """
        )

        question_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(questions)")
        }
        if "explanation" not in question_columns:
            connection.execute(
                "ALTER TABLE questions ADD COLUMN explanation TEXT NOT NULL DEFAULT ''"
            )

        attempt_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(quiz_attempts)")
        }
        for column in ("correct_answers", "incorrect_answers", "unanswered_questions"):
            if column not in attempt_columns:
                connection.execute(
                    f"ALTER TABLE quiz_attempts ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
                )
        connection.execute(
            """
            UPDATE quiz_attempts
            SET correct_answers = score,
                incorrect_answers = total_questions - score
            WHERE correct_answers = 0
                AND incorrect_answers = 0
                AND unanswered_questions = 0
            """
        )

        # Seed once so existing questions and attempt history survive restarts.
        question_count = connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        if question_count == 0:
            connection.executemany(
                """
                INSERT INTO questions (
                    category, question, option_a, option_b, option_c, option_d,
                    correct_answer, explanation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                SEED_QUESTIONS,
            )
        else:
            connection.executemany(
                """
                UPDATE questions SET explanation = ?
                WHERE id = ? AND explanation = '' AND category = ? AND question = ?
                """,
                (
                    (seed[7], index, seed[0], seed[1])
                    for index, seed in enumerate(SEED_QUESTIONS, start=1)
                ),
            )
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def serialize_review_row(row: sqlite3.Row | dict) -> dict:
    options = {
        "A": row["option_a"],
        "B": row["option_b"],
        "C": row["option_c"],
        "D": row["option_d"],
    }
    selected_answer = row["selected_answer"]
    correct_answer = row["correct_answer"]
    status = (
        "Unanswered"
        if selected_answer is None
        else "Correct"
        if selected_answer == correct_answer
        else "Incorrect"
    )
    return {
        "question_number": row["question_number"],
        "question_id": row["question_id"],
        "category": row["category"],
        "question": row["question_text"],
        "options": options,
        "selected_answer": selected_answer,
        "selected_option": options[selected_answer] if selected_answer else None,
        "correct_answer": correct_answer,
        "correct_option": options[correct_answer],
        "status": status,
        "explanation": row["explanation"] or "Explanation not available",
    }


def create_app(
    database_path: str | Path | None = None,
    pass_mark_percent: float | None = None,
) -> Flask:
    if pass_mark_percent is not None and not 0 <= pass_mark_percent <= 100:
        raise ValueError("pass_mark_percent must be between 0 and 100.")

    app = Flask(__name__, static_folder=None)
    resolved_database_path = str(database_path or DEFAULT_DATABASE_PATH)
    app.config["DATABASE_PATH"] = resolved_database_path
    app.config["PASS_MARK_PERCENT"] = pass_mark_percent
    initialize_database(resolved_database_path)

    @app.get("/")
    def serve_home():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/<path:filename>")
    def serve_frontend_file(filename: str):
        return send_from_directory(FRONTEND_DIR, filename)

    @app.get("/api/health")
    def health_check():
        connection = connect_database(app.config["DATABASE_PATH"])
        try:
            connection.execute("SELECT 1").fetchone()
        finally:
            connection.close()
        return jsonify({"status": "ok", "database": "connected"})

    @app.get("/api/questions")
    def get_questions():
        connection = connect_database(app.config["DATABASE_PATH"])
        try:
            rows = connection.execute(
                """
                SELECT id, category, question, option_a, option_b, option_c, option_d
                FROM questions ORDER BY id
                """
            ).fetchall()
        finally:
            connection.close()

        return jsonify(
            [
                {
                    "id": row["id"],
                    "category": row["category"],
                    "question": row["question"],
                    "options": {
                        "A": row["option_a"],
                        "B": row["option_b"],
                        "C": row["option_c"],
                        "D": row["option_d"],
                    },
                }
                for row in rows
            ]
        )

    @app.post("/api/submit")
    def submit_quiz():
        if not request.is_json:
            return jsonify({"error": "A JSON request body is required."}), 400

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("answers"), list):
            return jsonify({"error": "Request must contain an answers array."}), 400

        connection = connect_database(app.config["DATABASE_PATH"])
        try:
            rows = connection.execute(
                """
                SELECT id, category, question, option_a, option_b, option_c, option_d,
                    correct_answer, explanation
                FROM questions ORDER BY id
                """
            ).fetchall()
            questions_by_id = {row["id"]: row for row in rows}
            submitted_answers: dict[int, str | None] = {}

            for item in payload["answers"]:
                if not isinstance(item, dict):
                    return jsonify({"error": "Each answer must be an object."}), 400

                question_id = item.get("question_id")
                answer = item.get("answer")
                if type(question_id) is not int or question_id < 1:
                    return jsonify({"error": "Each question_id must be a positive integer."}), 400
                if question_id not in questions_by_id:
                    return jsonify({"error": f"Unknown question_id: {question_id}."}), 400
                if question_id in submitted_answers:
                    return jsonify({"error": f"Duplicate question_id: {question_id}."}), 400
                if answer is not None and (
                    not isinstance(answer, str) or answer not in ANSWER_LETTERS
                ):
                    return jsonify({"error": "Each answer must be A, B, C, D, or null."}), 400
                submitted_answers[question_id] = answer

            if set(submitted_answers) != set(questions_by_id):
                return jsonify({"error": "Submit one answer for every quiz question."}), 400

            total_questions = len(questions_by_id)
            correct_count = sum(
                submitted_answers[question_id] == row["correct_answer"]
                for question_id, row in questions_by_id.items()
            )
            unanswered_count = sum(answer is None for answer in submitted_answers.values())
            incorrect_count = total_questions - correct_count - unanswered_count
            score = correct_count
            percentage = round((score / total_questions) * 100, 2)
            attempted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            cursor = connection.execute(
                """
                INSERT INTO quiz_attempts (
                    score, total_questions, correct_answers, incorrect_answers,
                    unanswered_questions, percentage, attempted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    score,
                    total_questions,
                    correct_count,
                    incorrect_count,
                    unanswered_count,
                    percentage,
                    attempted_at,
                ),
            )
            attempt_id = cursor.lastrowid
            review_rows = []
            review_items = []
            for question_number, question in enumerate(questions_by_id.values(), start=1):
                selected_answer = submitted_answers[question["id"]]
                review_item = {
                    "question_number": question_number,
                    "question_id": question["id"],
                    "category": question["category"],
                    "question_text": question["question"],
                    "option_a": question["option_a"],
                    "option_b": question["option_b"],
                    "option_c": question["option_c"],
                    "option_d": question["option_d"],
                    "selected_answer": selected_answer,
                    "correct_answer": question["correct_answer"],
                    "explanation": question["explanation"] or "Explanation not available",
                }
                review_items.append(serialize_review_row(review_item))
                review_rows.append(
                    (
                        attempt_id,
                        question_number,
                        question["id"],
                        question["category"],
                        question["question"],
                        question["option_a"],
                        question["option_b"],
                        question["option_c"],
                        question["option_d"],
                        selected_answer,
                        question["correct_answer"],
                        question["explanation"] or "Explanation not available",
                    )
                )
            connection.executemany(
                """
                INSERT INTO quiz_attempt_reviews (
                    attempt_id, question_number, question_id, category, question_text,
                    option_a, option_b, option_c, option_d, selected_answer,
                    correct_answer, explanation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                review_rows,
            )
            connection.commit()
        except sqlite3.Error:
            connection.rollback()
            raise
        finally:
            connection.close()

        result = {
            "id": attempt_id,
            "score": score,
            "total_questions": total_questions,
            "correct_answers": correct_count,
            "incorrect_answers": incorrect_count,
            "unanswered_questions": unanswered_count,
            "percentage": percentage,
            "attempted_at": attempted_at,
                "review": review_items,
        }
        pass_mark = app.config["PASS_MARK_PERCENT"]
        if pass_mark is not None:
            result["pass_mark_percent"] = pass_mark
            result["passed"] = percentage >= pass_mark
        return jsonify(result), 201

    @app.get("/api/results")
    def get_results():
        connection = connect_database(app.config["DATABASE_PATH"])
        try:
            rows = connection.execute(
                """
                SELECT id, score, total_questions, correct_answers, incorrect_answers,
                    unanswered_questions, percentage, attempted_at,
                    EXISTS (
                        SELECT 1 FROM quiz_attempt_reviews
                        WHERE attempt_id = quiz_attempts.id
                    ) AS review_available
                FROM quiz_attempts ORDER BY id DESC
                """
            ).fetchall()
        finally:
            connection.close()
        return jsonify([dict(row) for row in rows])

    @app.get("/api/results/<int:attempt_id>")
    def get_attempt_review(attempt_id: int):
        connection = connect_database(app.config["DATABASE_PATH"])
        try:
            attempt = connection.execute(
                """
                SELECT id, score, total_questions, correct_answers, incorrect_answers,
                    unanswered_questions, percentage, attempted_at
                FROM quiz_attempts WHERE id = ?
                """,
                (attempt_id,),
            ).fetchone()
            if attempt is None:
                return jsonify({"error": "Quiz attempt not found."}), 404
            review_rows = connection.execute(
                """
                SELECT question_number, question_id, category, question_text,
                    option_a, option_b, option_c, option_d, selected_answer,
                    correct_answer, explanation
                FROM quiz_attempt_reviews WHERE attempt_id = ? ORDER BY question_number
                """,
                (attempt_id,),
            ).fetchall()
        finally:
            connection.close()

        if not review_rows:
            return jsonify({"error": "Detailed review is unavailable for this attempt."}), 404

        result = dict(attempt)
        result["review"] = [serialize_review_row(row) for row in review_rows]
        pass_mark = app.config["PASS_MARK_PERCENT"]
        if pass_mark is not None:
            result["pass_mark_percent"] = pass_mark
            result["passed"] = result["percentage"] >= pass_mark
        return jsonify(result)

    @app.errorhandler(sqlite3.Error)
    def database_error(error: sqlite3.Error):
        app.logger.exception("Database request failed", exc_info=error)
        return jsonify({"error": "The quiz database is temporarily unavailable."}), 500

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "The requested resource was not found."}), 404

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify({"error": "An unexpected server error occurred."}), 500

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
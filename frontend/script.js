let questions = [];

const welcomeScreen = document.querySelector('#welcome-screen');
const quizScreen = document.querySelector('#quiz-screen');
const resultsScreen = document.querySelector('#results-screen');
const startButton = document.querySelector('#start-button');
const backButton = document.querySelector('#back-button');
const nextButton = document.querySelector('#next-button');
const skipButton = document.querySelector('#skip-button');
const restartButton = document.querySelector('#restart-button');
const reviewAnswersButton = document.querySelector('#review-answers-button');
const resultsHomeButton = document.querySelector('#results-home-button');
const reviewBackButton = document.querySelector('#review-back-button');
const reviewHomeButton = document.querySelector('#review-home-button');
const apiError = document.querySelector('#api-error');
const serverStatus = document.querySelector('#server-status');
const serverStatusText = document.querySelector('#server-status-text');
const questionCounter = document.querySelector('#question-counter');
const progressPercent = document.querySelector('#progress-percent');
const progressTrack = document.querySelector('#progress-track');
const progressFill = document.querySelector('#progress-fill');
const scoreValue = document.querySelector('#score-value');
const questionTopic = document.querySelector('#question-topic');
const questionTitle = document.querySelector('#question-title');
const answerList = document.querySelector('#answer-list');
const feedback = document.querySelector('#feedback');
const finalScore = document.querySelector('#final-score');
const finalPercent = document.querySelector('#final-percent');
const resultMessage = document.querySelector('#result-message');
const resultTotal = document.querySelector('#result-total');
const resultCorrect = document.querySelector('#result-correct');
const resultIncorrect = document.querySelector('#result-incorrect');
const resultUnanswered = document.querySelector('#result-unanswered');
const passStatus = document.querySelector('#pass-status');
const historyCount = document.querySelector('#history-count');
const historyList = document.querySelector('#history-list');
const reviewScreen = document.querySelector('#review-screen');
const reviewSummary = document.querySelector('#review-summary');
const reviewList = document.querySelector('#review-list');

let currentQuestionIndex = 0;
let score = null;
let hasAnswered = false;
let selectedAnswer = null;
let submittedAnswers = [];
let exitNavigationPending = false;
let isSubmitting = false;
let latestReview = [];

history.replaceState({ smartQuizApp: true, screen: 'welcome' }, '', `${window.location.pathname}${window.location.search}`);

async function requestJson(url, options = {}) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (_error) {
    throw new Error('Could not reach the quiz server. Make sure Flask is running and open this app through its server URL.');
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.error || `The quiz server returned an error (${response.status}).`);
  }
  return payload;
}

function showApiError(message) {
  apiError.textContent = message;
  apiError.hidden = false;
}

function clearApiError() {
  apiError.textContent = '';
  apiError.hidden = true;
}

async function loadAttemptHistory() {
  const attempts = await requestJson('/api/results');
  if (!Array.isArray(attempts)) throw new Error('The quiz server returned invalid attempt history.');

  historyCount.textContent = attempts.length ? `${attempts.length} saved` : '';
  historyList.replaceChildren();
  if (attempts.length === 0) {
    const emptyMessage = document.createElement('p');
    emptyMessage.className = 'history-empty';
    emptyMessage.textContent = 'No attempts yet. Your results will appear here.';
    historyList.append(emptyMessage);
    return;
  }

  attempts.forEach((attempt) => {
    const row = document.createElement('div');
    const date = document.createElement('time');
    const result = document.createElement('span');
    const percentage = document.createElement('span');
    const reviewButton = document.createElement('button');
    const attemptedAt = new Date(attempt.attempted_at);

    row.className = 'attempt-row';
    date.className = 'attempt-date';
    date.dateTime = attempt.attempted_at;
    date.textContent = Number.isNaN(attemptedAt.getTime())
      ? attempt.attempted_at
      : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(attemptedAt);
    result.className = 'attempt-score';
    result.textContent = `${attempt.score}/${attempt.total_questions} correct`;
    percentage.className = 'attempt-percent';
    percentage.textContent = `${Math.round(attempt.percentage)}%`;
    reviewButton.className = 'review-attempt-button';
    reviewButton.type = 'button';
    reviewButton.textContent = attempt.review_available ? 'Review' : 'Review unavailable';
    reviewButton.disabled = !attempt.review_available;
    if (attempt.review_available) {
      reviewButton.addEventListener('click', () => { void openAttemptReview(attempt.id); });
    } else {
      reviewButton.title = 'This attempt was saved before detailed reviews were available.';
    }
    row.append(date, result, percentage, reviewButton);
    historyList.append(row);
  });
}

function setResultSummary(result) {
  resultTotal.textContent = String(result.total_questions);
  resultCorrect.textContent = String(result.correct_answers);
  resultIncorrect.textContent = String(result.incorrect_answers);
  resultUnanswered.textContent = String(result.unanswered_questions);
  finalScore.textContent = `${result.score}/${result.total_questions}`;
  finalPercent.textContent = `${Math.round(result.percentage)}%`;

  if (typeof result.pass_mark_percent === 'number' && typeof result.passed === 'boolean') {
    passStatus.textContent = result.passed
      ? `Pass · ${result.pass_mark_percent}% required`
      : `Fail · ${result.pass_mark_percent}% required`;
    passStatus.classList.toggle('is-fail', !result.passed);
    passStatus.hidden = false;
  } else {
    passStatus.hidden = true;
    passStatus.classList.remove('is-fail');
    passStatus.textContent = '';
  }

  if (result.percentage === 100) {
    resultMessage.textContent = 'A perfect score. You really know your way around these topics.';
  } else if (result.percentage >= 70) {
    resultMessage.textContent = 'A strong showing. Your curiosity is clearly paying off.';
  } else if (result.percentage >= 40) {
    resultMessage.textContent = 'Good work. Every question is another thing you know now.';
  } else {
    resultMessage.textContent = 'A solid start. There\'s always something new to learn.';
  }
}

function renderReview(review) {
  latestReview = review;
  reviewSummary.textContent = `${review.length} questions · ${resultCorrect.textContent} correct · ${resultIncorrect.textContent} incorrect · ${resultUnanswered.textContent} unanswered`;
  reviewList.replaceChildren();

  review.forEach((item) => {
    const card = document.createElement('article');
    const heading = document.createElement('div');
    const headingCopy = document.createElement('div');
    const number = document.createElement('p');
    const question = document.createElement('h2');
    const status = document.createElement('span');
    const options = document.createElement('div');
    const selection = document.createElement('p');
    const explanation = document.createElement('p');
    const statusClass = item.status.toLowerCase();

    card.className = `review-card is-${statusClass}`;
    heading.className = 'review-card-heading';
    number.className = 'review-question-number';
    number.textContent = `Question ${item.question_number} · ${item.category}`;
    question.className = 'review-question';
    question.textContent = item.question;
    headingCopy.append(number, question);
    status.className = `review-status is-${statusClass}`;
    status.textContent = item.status;
    heading.append(headingCopy, status);
    options.className = 'review-options';

    Object.entries(item.options).forEach(([letter, optionText]) => {
      const option = document.createElement('div');
      const label = document.createElement('span');
      const text = document.createElement('span');
      const notes = document.createElement('span');
      const noteLabels = [];

      option.className = 'review-option';
      if (letter === item.correct_answer) {
        option.classList.add('is-correct');
        noteLabels.push('Correct answer');
      }
      if (letter === item.selected_answer) {
        noteLabels.push('Your answer');
        if (letter !== item.correct_answer) option.classList.add('is-wrong');
      }
      label.className = 'review-option-label';
      label.textContent = letter;
      text.textContent = optionText;
      notes.className = 'review-option-note';
      notes.textContent = noteLabels.join(' · ');
      option.append(label, text, notes);
      options.append(option);
    });

    selection.className = 'review-selection';
    selection.textContent = item.selected_answer
      ? `Your answer: ${item.selected_answer} · ${item.selected_option}`
      : 'Your answer: Not Answered';
    explanation.className = 'review-explanation';
    const explanationLabel = document.createElement('strong');
    explanationLabel.textContent = 'Why this is correct: ';
    explanation.append(
      explanationLabel,
      document.createTextNode(item.explanation || 'Explanation not available')
    );

    card.append(heading, options, selection, explanation);
    reviewList.append(card);
  });
}

async function openAttemptReview(attemptId) {
  clearApiError();
  try {
    const result = await requestJson(`/api/results/${encodeURIComponent(attemptId)}`);
    setResultSummary(result);
    renderReview(result.review);
    showScreen(reviewScreen);
    document.querySelector('#review-title').focus();
  } catch (error) {
    showApiError(error.message);
  }
}

async function initializeHome() {
  try {
    await requestJson('/api/health');
    serverStatus.classList.remove('is-offline');
    serverStatus.classList.add('is-online');
    serverStatusText.textContent = 'Quiz service connected';
    clearApiError();
  } catch (error) {
    serverStatus.classList.remove('is-online');
    serverStatus.classList.add('is-offline');
    serverStatusText.textContent = 'Quiz service unavailable';
    showApiError(error.message);
  }

  try {
    await loadAttemptHistory();
  } catch (error) {
    historyList.textContent = 'Attempt history could not be loaded.';
    showApiError(error.message);
  }
}

function showScreen(screenToShow) {
  welcomeScreen.hidden = screenToShow !== welcomeScreen;
  quizScreen.hidden = screenToShow !== quizScreen;
  resultsScreen.hidden = screenToShow !== resultsScreen;
  reviewScreen.hidden = screenToShow !== reviewScreen;
}

function renderQuestion() {
  const question = questions[currentQuestionIndex];
  const questionNumber = currentQuestionIndex + 1;
  const progress = Math.round((questionNumber / questions.length) * 100);

  hasAnswered = false;
  questionCounter.textContent = `Question ${questionNumber} of ${questions.length}`;
  progressPercent.textContent = `${progress}%`;
  progressTrack.setAttribute('aria-valuenow', String(questionNumber));
  progressTrack.setAttribute('aria-valuetext', `Question ${questionNumber} of ${questions.length}`);
  progressFill.style.width = `${progress}%`;
  scoreValue.textContent = score === null ? '--' : String(score);
  questionTopic.textContent = question.category;
  questionTitle.textContent = question.question;
  feedback.hidden = true;
  feedback.removeAttribute('data-correct');
  nextButton.disabled = true;
  nextButton.innerHTML = currentQuestionIndex === questions.length - 1
    ? 'Finish Quiz <span class="button-arrow" aria-hidden="true">&#8594;</span>'
    : 'Next Question <span class="button-arrow" aria-hidden="true">&#8594;</span>';
  skipButton.hidden = hasAnswered;
  skipButton.disabled = false;

  answerList.replaceChildren(...Object.entries(question.options).map(([letter, option]) => {
    const button = document.createElement('button');
    const label = document.createElement('span');
    const text = document.createElement('span');

    button.className = 'answer-option';
    button.type = 'button';
    label.className = 'answer-letter';
    label.setAttribute('aria-hidden', 'true');
    label.textContent = letter;
    text.className = 'answer-text';
    text.textContent = option;
    button.append(label, text);
    button.addEventListener('click', () => chooseAnswer(letter));
    return button;
  }));
}

function chooseAnswer(answer) {
  if (hasAnswered) return;

  hasAnswered = true;
  selectedAnswer = answer;
  const question = questions[currentQuestionIndex];
  submittedAnswers[currentQuestionIndex].answer = answer;
  const answerButtons = answerList.querySelectorAll('.answer-option');

  answerButtons.forEach((button) => {
    button.disabled = true;
  });

  skipButton.hidden = true;
  feedback.replaceChildren();
  const mark = document.createElement('span');
  const message = document.createElement('span');
  mark.className = 'feedback-mark';
  mark.textContent = 'Answer saved.';
  message.textContent = 'Your score is calculated securely when you view your results.';
  feedback.append(mark, message);
  feedback.hidden = false;
  nextButton.disabled = false;
}

async function showResults() {
  if (isSubmitting || submittedAnswers.length !== questions.length) return;

  isSubmitting = true;
  nextButton.disabled = true;
  skipButton.disabled = true;
  nextButton.textContent = 'Submitting...';
  clearApiError();

  try {
    const result = await requestJson('/api/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers: submittedAnswers })
    });
    score = result.score;
    scoreValue.textContent = String(score);
    setResultSummary(result);
    renderReview(result.review);
    showScreen(resultsScreen);
    document.querySelector('#results-title').focus();
    loadAttemptHistory().catch((error) => showApiError(error.message));
  } catch (error) {
    showApiError(error.message);
    nextButton.disabled = false;
    nextButton.innerHTML = currentQuestionIndex === questions.length - 1
      ? 'Finish Quiz <span class="button-arrow" aria-hidden="true">&#8594;</span>'
      : 'Next Question <span class="button-arrow" aria-hidden="true">&#8594;</span>';
    skipButton.disabled = false;
  } finally {
    isSubmitting = false;
  }
}

async function startQuiz(addHistoryEntry = true) {
  startButton.disabled = true;
  clearApiError();

  try {
    if (questions.length === 0) {
      const response = await requestJson('/api/questions');
      if (!Array.isArray(response) || response.length === 0) {
        throw new Error('The quiz server did not return any questions.');
      }
      questions = response;
    }

    if (addHistoryEntry && history.state?.screen !== 'quiz') {
      history.pushState({ smartQuizApp: true, screen: 'quiz' }, '', `${window.location.pathname}${window.location.search}#quiz`);
    }

    exitNavigationPending = false;
    currentQuestionIndex = 0;
    score = null;
    selectedAnswer = null;
    submittedAnswers = questions.map((question) => ({ question_id: question.id, answer: null }));
    latestReview = [];
    showScreen(quizScreen);
    renderQuestion();
    questionTitle.focus();
  } catch (error) {
    showApiError(error.message);
  } finally {
    startButton.disabled = false;
  }
}

function hasQuizProgress() {
  return currentQuestionIndex > 0 || submittedAnswers.some((item) => item.answer !== null);
}

function returnToWelcome() {
  currentQuestionIndex = 0;
  score = null;
  hasAnswered = false;
  selectedAnswer = null;
  submittedAnswers = [];
  exitNavigationPending = false;
  scoreValue.textContent = '--';
  showScreen(welcomeScreen);
  void loadAttemptHistory().catch((error) => showApiError(error.message));
  startButton.focus();
}

function goHomeAfterResults() {
  if (history.state?.screen === 'quiz') {
    history.back();
  } else {
    returnToWelcome();
  }
}

function showPreviousResults() {
  showScreen(resultsScreen);
  document.querySelector('#results-title').focus();
}

function goBackToHome() {
  if (exitNavigationPending) return;
  if (hasQuizProgress() && !window.confirm('Exit quiz? Your current progress will be lost.')) return;

  exitNavigationPending = true;
  history.back();
}

startButton.addEventListener('click', () => { void startQuiz(); });
backButton.addEventListener('click', goBackToHome);
skipButton.addEventListener('click', () => {
  if (isSubmitting) return;
  if (currentQuestionIndex === questions.length - 1) {
    void showResults();
    return;
  }

  currentQuestionIndex += 1;
  renderQuestion();
  questionTitle.focus();
});
reviewAnswersButton.addEventListener('click', () => {
  renderReview(latestReview);
  showScreen(reviewScreen);
  document.querySelector('#review-title').focus();
});
resultsHomeButton.addEventListener('click', goHomeAfterResults);
reviewBackButton.addEventListener('click', showPreviousResults);
reviewHomeButton.addEventListener('click', goHomeAfterResults);
nextButton.addEventListener('click', () => {
  if (!hasAnswered || isSubmitting) return;
  if (currentQuestionIndex === questions.length - 1) {
    void showResults();
    return;
  }

  currentQuestionIndex += 1;
  renderQuestion();
  questionTitle.focus();
});
restartButton.addEventListener('click', () => { void startQuiz(); });

window.addEventListener('popstate', (event) => {
  if (event.state?.smartQuizApp && event.state.screen === 'quiz') {
    void startQuiz(false);
    return;
  }

  if (quizScreen.hidden) {
    if (welcomeScreen.hidden) returnToWelcome();
    return;
  }
  if (exitNavigationPending) {
    returnToWelcome();
    return;
  }

  if (hasQuizProgress() && !window.confirm('Exit quiz? Your current progress will be lost.')) {
    history.pushState({ smartQuizApp: true, screen: 'quiz' }, '', `${window.location.pathname}${window.location.search}#quiz`);
    return;
  }

  returnToWelcome();
});

void initializeHome();
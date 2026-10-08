import 'account.dart' show Json;

enum HomeworkStatus { preparing, ready, solved, guided, failed }

HomeworkStatus _status(Object? value) =>
    HomeworkStatus.values.asNameMap()[value] ?? HomeworkStatus.failed;

/// Une étape du guidage : « 🔎 Qu'est-ce qu'on cherche ? », « 💡 Un indice »…
class HomeworkStep {
  const HomeworkStep({required this.kind, required this.title, required this.text});

  factory HomeworkStep.fromJson(Json json) => HomeworkStep(
    kind: json['kind'] as String,
    title: json['title'] as String,
    text: json['text'] as String,
  );

  final String kind;
  final String title;
  final String text;
}

class HomeworkAttempt {
  const HomeworkAttempt({required this.text, this.correct});

  factory HomeworkAttempt.fromJson(Json json) =>
      HomeworkAttempt(text: json['text'] as String, correct: json['correct'] as bool?);

  final String text;

  /// `null` : réponse rédigée, l'enfant compare avec la correction.
  final bool? correct;
}

/// Mode devoirs : un exercice de l'enfant, guidé pas à pas (§29, §127).
class Homework {
  const Homework({
    required this.id,
    required this.status,
    required this.steps,
    required this.stepsLeft,
    required this.attempts,
    required this.solutionAvailable,
    this.statement,
    this.answerKind,
    this.solution,
    this.answer,
    this.check,
    this.failureMessage,
  });

  factory Homework.fromJson(Json json) => Homework(
    id: json['id'] as String,
    status: _status(json['status']),
    statement: json['statement'] as String?,
    answerKind: json['answer_kind'] as String?,
    steps: [for (final s in json['steps'] as List<dynamic>) HomeworkStep.fromJson(s as Json)],
    stepsLeft: json['steps_left'] as int? ?? 0,
    attempts: [
      for (final a in json['attempts'] as List<dynamic>) HomeworkAttempt.fromJson(a as Json),
    ],
    solutionAvailable: json['solution_available'] as bool? ?? false,
    solution: (json['solution'] as List<dynamic>?)?.cast<String>(),
    answer: json['answer'] as String?,
    check: json['check'] as String?,
    failureMessage: json['failure_message'] as String?,
  );

  final String id;
  final HomeworkStatus status;
  final String? statement;

  /// `number`, `short` ou `open` (phrase à rédiger).
  final String? answerKind;
  final List<HomeworkStep> steps;
  final int stepsLeft;
  final List<HomeworkAttempt> attempts;
  final bool solutionAvailable;
  final List<String>? solution;
  final String? answer;
  final String? check;
  final String? failureMessage;

  bool get finished => status == HomeworkStatus.solved || status == HomeworkStatus.guided;
  bool get open => answerKind == 'open';
}

/// Pour le parent : l'exercice, l'aide utilisée, la suite.
class HomeworkSummary {
  const HomeworkSummary({
    required this.id,
    required this.createdAt,
    required this.status,
    required this.stepsUsed,
    required this.stepsTotal,
    required this.attempts,
    required this.solvedAlone,
    this.statement,
  });

  factory HomeworkSummary.fromJson(Json json) => HomeworkSummary(
    id: json['id'] as String,
    createdAt: DateTime.parse(json['created_at'] as String),
    status: _status(json['status']),
    statement: json['statement'] as String?,
    stepsUsed: json['steps_used'] as int,
    stepsTotal: json['steps_total'] as int,
    attempts: json['attempts'] as int,
    solvedAlone: json['solved_alone'] as bool,
  );

  final String id;
  final DateTime createdAt;
  final HomeworkStatus status;
  final String? statement;
  final int stepsUsed;
  final int stepsTotal;
  final int attempts;
  final bool solvedAlone;
}

class HomeworkPage {
  const HomeworkPage({required this.homework, this.nextBefore});

  factory HomeworkPage.fromJson(Json json) => HomeworkPage(
    homework: [
      for (final h in json['homework'] as List<dynamic>) HomeworkSummary.fromJson(h as Json),
    ],
    nextBefore: json['next_before'] as String?,
  );

  final List<HomeworkSummary> homework;
  final String? nextBefore;
}

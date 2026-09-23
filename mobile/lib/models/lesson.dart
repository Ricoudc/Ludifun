import 'account.dart';

/// Formats de l'API des leçons, de la mission du jour et des séances (§11).

enum LessonStatus {
  uploaded,
  reading,
  analyzing,
  generating,
  ready,
  failed;

  static LessonStatus parse(String value) =>
      values.firstWhere((s) => s.name == value, orElse: () => LessonStatus.uploaded);

  bool get inProgress => this != ready && this != failed;
}

/// Étapes de l'analyse suivies par l'écran 3, dans l'ordre.
const analysisSteps = ['reading', 'analyzing', 'generating'];

enum AnalysisStep { pending, running, done }

class LessonSummary {
  const LessonSummary({
    required this.id,
    required this.status,
    required this.createdAt,
    this.failureReason,
    this.subject,
    this.title,
    this.nextReviewAt,
    this.due = false,
    this.mastered = false,
  });

  factory LessonSummary.fromJson(Json json) => LessonSummary(
    id: json['id'] as String,
    status: LessonStatus.parse(json['status'] as String),
    failureReason: json['failure_reason'] as String?,
    subject: json['subject'] as String?,
    title: json['title'] as String?,
    createdAt: DateTime.parse(json['created_at'] as String),
    nextReviewAt: switch (json['next_review_at']) {
      final String at => DateTime.parse(at),
      _ => null,
    },
    due: json['due'] as bool? ?? false,
    mastered: json['mastered'] as bool? ?? false,
  );

  final String id;
  final LessonStatus status;
  final String? failureReason;
  final String? subject;
  final String? title;
  final DateTime createdAt;
  final DateTime? nextReviewAt;
  final bool due;
  final bool mastered;
}

class Knowledge {
  const Knowledge({
    required this.id,
    required this.label,
    required this.statement,
    required this.importance,
  });

  factory Knowledge.fromJson(Json json) => Knowledge(
    id: json['id'] as String,
    label: json['label'] as String,
    statement: json['statement'] as String,
    importance: json['importance'] as int,
  );

  final String id;
  final String label;
  final String statement;
  final int importance;
}

class Lesson extends LessonSummary {
  const Lesson({
    required super.id,
    required super.status,
    required super.createdAt,
    super.failureReason,
    super.subject,
    super.title,
    super.nextReviewAt,
    super.due,
    super.mastered,
    this.steps = const {},
    this.failureMessage,
    this.grade,
    this.objective,
    this.summary,
    this.knowledge = const [],
    this.canRetry = false,
  });

  factory Lesson.fromJson(Json json) {
    final base = LessonSummary.fromJson(json);
    final steps = json['steps'] as Map<String, dynamic>?;
    return Lesson(
      id: base.id,
      status: base.status,
      createdAt: base.createdAt,
      failureReason: base.failureReason,
      subject: base.subject,
      title: base.title,
      nextReviewAt: base.nextReviewAt,
      due: base.due,
      mastered: base.mastered,
      steps: {
        for (final MapEntry(:key, :value) in (steps ?? const {}).entries)
          key: AnalysisStep.values.byName(value as String),
      },
      failureMessage: json['failure_message'] as String?,
      grade: json['grade'] as String?,
      objective: json['objective'] as String?,
      summary: json['summary'] as String?,
      knowledge: [
        for (final k in json['knowledge'] as List<dynamic>? ?? const [])
          Knowledge.fromJson(k as Json),
      ],
      canRetry: json['can_retry'] as bool? ?? false,
    );
  }

  final Map<String, AnalysisStep> steps;
  final String? failureMessage;
  final String? grade;
  final String? objective;
  final String? summary;
  final List<Knowledge> knowledge;
  final bool canRetry;

  /// Étapes terminées côté serveur (0 à 3).
  int get stepsDone => status == LessonStatus.ready
      ? analysisSteps.length
      : analysisSteps.where((s) => steps[s] == AnalysisStep.done).length;
}

class Mission {
  const Mission({this.lessonId, this.title, this.subject, this.reason, this.estimatedMinutes});

  factory Mission.fromJson(Json json) {
    final lesson = json['lesson'] as Json?;
    return Mission(
      lessonId: lesson?['id'] as String?,
      title: lesson?['title'] as String?,
      subject: lesson?['subject'] as String?,
      reason: json['reason'] as String?,
      estimatedMinutes: json['estimated_minutes'] as int?,
    );
  }

  /// `null` : tout est à jour.
  final String? lessonId;
  final String? title;
  final String? subject;
  final String? reason;
  final int? estimatedMinutes;
}

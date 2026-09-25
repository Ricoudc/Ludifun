import 'account.dart';
import 'level.dart';

/// Formats de l'API des leçons, de la mission du jour et des séances (§11).

enum LessonStatus {
  uploaded,
  reading,

  /// « Peux-tu vérifier ? » : l'analyse attend que l'enfant relise des mots mal lus.
  needsReview,
  analyzing,
  generating,
  ready,
  failed;

  static LessonStatus parse(String value) => value == 'needs_review'
      ? needsReview
      : values.firstWhere((s) => s.name == value, orElse: () => LessonStatus.uploaded);

  /// L'analyse avance sans l'enfant (l'accueil l'attend).
  bool get inProgress => this != ready && this != failed && this != needsReview;
}

/// Un passage que la lecture de la photo n'est pas sûre d'avoir bien lu.
class ReviewItem {
  const ReviewItem({required this.id, required this.readText, required this.context});

  factory ReviewItem.fromJson(Json json) => ReviewItem(
    id: json['id'] as String,
    readText: json['read_text'] as String,
    context: json['context'] as String,
  );

  final String id;

  /// Ce qui a été lu, ou « [illisible] ».
  final String readText;

  /// Les mots autour, pour le retrouver sur le cahier.
  final String context;

  bool get unreadable => readText == '[illisible]';
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
    this.level = 0,
    this.sourceExcerpt,
    this.sourcePage,
  });

  factory Knowledge.fromJson(Json json) => Knowledge(
    id: json['id'] as String,
    label: json['label'] as String,
    statement: json['statement'] as String,
    importance: json['importance'] as int,
    level: json['level'] as int? ?? 0,
    sourceExcerpt: json['source_excerpt'] as String?,
    sourcePage: json['source_page'] as int?,
  );

  final String id;
  final String label;
  final String statement;
  final int importance;

  /// Niveau de maîtrise de l'enfant, 0 à 5.
  final int level;

  /// « Pourquoi cette notion ? » : la phrase de la leçon d'où elle vient, et sa page.
  final String? sourceExcerpt;
  final int? sourcePage;
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
    this.skills = const [],
    this.review = const [],
    this.canRetry = false,
    this.diagnostics,
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
      skills: [
        for (final s in json['skills'] as List<dynamic>? ?? const []) Skill.fromJson(s as Json),
      ],
      review: [
        for (final r in json['review'] as List<dynamic>? ?? const [])
          ReviewItem.fromJson(r as Json),
      ],
      canRetry: json['can_retry'] as bool? ?? false,
      diagnostics: switch (json['diagnostics']) {
        final Json d => Diagnostics.fromJson(d),
        _ => null,
      },
    );
  }

  final Map<String, AnalysisStep> steps;
  final String? failureMessage;
  final String? grade;
  final String? objective;
  final String? summary;
  final List<Knowledge> knowledge;

  /// Vide pour une leçon analysée avant les compétences.
  final List<Skill> skills;

  /// Passages à vérifier (statut « à vérifier »).
  final List<ReviewItem> review;
  final bool canRetry;

  /// « Voir ce qui se passe » : l'IA étape par étape, et la raison d'un échec.
  final Diagnostics? diagnostics;

  /// Étapes terminées côté serveur (0 à 3).
  int get stepsDone => status == LessonStatus.ready
      ? analysisSteps.length
      : analysisSteps.where((s) => steps[s] == AnalysisStep.done).length;
}

class Mission {
  const Mission({
    this.lessonId,
    this.title,
    this.subject,
    this.reason,
    this.estimatedMinutes,
    this.examTitle,
    this.examDate,
    this.focusLabel,
    this.dailyMinutes,
  });

  factory Mission.fromJson(Json json) {
    final lesson = json['lesson'] as Json?;
    final exam = json['exam'] as Json?;
    return Mission(
      lessonId: lesson?['id'] as String?,
      title: lesson?['title'] as String?,
      subject: lesson?['subject'] as String?,
      reason: json['reason'] as String?,
      estimatedMinutes: json['estimated_minutes'] as int?,
      examTitle: exam?['title'] as String?,
      examDate: switch (exam?['exam_date']) {
        final String day => DateTime.parse(day),
        _ => null,
      },
      focusLabel: exam?['focus_label'] as String?,
      dailyMinutes: json['daily_minutes'] as int?,
    );
  }

  /// Étape du jour d'un plan avant un contrôle.
  final String? examTitle;
  final DateTime? examDate;
  final String? focusLabel;

  /// Temps de révision par jour choisi par le parent.
  final int? dailyMinutes;

  /// `null` : tout est à jour.
  final String? lessonId;
  final String? title;
  final String? subject;
  final String? reason;
  final int? estimatedMinutes;
}

/// Une étape de l'IA pendant l'analyse (`running` : en cours depuis [seconds]).
class AiStep {
  const AiStep({
    required this.stage,
    required this.model,
    required this.seconds,
    required this.status,
    this.message,
  });

  factory AiStep.fromJson(Json json) => AiStep(
    stage: json['stage'] as String,
    model: json['model'] as String,
    seconds: json['seconds'] as int,
    status: json['status'] as String,
    message: json['message'] as String?,
  );

  final String stage;
  final String model;
  final int seconds;
  final String status;
  final String? message;

  bool get running => status == 'running';
  bool get ok => status == 'ok';
}

class Diagnostics {
  const Diagnostics({required this.steps, this.explanation});

  factory Diagnostics.fromJson(Json json) => Diagnostics(
    steps: [for (final s in json['steps'] as List<dynamic>) AiStep.fromJson(s as Json)],
    explanation: json['explanation'] as String?,
  );

  final List<AiStep> steps;

  /// Raison de l'échec, en clair.
  final String? explanation;
}

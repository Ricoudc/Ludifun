import 'account.dart';

/// Formats de l'API des séances (§7.3 et §11) : écrans 4 à 7.

enum Block { warmup, core, match, speed, replay }

enum AttemptResult {
  correct,
  partial,
  incorrect,
  skipped;

  static AttemptResult parse(String value) => values.byName(value);
}

class SessionItem {
  const SessionItem({
    required this.id,
    required this.position,
    required this.block,
    required this.type,
    required this.difficulty,
    required this.payload,
    this.result,
  });

  factory SessionItem.fromJson(Json json) => SessionItem(
    id: json['id'] as String,
    position: json['position'] as int,
    block: Block.values.byName(json['block'] as String),
    type: json['type'] as String,
    difficulty: json['difficulty'] as int? ?? 1,
    payload: json['payload'] as Json,
    result: switch (json['attempt']) {
      {'result': final String result} => AttemptResult.parse(result),
      _ => null,
    },
  );

  final String id;
  final int position;
  final Block block;
  final String type;
  final int difficulty;

  /// Données publiques de l'activité ; la solution reste sur le serveur.
  final Json payload;

  /// Déjà répondu (reprise d'une séance).
  final AttemptResult? result;

  bool get answered => result != null;

  SessionItem answeredWith(AttemptResult value) => SessionItem(
    id: id,
    position: position,
    block: block,
    type: type,
    difficulty: difficulty,
    payload: payload,
    result: value,
  );
}

class RevisionSession {
  const RevisionSession({
    required this.id,
    required this.lessonId,
    required this.kind,
    required this.status,
    required this.objective,
    required this.estimatedMinutes,
    required this.express,
    required this.items,
    this.scoreOn10,
  });

  factory RevisionSession.fromJson(Json json) => RevisionSession(
    id: json['id'] as String,
    lessonId: json['lesson_id'] as String,
    kind: json['kind'] as String,
    status: json['status'] as String,
    objective: json['objective'] as String,
    estimatedMinutes: json['estimated_duration_min'] as int,
    express: json['express'] as bool? ?? false,
    items: [for (final item in json['items'] as List<dynamic>) SessionItem.fromJson(item as Json)],
    scoreOn10: (json['score_on_10'] as num?)?.toDouble(),
  );

  final String id;
  final String lessonId;

  /// `first`, `review` ou `errors`.
  final String kind;

  /// `active`, `completed` ou `abandoned`.
  final String status;
  final String objective;
  final int estimatedMinutes;
  final bool express;
  final List<SessionItem> items;
  final double? scoreOn10;
}

/// Correction immédiate (écran 6).
class Correction {
  const Correction({
    required this.result,
    required this.score,
    this.correctAnswer,
    this.tip,
    this.explanation,
    this.details = const [],
  });

  factory Correction.fromJson(Json json) => Correction(
    result: AttemptResult.parse(json['result'] as String),
    score: (json['score'] as num).toDouble(),
    correctAnswer: json['correct_answer'] as String?,
    tip: json['tip'] as String?,
    explanation: json['explanation'] as String?,
    details: [for (final d in json['details'] as List<dynamic>? ?? const []) d as Json],
  );

  final AttemptResult result;
  final double score;
  final String? correctAnswer;
  final String? tip;
  final String? explanation;

  /// Association et défi rapide : `[{id, correct, expected, correction?}]`.
  final List<Json> details;
}

enum KnowledgeStatus { mastered, toReview, notMastered }

class KnowledgeResult {
  const KnowledgeResult({required this.label, required this.status, required this.mastery});

  factory KnowledgeResult.fromJson(Json json) => KnowledgeResult(
    label: json['label'] as String,
    status: switch (json['status']) {
      'mastered' => KnowledgeStatus.mastered,
      'to_review' => KnowledgeStatus.toReview,
      _ => KnowledgeStatus.notMastered,
    },
    mastery: json['mastery'] as int,
  );

  final String label;
  final KnowledgeStatus status;
  final int mastery;
}

/// Bilan (écran 7).
class Report {
  const Report({
    required this.scoreOn10,
    required this.knowledge,
    required this.lessonMastered,
    required this.canReviewErrors,
    this.nextReviewAt,
  });

  factory Report.fromJson(Json json) => Report(
    scoreOn10: (json['score_on_10'] as num).toDouble(),
    knowledge: [
      for (final k in json['knowledge'] as List<dynamic>) KnowledgeResult.fromJson(k as Json),
    ],
    nextReviewAt: switch (json['next_review_at']) {
      final String at => DateTime.parse(at),
      _ => null,
    },
    lessonMastered: json['lesson_mastered'] as bool? ?? false,
    canReviewErrors: json['can_review_errors'] as bool? ?? false,
  );

  final double scoreOn10;
  final List<KnowledgeResult> knowledge;
  final DateTime? nextReviewAt;
  final bool lessonMastered;
  final bool canReviewErrors;

  List<KnowledgeResult> withStatus(KnowledgeStatus status) => [
    for (final k in knowledge)
      if (k.status == status) k,
  ];
}

import 'account.dart';
import 'rewards.dart';

/// Formats de l'API des séances (§7.3 et §11) : écrans 4 à 7.

enum Block {
  warmup,
  core,
  match,
  speed,
  replay,

  /// Insérée après deux échecs sur une notion (rappel, puis activités faciles).
  remediation,

  /// Défis en plus, proposés à un enfant rapide.
  bonus;

  /// Un bloc inconnu (serveur plus récent) se joue comme une activité ordinaire.
  static Block parse(String value) => values.asNameMap()[value] ?? core;
}

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
    this.helpAvailable = false,
    this.intro,
    this.instruction,
    this.daily,
  });

  factory SessionItem.fromJson(Json json) => SessionItem(
    helpAvailable: json['help_available'] as bool? ?? false,
    id: json['id'] as String,
    position: json['position'] as int,
    block: Block.parse(json['block'] as String),
    intro: json['intro'] as String?,
    instruction: json['instruction'] as String?,
    daily: json['daily'] as String?,
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

  /// Bouton « Je n'ai pas compris » proposé (activités sur une seule notion).
  final bool helpAvailable;

  /// Rappel de la règle, affiché avant l'activité (remédiation).
  final String? intro;

  /// Comment jouer, au niveau de la classe de l'enfant (étape 25) ; null avec un serveur ancien.
  final String? instruction;

  /// Nom du jeu du jour si c'est lui (§5.54) : étoiles doublées.
  final String? daily;

  bool get answered => result != null;

  SessionItem answeredWith(AttemptResult value) => SessionItem(
    id: id,
    position: position,
    block: block,
    type: type,
    difficulty: difficulty,
    payload: payload,
    result: value,
    helpAvailable: helpAvailable,
    intro: intro,
    instruction: instruction,
    daily: daily,
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
    this.insertedItems = const [],
    this.pauseMessage,
  });

  factory Correction.fromJson(Json json) => Correction(
    insertedItems: [
      for (final i in json['inserted_items'] as List<dynamic>? ?? const [])
        SessionItem.fromJson(i as Json),
    ],
    pauseMessage: (json['engagement_hint'] as Json?)?['message'] as String?,
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

  /// Remédiation : activités à jouer juste après celle-ci.
  final List<SessionItem> insertedItems;

  /// Proposition de pause (réponses au hasard, ou trop d'échecs d'affilée).
  final String? pauseMessage;
}

enum KnowledgeStatus { mastered, toReview, notMastered }

class KnowledgeResult {
  const KnowledgeResult({
    required this.label,
    required this.status,
    required this.mastery,
    this.level = 0,
    this.previousLevel = 0,
    this.explanation,
  });

  factory KnowledgeResult.fromJson(Json json) => KnowledgeResult(
    label: json['label'] as String,
    status: switch (json['status']) {
      'mastered' => KnowledgeStatus.mastered,
      'to_review' => KnowledgeStatus.toReview,
      _ => KnowledgeStatus.notMastered,
    },
    mastery: json['mastery'] as int,
    level: json['level'] as int? ?? 0,
    previousLevel: json['previous_level'] as int? ?? 0,
    explanation: json['explanation'] as String?,
  );

  final String label;

  /// Résultat de cette séance.
  final KnowledgeStatus status;
  final int mastery;

  /// Niveau de maîtrise (0 à 5) après et avant la séance.
  final int level;
  final int previousLevel;
  final String? explanation;

  bool get levelledUp => level > previousLevel;
}

/// Bilan (écran 7).
class Report {
  const Report({
    required this.scoreOn10,
    required this.knowledge,
    required this.lessonMastered,
    required this.canReviewErrors,
    this.nextReviewAt,
    this.rewards,
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
    rewards: switch (json['rewards']) {
      final Json rewards => Rewards.fromJson(rewards),
      _ => null,
    },
  );

  final double scoreOn10;
  final List<KnowledgeResult> knowledge;
  final DateTime? nextReviewAt;
  final bool lessonMastered;
  final bool canReviewErrors;

  /// XP, badges et message de la séance (étape 20).
  final Rewards? rewards;

  List<KnowledgeResult> withStatus(KnowledgeStatus status) => [
    for (final k in knowledge)
      if (k.status == status) k,
  ];

  /// Notions qui ont gagné au moins un niveau pendant la séance.
  List<KnowledgeResult> get levelledUp => [
    for (final k in knowledge)
      if (k.levelledUp) k,
  ];
}

/// « Je n'ai pas compris » : une aide (1 indice, 2 rappel, 3 exemple, 4 étapes, 5 la réponse).
class HelpStep {
  const HelpStep({
    required this.level,
    required this.kind,
    required this.title,
    required this.text,
    this.lines = const [],
    this.last = false,
  });

  factory HelpStep.fromJson(Json json) => HelpStep(
    level: json['level'] as int,
    kind: json['kind'] as String,
    title: json['title'] as String,
    text: json['text'] as String,
    lines: [for (final l in json['lines'] as List<dynamic>? ?? const []) l as String],
    last: json['last'] as bool? ?? false,
  );

  final int level;
  final String kind;
  final String title;
  final String text;
  final List<String> lines;

  /// Plus d'aide après celle-ci.
  final bool last;
}

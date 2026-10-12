import 'account.dart' show Json;

/// Une réplique de la conversation : Ludi (l'élève joué par l'IA) ou l'enfant (le professeur).
class TeachMessage {
  const TeachMessage({required this.fromLudi, required this.text});

  factory TeachMessage.fromJson(Json json) =>
      TeachMessage(fromLudi: json['speaker'] != 'child', text: json['text'] as String);

  final bool fromLudi;
  final String text;
}

/// « Enseigne-moi » (§83) : l'enfant explique une notion de sa leçon à Ludi.
class Teach {
  const Teach({
    required this.id,
    required this.lessonId,
    required this.label,
    required this.finished,
    required this.messages,
    required this.total,
    this.covered,
    this.validated,
    this.summary,
  });

  factory Teach.fromJson(Json json) => Teach(
    id: json['id'] as String,
    lessonId: json['lesson_id'] as String,
    label: json['label'] as String,
    finished: json['status'] == 'finished',
    messages: [for (final m in json['messages'] as List<dynamic>) TeachMessage.fromJson(m as Json)],
    total: json['total'] as int? ?? 0,
    covered: json['covered'] as int?,
    validated: json['validated'] as bool?,
    summary: json['summary'] as String?,
  );

  final String id;
  final String lessonId;

  /// La notion expliquée.
  final String label;
  final bool finished;
  final List<TeachMessage> messages;

  /// Points clés attendus, et ceux expliqués (à la fin).
  final int total;
  final int? covered;

  /// Niveau « expliquer » validé (à la fin).
  final bool? validated;
  final String? summary;
}

/// Pour le parent : la notion, ce que l'enfant a expliqué, le bilan et la règle appliquée.
class TeachSummary {
  const TeachSummary({
    required this.id,
    required this.createdAt,
    required this.label,
    required this.finished,
    required this.total,
    required this.turns,
    this.lessonTitle,
    this.covered,
    this.validated,
    this.decision,
  });

  factory TeachSummary.fromJson(Json json) => TeachSummary(
    id: json['id'] as String,
    createdAt: DateTime.parse(json['created_at'] as String),
    lessonTitle: json['lesson_title'] as String?,
    label: json['label'] as String,
    finished: json['status'] == 'finished',
    total: json['total'] as int? ?? 0,
    covered: json['covered'] as int?,
    validated: json['validated'] as bool?,
    decision: json['decision'] as String?,
    turns: [
      for (final t in json['turns'] as List<dynamic>? ?? const [])
        ((t as Json)['question'] as String, t['answer'] as String),
    ],
  );

  final String id;
  final DateTime createdAt;
  final String? lessonTitle;
  final String label;
  final bool finished;
  final int total;
  final int? covered;
  final bool? validated;
  final String? decision;

  /// (question de Ludi, explication de l'enfant)
  final List<(String, String)> turns;
}

class TeachPage {
  const TeachPage({required this.teach, this.nextBefore});

  factory TeachPage.fromJson(Json json) => TeachPage(
    teach: [for (final t in json['teach'] as List<dynamic>) TeachSummary.fromJson(t as Json)],
    nextBefore: json['next_before'] as String?,
  );

  final List<TeachSummary> teach;
  final String? nextBefore;
}

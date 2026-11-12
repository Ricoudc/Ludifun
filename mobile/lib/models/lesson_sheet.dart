import 'account.dart' show Json;
import 'lesson.dart' show LessonIllustration;
import 'resource.dart';

/// Un exemple semblable, résolu.
class SheetExample {
  const SheetExample({required this.question, required this.answer, this.why});

  factory SheetExample.fromJson(Json json) => SheetExample(
    question: json['question'] as String,
    answer: json['answer'] as String,
    why: json['why'] as String?,
  );

  final String question;
  final String answer;
  final String? why;
}

/// Une notion de la fiche : de quoi la relire, sans jeu.
class SheetNotion {
  const SheetNotion({
    required this.id,
    required this.label,
    required this.statement,
    this.explanation,
    this.tip,
    this.cardFront,
    this.cardBack,
    this.example,
    this.level = 0,
    this.image,
  });

  factory SheetNotion.fromJson(Json json) => SheetNotion(
    id: json['id'] as String,
    label: json['label'] as String,
    statement: json['statement'] as String,
    explanation: json['explanation'] as String?,
    tip: json['tip'] as String?,
    cardFront: json['card_front'] as String?,
    cardBack: json['card_back'] as String?,
    example: switch (json['example']) {
      final Json example => SheetExample.fromJson(example),
      _ => null,
    },
    level: json['level'] as int? ?? 0,
    image: json['image'] as String?,
  );

  final String id;
  final String label;

  /// À retenir.
  final String statement;
  final String? explanation;
  final String? tip;

  /// Carte mémoire : la question, puis la réponse à retourner.
  final String? cardFront;
  final String? cardBack;
  final SheetExample? example;

  /// Niveau de maîtrise, 0 à 5.
  final int level;
  final String? image;
}

/// « Mon cahier » : la fiche de révision d'une leçon, à relire sans faire de jeux.
class LessonSheet {
  const LessonSheet({
    required this.lessonId,
    required this.notions,
    required this.resources,
    this.title,
    this.subject,
    this.grade,
    this.objective,
    this.summary,
    this.text,
    this.image,
  });

  factory LessonSheet.fromJson(Json json) => LessonSheet(
    lessonId: json['lesson_id'] as String,
    title: json['title'] as String?,
    subject: json['subject'] as String?,
    grade: json['grade'] as String?,
    objective: json['objective'] as String?,
    summary: json['summary'] as String?,
    text: json['text'] as String?,
    image: switch (json['image']) {
      final Json image => LessonIllustration.fromJson(image),
      _ => null,
    },
    notions: [for (final n in json['notions'] as List<dynamic>) SheetNotion.fromJson(n as Json)],
    resources: LessonResource.listFromJson(json['resources']),
  );

  final String lessonId;
  final String? title;
  final String? subject;
  final String? grade;
  final String? objective;
  final String? summary;

  /// Le texte de la leçon, tel qu'il a été lu.
  final String? text;
  final LessonIllustration? image;
  final List<SheetNotion> notions;
  final List<LessonResource> resources;
}

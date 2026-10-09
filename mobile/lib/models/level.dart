import 'account.dart';

/// Niveau de maîtrise d'une notion ou d'une compétence, de 0 à 5 (spécification technique §5.3).
///
/// 4 « maîtrisée » demande de retrouver la réponse seul (et d'appliquer une règle), pas
/// seulement de la reconnaître dans un QCM.
abstract final class Levels {
  static const max = 5;

  static const labels = [
    'Jamais travaillée',
    'Découverte',
    'Fragile',
    'En cours d\'acquisition',
    'Maîtrisée',
    'Très bien maîtrisée',
  ];

  static String label(int level) => labels[level.clamp(0, max)];

  /// `grey`, `red`, `orange` ou `green`, comme le serveur.
  static String color(int level) => switch (level) {
    <= 0 => 'grey',
    1 || 2 => 'red',
    3 => 'orange',
    _ => 'green',
  };
}

/// Ce que l'enfant doit savoir faire : le niveau de compréhension visé par une compétence.
const verbLabels = {
  'recognize': 'Reconnaître',
  'recall': 'Se rappeler',
  'apply': 'Appliquer',
  'explain': 'Expliquer',
  'transfer': 'Réutiliser',
};

/// Une compétence de la leçon (« Comparer deux fractions »), reliée à ses notions.
class Skill {
  const Skill({
    required this.id,
    required this.label,
    required this.verb,
    required this.importance,
    required this.level,
    this.knowledgeIds = const [],
    this.report,
  });

  factory Skill.fromJson(Json json) => Skill(
    id: json['id'] as String,
    label: json['label'] as String,
    verb: json['verb'] as String,
    importance: json['importance'] as int,
    // Écran de la leçon : un entier ; espace parent : {value, label, color}.
    level: switch (json['level']) {
      final int value => value,
      final Json level => level['value'] as int,
      _ => 0,
    },
    knowledgeIds: [
      for (final k in json['knowledge_ids'] as List<dynamic>? ?? const []) k as String,
    ],
    report: switch (json['report']) {
      final Json report => SkillReport.fromJson(report),
      _ => null,
    },
  );

  final String id;
  final String label;
  final String verb;
  final int importance;
  final int level;
  final List<String> knowledgeIds;

  /// Bilan pour le parent (espace parent seulement ; absent d'un serveur plus ancien).
  final SkillReport? report;
}

/// Bilan d'une compétence pour le parent, écrit par le serveur (§5.52).
class SkillReport {
  const SkillReport({
    required this.status,
    required this.summary,
    this.facts,
    this.weakest,
    this.advice,
  });

  factory SkillReport.fromJson(Json json) => SkillReport(
    status: json['status'] as String,
    summary: json['summary'] as String,
    facts: json['facts'] as String?,
    weakest: json['weakest'] as String?,
    advice: json['advice'] as String?,
  );

  /// not_started, to_work, in_progress, acquired.
  final String status;
  final String summary;
  final String? facts;
  final String? weakest;
  final String? advice;

  String get emoji => switch (status) {
    'acquired' => '✅',
    'in_progress' => '🟠',
    'to_work' => '🔴',
    _ => '⚪',
  };
}

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
  );

  final String id;
  final String label;
  final String verb;
  final int importance;
  final int level;
  final List<String> knowledgeIds;
}

/// Matières (§6.2) : libellé et icône affichés à l'enfant.
abstract final class Subjects {
  static const _labels = {
    'french': ('Français', '📖'),
    'math': ('Mathématiques', '📐'),
    'history': ('Histoire', '🏛️'),
    'geography': ('Géographie', '🌍'),
    'science': ('Sciences', '🔬'),
    'english': ('Anglais', '🇬🇧'),
    'civics': ('Enseignement moral et civique', '🤝'),
  };

  /// Les matières, dans l'ordre des programmes.
  static List<String> get all => _labels.keys.toList();

  static String label(String? subject) => _labels[subject]?.$1 ?? 'Leçon';

  static String emoji(String? subject) => _labels[subject]?.$2 ?? '📚';
}

/// Niveaux, du CP à la 3e.
const grades = ['CP', 'CE1', 'CE2', 'CM1', 'CM2', '6e', '5e', '4e', '3e'];

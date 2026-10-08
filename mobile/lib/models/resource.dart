import 'dart:convert';

import 'account.dart';

/// Ressources des sites de confiance (étape 30) : exercices MathALÉA, quiz Vikidia, vidéos et
/// quiz Lumni, ouverts dans la visionneuse de l'application, qui reste sur le site.

enum ResourceProvider {
  mathalea('🧮', 'MathALÉA', ['coopmaths.fr']),
  vikidia('📖', 'Vikidia', ['vikidia.org']),
  lumni('📺', 'Lumni', ['lumni.fr']);

  const ResourceProvider(this.emoji, this.label, this.hosts);

  final String emoji;
  final String label;

  /// Seuls ces sites (et leurs sous-domaines) s'ouvrent dans la visionneuse.
  final List<String> hosts;

  bool allows(Uri uri) =>
      uri.scheme == 'https' && hosts.any((h) => uri.host == h || uri.host.endsWith('.$h'));
}

enum ResourceKind {
  exercise('Exercice noté'),
  quiz('Quiz'),
  video('Vidéo'),
  article('Article');

  const ResourceKind(this.label);

  final String label;
}

/// Meilleur score d'un exercice noté.
class ResourceScore {
  const ResourceScore(this.correct, this.total);

  factory ResourceScore.fromJson(Json json) =>
      ResourceScore(json['correct'] as int, json['total'] as int);

  final int correct;
  final int total;

  Json toJson() => {'correct': correct, 'total': total};

  @override
  String toString() => '$correct/$total';
}

class LessonResource {
  const LessonResource({
    required this.id,
    required this.provider,
    required this.kind,
    required this.title,
    required this.url,
    required this.licence,
    this.best,
  });

  /// `null` pour un site ou un type que cette version de l'application ne connaît pas : sauté.
  static LessonResource? tryParse(Json json) {
    final provider = ResourceProvider.values.asNameMap()[json['provider']];
    final kind = ResourceKind.values.asNameMap()[json['kind']];
    final url = Uri.tryParse(json['url'] as String? ?? '');
    if (provider == null || kind == null || url == null || !provider.allows(url)) return null;
    return LessonResource(
      id: json['id'] as String,
      provider: provider,
      kind: kind,
      title: json['title'] as String,
      url: url,
      licence: json['licence'] as String? ?? provider.label,
      best: switch (json['best']) {
        final Json b => ResourceScore.fromJson(b),
        _ => null,
      },
    );
  }

  static List<LessonResource> listFromJson(Object? json) => [
    for (final r in json as List<dynamic>? ?? const []) ?LessonResource.tryParse(r as Json),
  ];

  final String id;
  final ResourceProvider provider;
  final ResourceKind kind;
  final String title;
  final Uri url;

  /// Source et licence, affichées sous la page.
  final String licence;
  final ResourceScore? best;
}

/// Vue du parent : avec les essais de l'enfant et le choix de masquer.
class ParentResource {
  const ParentResource({
    required this.resource,
    required this.hidden,
    required this.attempts,
    this.lastDoneAt,
  });

  final LessonResource resource;
  final bool hidden;
  final int attempts;
  final DateTime? lastDoneAt;

  static ParentResource? tryParse(Json json) => switch (LessonResource.tryParse(json)) {
    final resource? => ParentResource(
      resource: resource,
      hidden: json['hidden'] as bool? ?? false,
      attempts: json['attempts'] as int? ?? 0,
      lastDoneAt: switch (json['last_done_at']) {
        final String d => DateTime.parse(d),
        _ => null,
      },
    ),
    null => null,
  };
}

class LessonResources {
  const LessonResources({required this.available, this.resources = const []});

  factory LessonResources.fromJson(Json json) => LessonResources(
    available: json['available'] as bool? ?? false,
    resources: [
      for (final r in json['resources'] as List<dynamic>? ?? const [])
        ?ParentResource.tryParse(r as Json),
    ],
  );

  /// Le parent a permis les sites de confiance et le serveur les propose.
  final bool available;
  final List<ParentResource> resources;
}

/// Score envoyé par un exercice MathALÉA à la fin (message `postMessage` de la page) :
/// `{"action": "mathalea:score", "resultsByExercice": [{"numberOfPoints", "numberOfQuestions"}]}`
/// ou, pour les anciennes versions, `{"nbBonnesReponses", "nbMauvaisesReponses"}`.
/// `null` pour tout autre message.
ResourceScore? scoreFromMessage(String message) {
  Object? data;
  try {
    data = jsonDecode(message);
  } on FormatException {
    return null;
  }
  if (data is! Map) return null;
  int? count(Object? value) => value is num && value >= 0 ? value.round() : null;
  var (correct, total) = (0, 0);
  if (data['action'] == 'mathalea:score' && data['resultsByExercice'] is List) {
    for (final result in data['resultsByExercice'] as List) {
      if (result is! Map) continue;
      final points = count(result['numberOfPoints']);
      final questions = count(result['numberOfQuestions']);
      if (points == null || questions == null) continue;
      correct += points;
      total += questions;
    }
  } else if (count(data['nbBonnesReponses']) case final right?) {
    correct = right;
    total = right + (count(data['nbMauvaisesReponses']) ?? 0);
  }
  if (total <= 0 || total > 100 || correct > total) return null;
  return ResourceScore(correct, total);
}

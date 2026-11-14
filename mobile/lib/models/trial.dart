import 'account.dart';
import 'session.dart';

/// Une activité de l'essai du parent, avec le nom des notions qu'elle fait travailler.
class TrialItem {
  const TrialItem({required this.item, required this.notions});

  final SessionItem item;
  final List<String> notions;
}

/// « Essayer la leçon » (§5.84) : la séance que l'enfant aura, jouée par le parent. Rien n'est
/// enregistré ; `seed` et `plan` sont renvoyés au serveur pour chaque correction.
class LessonTrial {
  const LessonTrial({
    required this.seed,
    required this.plan,
    required this.items,
    this.full = false,
    this.totalNotions,
    this.neverShown = const [],
  });

  factory LessonTrial.fromJson(Json json) {
    final labels = (json['notions'] as Json? ?? const {}).cast<String, Object?>();
    return LessonTrial(
      full: json['full'] as bool? ?? false,
      totalNotions: json['total_notions'] as int?,
      neverShown: (json['never_shown'] as List<dynamic>? ?? const []).cast<String>(),
      seed: json['seed'] as String,
      plan: json['plan'] as String,
      items: [
        for (final raw in json['items'] as List<dynamic>)
          TrialItem(
            item: SessionItem.fromJson(raw as Json),
            notions: [
              for (final id in (raw['knowledge_ids'] as List<dynamic>? ?? const []))
                if (labels[id] case final String label) label,
            ],
          ),
      ],
    );
  }

  final String seed;
  final String plan;
  final List<TrialItem> items;

  /// Essai de toute la leçon : chaque notion que l'enfant peut travailler y passe (§5.90).
  final bool full;

  /// Notions que l'enfant peut travailler ; absent avec un ancien serveur.
  final int? totalNotions;

  /// Notions secondaires que les séances ne travaillent pas : l'enfant ne les verra pas non plus.
  final List<String> neverShown;
}

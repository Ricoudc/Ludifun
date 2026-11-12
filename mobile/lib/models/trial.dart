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
  const LessonTrial({required this.seed, required this.plan, required this.items});

  factory LessonTrial.fromJson(Json json) {
    final labels = (json['notions'] as Json? ?? const {}).cast<String, Object?>();
    return LessonTrial(
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
}

/// Progression ludique (étape 20) : XP, niveau, série et badges. Jamais liés à la note.
library;

import 'account.dart';

class BadgeInfo {
  const BadgeInfo({
    required this.code,
    required this.emoji,
    required this.title,
    required this.how,
    this.earnedAt,
  });

  factory BadgeInfo.fromJson(Json json) => BadgeInfo(
    code: json['code'] as String,
    emoji: json['emoji'] as String,
    title: json['title'] as String,
    how: json['how'] as String,
    earnedAt: switch (json['earned_at']) {
      final String at => DateTime.parse(at),
      _ => null,
    },
  );

  final String code;
  final String emoji;
  final String title;

  /// Comment le gagner (affiché tant qu'il ne l'est pas).
  final String how;
  final DateTime? earnedAt;

  bool get earned => earnedAt != null;
}

class Progress {
  const Progress({
    required this.totalXp,
    required this.level,
    required this.levelStartXp,
    required this.nextLevelXp,
    required this.streakDays,
    required this.doneToday,
    required this.badges,
  });

  factory Progress.fromJson(Json json) => Progress(
    totalXp: json['total_xp'] as int,
    level: json['level'] as int,
    levelStartXp: json['level_start_xp'] as int,
    nextLevelXp: json['next_level_xp'] as int,
    streakDays: json['streak_days'] as int,
    doneToday: json['done_today'] as bool? ?? false,
    badges: [for (final b in json['badges'] as List<dynamic>) BadgeInfo.fromJson(b as Json)],
  );

  final int totalXp;
  final int level;
  final int levelStartXp;
  final int nextLevelXp;
  final int streakDays;
  final bool doneToday;

  /// Tout le catalogue : les badges gagnés d'abord.
  final List<BadgeInfo> badges;

  double get levelProgress => (totalXp - levelStartXp) / (nextLevelXp - levelStartXp);

  int get earnedBadges => badges.where((b) => b.earned).length;
}

class Rewards {
  const Rewards({
    required this.xp,
    required this.lines,
    required this.message,
    required this.newBadges,
    required this.progress,
  });

  factory Rewards.fromJson(Json json) => Rewards(
    xp: json['xp'] as int,
    lines: [
      for (final l in json['lines'] as List<dynamic>)
        ((l as Json)['label'] as String, l['xp'] as int),
    ],
    message: json['message'] as String,
    newBadges: [for (final b in json['new_badges'] as List<dynamic>) BadgeInfo.fromJson(b as Json)],
    progress: Progress.fromJson(json['progress'] as Json),
  );

  final int xp;

  /// « Séance terminée +10 », « Notions enfin réussies +10 »…
  final List<(String, int)> lines;

  /// Le progrès le plus parlant de la séance (« 🏆 Tu as réussi une notion… »).
  final String message;
  final List<BadgeInfo> newBadges;
  final Progress progress;
}

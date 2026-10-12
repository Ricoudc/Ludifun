import 'package:flutter/material.dart';

import '../../app/theme.dart';
import '../../models/rewards.dart';

/// « ⭐ 120 XP · Niveau 2 — 🔥 Série : 4 jours » (accueil de l'enfant, tableau de bord du parent).
class ProgressStrip extends StatelessWidget {
  const ProgressStrip(this.progress, {this.onBadges, super.key});

  final Progress progress;
  final VoidCallback? onBadges;

  @override
  Widget build(BuildContext context) {
    final p = progress;
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Wrap(
              spacing: 16,
              runSpacing: 4,
              children: [
                Text(
                  '⭐ ${p.totalXp} XP · Niveau ${p.level}',
                  style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
                ),
                if (p.streakDays > 0)
                  Text(
                    '🔥 Série : ${p.streakDays} jour${p.streakDays > 1 ? 's' : ''}',
                    style: const TextStyle(fontSize: 17),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Semantics(
              label: 'Encore ${p.nextLevelXp - p.totalXp} XP avant le niveau ${p.level + 1}',
              child: LinearProgressIndicator(
                value: p.levelProgress.clamp(0, 1).toDouble(),
                minHeight: 8,
                color: LudiColors.accent,
                borderRadius: BorderRadius.circular(4),
              ),
            ),
            if (onBadges != null)
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: onBadges,
                  child: Text('🏅 Mes badges (${p.earnedBadges})'),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

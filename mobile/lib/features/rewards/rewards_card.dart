import 'package:flutter/material.dart';

import '../../app/theme.dart';
import '../../models/rewards.dart';

/// Bilan : ce que l'effort a rapporté (« XP : +35 »), le progrès du jour et les nouveaux badges.
class RewardsCard extends StatelessWidget {
  const RewardsCard(this.rewards, {super.key});

  final Rewards rewards;

  @override
  Widget build(BuildContext context) {
    final r = rewards;
    final streak = r.progress.streakDays;
    return Card(
      color: LudiColors.accent.withValues(alpha: 0.14),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(r.message, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700)),
            const SizedBox(height: 12),
            if (r.xp > 0) ...[
              Text(
                '⭐ +${r.xp} XP',
                style: Theme.of(context).textTheme.titleLarge
                    ?.copyWith(fontWeight: FontWeight.w900),
              ),
              for (final (label, xp) in r.lines)
                Text('$label  +$xp', style: const TextStyle(fontSize: 16)),
            ] else
              const Text(
                'Tu as déjà gagné tout l\'XP du jour : repose-toi, tu l\'as bien mérité !',
                style: TextStyle(fontSize: 16),
              ),
            if (streak > 1) ...[
              const SizedBox(height: 8),
              Text('🔥 Série : $streak jours', style: const TextStyle(fontSize: 16)),
            ],
            for (final badge in r.newBadges) ...[
              const SizedBox(height: 10),
              Row(
                children: [
                  Text(badge.emoji, style: const TextStyle(fontSize: 34)),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'Nouveau badge : ${badge.title} !',
                      style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
                    ),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

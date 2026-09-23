import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';

/// Premier lancement : cet appareil sert l'espace parent ou l'espace enfant.
class StartScreen extends StatelessWidget {
  const StartScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
    body: CenteredBody(
      children: [
        const Logo(),
        const SizedBox(height: 8),
        Text(
          'Photographie ta leçon, révise en jouant.',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 40),
        Text(
          'Qui utilise cet appareil ?',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 24),
        _SpaceCard(
          emoji: '🧒',
          title: 'Je suis un enfant',
          subtitle: 'Mon parent m\'a donné un code pour relier cet appareil.',
          color: LudiColors.accent,
          onTap: () => context.go(Routes.link),
        ),
        const SizedBox(height: 16),
        _SpaceCard(
          emoji: '👤',
          title: 'Je suis un parent',
          subtitle: 'Je crée les profils de mes enfants et je suis leurs progrès.',
          color: LudiColors.primary,
          onTap: () => context.go(Routes.parentSignIn),
        ),
      ],
    ),
  );
}

class _SpaceCard extends StatelessWidget {
  const _SpaceCard({
    required this.emoji,
    required this.title,
    required this.subtitle,
    required this.color,
    required this.onTap,
  });

  final String emoji;
  final String title;
  final String subtitle;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Card(
    clipBehavior: Clip.antiAlias,
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(18),
      side: BorderSide(color: color, width: 2),
    ),
    child: InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            Text(emoji, style: const TextStyle(fontSize: 40)),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(color: color),
                  ),
                  const SizedBox(height: 4),
                  Text(subtitle),
                ],
              ),
            ),
            Icon(Icons.chevron_right, color: color),
          ],
        ),
      ),
    ),
  );
}

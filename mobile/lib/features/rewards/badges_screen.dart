import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../models/rewards.dart';
import '../home/home_providers.dart';
import 'progress_strip.dart';

/// Mes badges : ceux gagnés, et comment gagner les autres (jamais de badge de note).
class BadgesScreen extends ConsumerWidget {
  const BadgesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final progress = ref.watch(progressProvider);
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.childHome)),
        title: const Text('Mes badges'),
      ),
      body: CenteredBody(
        top: true,
        children: switch (progress) {
          AsyncData(value: final p) => [
            ProgressStrip(p),
            const SizedBox(height: 12),
            for (final badge in p.badges) _BadgeTile(badge),
          ],
          AsyncError(:final error) => [
            ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
          ],
          _ => [const Center(child: CircularProgressIndicator())],
        },
      ),
    );
  }
}

class _BadgeTile extends StatelessWidget {
  const _BadgeTile(this.badge);

  final BadgeInfo badge;

  @override
  Widget build(BuildContext context) => Opacity(
    opacity: badge.earned ? 1 : 0.45,
    child: ListTile(
      leading: Text(badge.earned ? badge.emoji : '🔒', style: const TextStyle(fontSize: 32)),
      title: Text(badge.title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
      subtitle: Text(badge.earned ? 'Gagné !' : badge.how),
      trailing: badge.earned ? const Icon(Icons.check_circle, color: LudiColors.mastered) : null,
    ),
  );
}

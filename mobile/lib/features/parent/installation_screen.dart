import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/session.dart';
import '../../models/parent.dart';

final installationProvider = FutureProvider.autoDispose<InstallationReport>(
  (ref) => ref.watch(apiProvider).installation(),
);

(IconData, Color) _look(String level) => switch (level) {
  'error' => (Icons.error_outline, LudiColors.notMastered),
  'warning' => (Icons.warning_amber_outlined, LudiColors.toReview),
  _ => (Icons.check_circle_outline, LudiColors.mastered),
};

/// Sur l'accueil du parent : rien si tout va bien ; sinon le point le plus grave, et un accès à
/// l'état complet. Un serveur plus ancien (route absente) : rien non plus.
class InstallationCard extends ConsumerWidget {
  const InstallationCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final report = ref.watch(installationProvider).value;
    final problems = report?.problems ?? const <InstallationCheck>[];
    if (problems.isEmpty) return const SizedBox.shrink();
    final first = problems.first;
    final (icon, color) = _look(first.level);
    return Card(
      margin: const EdgeInsets.only(top: 12),
      child: ListTile(
        leading: Icon(icon, color: color),
        title: Text(
          problems.length == 1 ? first.title : '${problems.length} points à regarder',
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
        subtitle: Text(first.message, maxLines: 3, overflow: TextOverflow.ellipsis),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => context.go(Routes.installation),
      ),
    );
  }
}

/// « État de l'installation » (§5.89) : ce qui marche, ce qui bloque, et quoi faire.
class InstallationScreen extends ConsumerWidget {
  const InstallationScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final report = ref.watch(installationProvider);
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.parentHome)),
        title: const Text('État de l\'installation'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Vérifier de nouveau',
            onPressed: () => ref.invalidate(installationProvider),
          ),
        ],
      ),
      body: CenteredBody(
        top: true,
        children: switch (report) {
          AsyncData(:final value) => [
            Text(switch (value.level) {
              'error' => 'Quelque chose bloque',
              'warning' => 'Ça marche, avec des points à regarder',
              _ => 'Tout va bien',
            }, style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 4),
            const Text(
              'Ludifun vérifie son IA et les dernières leçons. Rien n\'est envoyé à l\'IA pour '
              'cette vérification.',
              style: TextStyle(fontSize: 15, color: Colors.black54),
            ),
            const SizedBox(height: 12),
            for (final check in value.checks) _CheckCard(check),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: () => context.go(Routes.aiSettings),
              icon: const Icon(Icons.tune),
              label: const Text('Régler l\'intelligence artificielle'),
            ),
          ],
          AsyncError() => [
            const Text(
              'L\'état de l\'installation n\'a pas pu être lu. Le serveur est-il à jour et joignable ?',
              style: TextStyle(fontSize: 17),
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: () => ref.invalidate(installationProvider),
              child: const Text('Réessayer'),
            ),
          ],
          _ => [const Center(child: CircularProgressIndicator())],
        },
      ),
    );
  }
}

class _CheckCard extends StatelessWidget {
  const _CheckCard(this.check);

  final InstallationCheck check;

  @override
  Widget build(BuildContext context) {
    final (icon, color) = _look(check.level);
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    check.title,
                    style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 4),
                  Text(check.message, style: const TextStyle(fontSize: 15)),
                  if (check.action case final action?) ...[
                    const SizedBox(height: 8),
                    Text(
                      '👉 $action',
                      style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

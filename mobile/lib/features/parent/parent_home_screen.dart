import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../core/storage/credentials.dart';
import '../../models/account.dart';

final childrenProvider = FutureProvider.autoDispose<List<Child>>(
  (ref) => ref.watch(apiProvider).children(),
);

/// Écran P2 (socle) : les enfants de la famille. Ajout, codes de liaison et tableau
/// de bord arrivent à l'étape 12.
class ParentHomeScreen extends ConsumerWidget {
  const ParentHomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final children = ref.watch(childrenProvider);
    final email = switch (ref.watch(sessionProvider).value) {
      ParentCredentials(:final email) => email,
      _ => '',
    };
    return Scaffold(
      appBar: AppBar(
        title: const Text('Mes enfants'),
        actions: [
          IconButton(
            tooltip: 'Me déconnecter',
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(sessionProvider.notifier).signOut(),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(childrenProvider.future),
        child: CenteredBody(
          top: true,
          children: [
            Text(email, style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 16),
            ...switch (children) {
              AsyncData(value: final list) when list.isEmpty => [
                const Text(
                  'Aucun profil pour l\'instant. L\'ajout d\'un enfant et la liaison de sa '
                  'tablette arrivent très bientôt.',
                ),
              ],
              AsyncData(value: final list) => [
                for (final child in list) ...[_ChildTile(child), const SizedBox(height: 12)],
              ],
              AsyncError(:final error) => [
                ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
                TextButton(
                  onPressed: () => ref.invalidate(childrenProvider),
                  child: const Text('Réessayer'),
                ),
              ],
              _ => [const Center(child: CircularProgressIndicator())],
            },
          ],
        ),
      ),
    );
  }
}

class _ChildTile extends StatelessWidget {
  const _ChildTile(this.child);

  final Child child;

  @override
  Widget build(BuildContext context) => Card(
    child: ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
      leading: CircleAvatar(child: Text(child.displayName.characters.first.toUpperCase())),
      title: Text(child.displayName, style: Theme.of(context).textTheme.titleLarge),
      subtitle: Text(
        '${child.grade} · ${switch (child.devices) {
          0 => 'aucun appareil lié',
          1 => '1 appareil lié',
          final n => '$n appareils liés',
        }}',
      ),
    ),
  );
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/session.dart';
import '../../core/storage/credentials.dart';
import '../../models/account.dart';

/// Profil de l'enfant ; appelé à l'ouverture, il détecte aussi un appareil délié.
final meProvider = FutureProvider.autoDispose<Child>((ref) => ref.watch(apiProvider).me());

/// Écran 1 (socle) : accueil de l'enfant. Mission du jour et leçons à l'étape 10.
class ChildHomeScreen extends ConsumerWidget {
  const ChildHomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stored = switch (ref.watch(sessionProvider).value) {
      ChildCredentials(:final displayName) => displayName,
      _ => '',
    };
    final name = ref.watch(meProvider).value?.displayName ?? stored;
    return Scaffold(
      body: CenteredBody(
        children: [
          Text('Bonjour $name ! 👋', style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: 24),
          Card(
            color: LudiColors.primary,
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '🎯 Ta mission du jour',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(color: Colors.white),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Bientôt ici : photographie ta leçon et révise-la en jouant.',
                    style: TextStyle(color: Colors.white, fontSize: 18),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

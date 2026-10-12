import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../app/theme.dart';
import 'api/api_exception.dart';
import 'link_opener.dart';
import 'session.dart';

/// Numéro de cette construction de l'application (APK de test : `--dart-define=LUDIFUN_BUILD`,
/// le numéro de la construction GitHub). 0 : construite à la main ou publiée sur le Play Store,
/// qui se met à jour tout seul : jamais de bandeau.
const appBuild = int.fromEnvironment('LUDIFUN_BUILD');

final appBuildProvider = Provider<int>((ref) => appBuild);

/// Une version plus récente que celle-ci, proposée par le serveur de la maison (§5.50).
typedef AppUpdate = ({int build, String url});

final appUpdateProvider = FutureProvider<AppUpdate?>((ref) async {
  final mine = ref.watch(appBuildProvider);
  if (mine <= 0) return null;
  try {
    final latest = await ref.read(apiProvider).latestApp();
    if (latest == null || latest.build <= mine) return null;
    return latest;
  } on ApiException {
    return null; // serveur sans application à donner, ou injoignable : rien à dire
  }
});

/// « Nouvelle version de Ludifun » : ouvre le téléchargement de l'APK ; Android propose ensuite
/// de l'installer par-dessus (compte et réglages gardés).
class AppUpdateBanner extends ConsumerWidget {
  const AppUpdateBanner({this.forChild = false, super.key});

  /// Côté enfant : on lui dit de demander à un adulte.
  final bool forChild;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final update = ref.watch(appUpdateProvider).value;
    if (update == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Card(
        color: LudiColors.primary.withValues(alpha: 0.08),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                forChild
                    ? '📲 Une nouvelle version de Ludifun est prête. Demande à un adulte !'
                    : '📲 Une nouvelle version de Ludifun est prête.',
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 4),
              const Text(
                'Après le téléchargement, ouvrez le fichier et acceptez l\'installation : '
                'le compte et les réglages sont gardés.',
                style: TextStyle(color: Colors.black54),
              ),
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: () => openPublicPage(ref, update.url),
                icon: const Icon(Icons.system_update),
                label: const Text('Mettre à jour'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

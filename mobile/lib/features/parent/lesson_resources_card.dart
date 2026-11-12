import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_exception.dart';
import '../../core/link_opener.dart';
import '../../core/session.dart';
import '../../models/resource.dart';
import '../lesson/resource_screen.dart';

final lessonResourcesProvider = FutureProvider.autoDispose
    .family<LessonResources, (String, String)>(
      (ref, ids) => ref.watch(apiProvider).lessonResources(ids.$1, ids.$2),
    );

/// Après « Chercher », la liste est relue à ces moments (la recherche se fait en arrière-plan).
const resourceRefreshDelays = [Duration(seconds: 10), Duration(seconds: 40)];

/// Ressources des sites de confiance (étape 30) : exercices MathALÉA, quiz Vikidia, vidéos Lumni.
/// Le parent les regarde, voit les essais et le meilleur score, et masque ce qui ne convient pas.
class LessonResourcesCard extends ConsumerStatefulWidget {
  const LessonResourcesCard({required this.childId, required this.lessonId, super.key});

  final String childId;
  final String lessonId;

  @override
  ConsumerState<LessonResourcesCard> createState() => _LessonResourcesCardState();
}

class _LessonResourcesCardState extends ConsumerState<LessonResourcesCard> {
  final List<Timer> _refresh = [];
  bool _busy = false;

  (String, String) get _ids => (widget.childId, widget.lessonId);

  @override
  void dispose() {
    for (final timer in _refresh) {
      timer.cancel();
    }
    super.dispose();
  }

  Future<void> _act(Future<Object?> Function() action, String done) async {
    setState(() => _busy = true);
    String message;
    try {
      await action();
      message = done;
    } on ApiException catch (error) {
      message = error.message;
    }
    if (!mounted) return;
    setState(() => _busy = false);
    ref.invalidate(lessonResourcesProvider(_ids));
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _search() async {
    await _act(
      () => ref.read(apiProvider).prepareResources(_ids.$1, _ids.$2),
      'Recherche lancée sur les sites de confiance : la liste se met à jour dans un instant.',
    );
    if (!mounted) return;
    for (final delay in resourceRefreshDelays) {
      _refresh.add(Timer(delay, () => ref.invalidate(lessonResourcesProvider(_ids))));
    }
  }

  @override
  Widget build(BuildContext context) {
    final value = ref.watch(lessonResourcesProvider(_ids)).value;
    if (value == null) return const SizedBox();
    final api = ref.read(apiProvider);
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const Icon(Icons.public),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'Pour s\'entraîner autrement',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              value.available
                  ? 'Exercices, jeux, vidéos et fiches des sites de confiance (MathALÉA, Vikidia, '
                        'Lumni, Logiciel Éducatif, Bout de Gomme, Khan Academy…) sur le sujet de la leçon. '
                        'Ils s\'ouvrent dans l\'application, sans quitter le site choisi. Le score '
                        'des exercices est gardé ici ; il ne change pas la progression de l\'enfant.'
                  : 'Autorisez les sites éducatifs de confiance (Mon compte → Intelligence '
                        'artificielle) pour proposer à l\'enfant des exercices MathALÉA, des quiz '
                        'Vikidia et des vidéos Lumni.',
              style: const TextStyle(fontSize: 14, color: Colors.black54),
            ),
            if (value.resources.isEmpty && value.available)
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text('Rien de trouvé pour cette leçon pour l\'instant.'),
              ),
            for (final item in value.resources)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Text(
                  item.resource.provider.emoji,
                  style: TextStyle(fontSize: 24, color: item.hidden ? Colors.black26 : null),
                ),
                title: Text(
                  item.resource.title,
                  style: TextStyle(color: item.hidden ? Colors.black38 : null),
                ),
                subtitle: Text(
                  [
                    '${item.resource.kind.label} · ${item.resource.provider.label}',
                    if (item.hidden) 'masquée',
                    if (item.attempts > 0) '${item.attempts} essai(s)',
                    if (item.resource.best case final best?) 'meilleur score $best',
                  ].join(' · '),
                ),
                trailing: Switch(
                  value: !item.hidden,
                  onChanged: _busy
                      ? null
                      : (visible) => _act(
                          () => api.setResourceHidden(
                            _ids.$1,
                            _ids.$2,
                            item.resource.id,
                            hidden: !visible,
                          ),
                          visible
                              ? 'L\'enfant voit de nouveau « ${item.resource.title} ».'
                              : '« ${item.resource.title} » est masquée pour l\'enfant.',
                        ),
                ),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(builder: (_) => ResourceScreen(resource: item.resource)),
                ),
              ),
            if (value.available) ...[
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                  onPressed: _busy ? null : _search,
                  icon: const Icon(Icons.travel_explore),
                  label: const Text('Chercher des ressources'),
                ),
              ),
            ],
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              shape: const Border(),
              title: const Text('Autres sites de confiance (avec un compte)'),
              children: [
                for (final site in accountSites)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Text(site.emoji, style: const TextStyle(fontSize: 24)),
                    title: Text(site.name),
                    subtitle: Text(site.about),
                    trailing: site.url == null ? null : const Icon(Icons.open_in_new),
                    onTap: switch (site.url) {
                      final url? => () => ref.read(linkOpenerProvider).open(url),
                      null => null,
                    },
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

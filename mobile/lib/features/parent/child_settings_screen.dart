import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/format.dart';
import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/parent.dart';
import '../../models/subject.dart';
import '../home/home_providers.dart';
import 'file_sharer.dart';
import 'parent_home_screen.dart';
import 'parent_providers.dart';

/// Écran P4 : historique des séances, appareils liés, profil, suppression.
class ChildSettingsScreen extends ConsumerStatefulWidget {
  const ChildSettingsScreen({required this.childId, super.key});

  final String childId;

  @override
  ConsumerState<ChildSettingsScreen> createState() => _ChildSettingsScreenState();
}

class _ChildSettingsScreenState extends ConsumerState<ChildSettingsScreen> {
  final _history = <HistoryEntry>[];
  String? _nextBefore;
  bool _loading = true;
  bool _complete = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadMore();
  }

  Future<void> _loadMore() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await ref
          .read(apiProvider)
          .history(widget.childId, before: _history.isEmpty ? null : _nextBefore);
      _history.addAll(page.sessions);
      _nextBefore = page.nextBefore;
      _complete = page.nextBefore == null;
    } on ApiException catch (error) {
      _error = error.message;
    }
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _unlink(Device device) async {
    final ok = await confirmDanger(
      context,
      title: 'Délier cet appareil ?',
      message: 'Il n\'aura plus accès au profil. Pour le relier, il faudra un nouveau code.',
      action: 'Délier',
    );
    if (!ok) return;
    try {
      await ref.read(apiProvider).revokeDevice(widget.childId, device.id);
      ref
        ..invalidate(devicesProvider(widget.childId))
        ..invalidate(childrenProvider);
    } on ApiException catch (error) {
      if (mounted) showError(context, error);
    }
  }

  bool _exporting = false;

  /// §16.2 : le parent récupère toutes les données de son enfant dans un fichier.
  Future<void> _export(String name) async {
    setState(() => _exporting = true);
    try {
      final export = await ref.read(apiProvider).exportChild(widget.childId);
      await ref
          .read(fileSharerProvider)
          .share(
            filename: export.filename,
            bytes: export.bytes,
            mimeType: 'application/json',
            subject: 'Données Ludifun de $name',
          );
    } on ApiException catch (error) {
      if (mounted) showError(context, error);
    } on Exception {
      if (mounted) {
        showError(context, const ApiException('share', 'Impossible de partager le fichier.'));
      }
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  Future<void> _deleteChild(String name) async {
    final ok = await confirmDanger(
      context,
      title: 'Supprimer le profil de $name ?',
      message:
          'Ses leçons, ses séances et ses résultats seront définitivement effacés, et ses '
          'appareils déliés.',
      action: 'Supprimer',
    );
    if (!ok) return;
    try {
      await ref.read(apiProvider).deleteChild(widget.childId);
      ref.invalidate(childrenProvider);
      if (mounted) context.go(Routes.parentHome);
    } on ApiException catch (error) {
      if (mounted) showError(context, error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final child = ref.watch(childProvider(widget.childId)).value;
    final devices = ref.watch(devicesProvider(widget.childId));
    final now = ref.watch(nowProvider)();
    final name = child?.displayName ?? '';
    final theme = Theme.of(context).textTheme;
    Widget section(String title) => Padding(
      padding: const EdgeInsets.only(top: 28, bottom: 8),
      child: Text(title, style: theme.titleLarge),
    );
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.childDashboard(widget.childId))),
        title: Text(name.isEmpty ? 'Historique et réglages' : '$name · historique et réglages'),
      ),
      body: CenteredBody(
        top: true,
        children: [
          Text('Séances', style: theme.titleLarge),
          const SizedBox(height: 8),
          if (_history.isEmpty && !_loading && _error == null)
            Text('$name n\'a pas encore fait de séance.'),
          for (final entry in _history) _HistoryTile(entry, now),
          if (_error != null) ErrorMessage(_error!),
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(12),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (!_complete || _error != null)
            TextButton(onPressed: _loadMore, child: const Text('Voir les séances plus anciennes')),
          section('Appareils liés'),
          ...switch (devices) {
            AsyncData(value: final list) when list.isEmpty => [
              const Text('Aucun appareil lié.'),
              TextButton.icon(
                onPressed: () => context.go(Routes.childLink(widget.childId)),
                icon: const Icon(Icons.link),
                label: const Text('Lier un appareil'),
              ),
            ],
            AsyncData(value: final list) => [
              for (final d in list)
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.tablet_android),
                    title: Text(d.name ?? 'Appareil'),
                    subtitle: Text(
                      d.lastSeenAt == null
                          ? 'Lié ${when(d.createdAt, now)}'
                          : 'Utilisé ${when(d.lastSeenAt!, now)}',
                    ),
                    trailing: TextButton(onPressed: () => _unlink(d), child: const Text('Délier')),
                  ),
                ),
            ],
            AsyncError(:final error) => [
              ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
            ],
            _ => [const Center(child: CircularProgressIndicator())],
          },
          section('Données'),
          Text(
            'Un fichier avec tout ce que Ludifun conserve sur $name : profil, appareils, texte '
            'des leçons, notions, résultats et réponses (droit d\'accès, RGPD).',
            style: const TextStyle(color: Colors.black54),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: _exporting ? null : () => _export(name),
            icon: _exporting
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.download_outlined),
            label: Text(name.isEmpty ? 'Exporter les données' : 'Exporter les données de $name'),
          ),
          section('Profil'),
          OutlinedButton.icon(
            onPressed: () => context.go(Routes.childEdit(widget.childId)),
            icon: const Icon(Icons.edit_outlined),
            label: const Text('Modifier le profil'),
          ),
          const SizedBox(height: 12),
          TextButton.icon(
            style: TextButton.styleFrom(foregroundColor: LudiColors.notMastered),
            onPressed: () => _deleteChild(name),
            icon: const Icon(Icons.delete_outline),
            label: Text('Supprimer $name et toutes ses données'),
          ),
        ],
      ),
    );
  }
}

class _HistoryTile extends StatelessWidget {
  const _HistoryTile(this.entry, this.now);

  final HistoryEntry entry;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final kind = switch (entry.kind) {
      'errors' => ' · revoir mes erreurs',
      'review' => ' · révision',
      _ => '',
    };
    final state = switch (entry.status) {
      'completed' => entry.scoreOn10 == null ? '' : '${score(entry.scoreOn10!)} / 10',
      'active' => 'en cours',
      _ => 'abandonnée',
    };
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${Subjects.emoji(entry.subject)} ${entry.lessonTitle ?? 'Leçon'}',
                    style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
                  ),
                ),
                Text(state, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
              ],
            ),
            Text(
              '${when(entry.startedAt, now)} · ${entry.minutes} min$kind',
              style: const TextStyle(color: Colors.black54),
            ),
            if (entry.notions.isNotEmpty) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final (label, status) in entry.notions)
                    Text(
                      '${switch (status) {
                        'mastered' => '✓',
                        'to_review' => '⚠',
                        _ => '✗',
                      }} $label',
                      style: TextStyle(
                        color: switch (status) {
                          'mastered' => LudiColors.mastered,
                          'to_review' => const Color(0xFFB86E00),
                          _ => LudiColors.notMastered,
                        },
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

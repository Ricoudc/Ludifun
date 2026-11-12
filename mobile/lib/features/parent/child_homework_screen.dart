import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/format.dart';
import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/homework.dart';
import '../home/home_providers.dart';
import 'child_mistakes_screen.dart' show ofName;
import 'parent_providers.dart';

/// Les exercices faits avec l'aide aux devoirs : l'aide utilisée, les essais, la suite.
class ChildHomeworkScreen extends ConsumerStatefulWidget {
  const ChildHomeworkScreen({required this.childId, super.key});

  final String childId;

  @override
  ConsumerState<ChildHomeworkScreen> createState() => _ChildHomeworkScreenState();
}

class _ChildHomeworkScreenState extends ConsumerState<ChildHomeworkScreen> {
  final _items = <HomeworkSummary>[];
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
          .childHomework(widget.childId, before: _items.isEmpty ? null : _nextBefore);
      _items.addAll(page.homework);
      _nextBefore = page.nextBefore;
      _complete = page.nextBefore == null;
    } on ApiException catch (error) {
      _error = error.message;
    }
    if (mounted) setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    final name = ref.watch(childProvider(widget.childId)).value?.displayName ?? '';
    final now = ref.watch(nowProvider)();
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.childDashboard(widget.childId))),
        title: Text(name.isEmpty ? 'Devoirs' : 'Devoirs ${ofName(name)}'),
      ),
      body: CenteredBody(
        top: true,
        children: [
          const Text(
            'Avec « Aide aux devoirs », l\'enfant photographie son exercice : Ludifun le guide par '
            'étapes, sans donner la réponse ; la correction n\'arrive qu\'après plusieurs essais.',
            style: TextStyle(fontSize: 15, color: Colors.black54),
          ),
          const SizedBox(height: 12),
          if (_items.isEmpty && !_loading && _error == null)
            Text(
              name.isEmpty
                  ? 'Aucun exercice pour l\'instant.'
                  : '$name n\'a pas encore utilisé l\'aide aux devoirs.',
              style: const TextStyle(fontSize: 17),
            ),
          for (final item in _items) _HomeworkCard(item, now),
          if (_error != null) ErrorMessage(_error!),
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(12),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (!_complete || _error != null)
            TextButton(onPressed: _loadMore, child: const Text('Voir les exercices plus anciens')),
        ],
      ),
    );
  }
}

class _HomeworkCard extends StatelessWidget {
  const _HomeworkCard(this.item, this.now);

  final HomeworkSummary item;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (item.status) {
      HomeworkStatus.solved when item.solvedAlone => ('✅ Réussi seul', LudiColors.mastered),
      HomeworkStatus.solved => (
        '✅ Réussi avec ${item.stepsUsed} coup(s) de pouce',
        LudiColors.mastered,
      ),
      HomeworkStatus.guided => (
        '🧭 Correction guidée après ${item.attempts} essai(s)',
        LudiColors.toReview,
      ),
      HomeworkStatus.ready => ('⏸️ Pas terminé', Colors.black54),
      HomeworkStatus.preparing => ('⏳ En préparation', Colors.black54),
      HomeworkStatus.failed => ('⚠️ Exercice illisible ou refusé', Colors.black54),
    };
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '📝 ${whenAt(item.createdAt, now)}',
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            if (item.statement case final statement?) ...[
              const SizedBox(height: 6),
              Text(statement, style: Theme.of(context).textTheme.titleMedium),
            ],
            const SizedBox(height: 8),
            Text(
              label,
              style: TextStyle(fontWeight: FontWeight.w700, color: color),
            ),
            if (item.stepsTotal > 0)
              Text(
                'Coups de pouce : ${item.stepsUsed} sur ${item.stepsTotal} · essais : ${item.attempts}',
                style: const TextStyle(fontSize: 14, color: Colors.black54),
              ),
          ],
        ),
      ),
    );
  }
}

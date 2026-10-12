import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/format.dart';
import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/teach.dart';
import '../home/home_providers.dart';
import 'child_mistakes_screen.dart' show ofName;
import 'parent_providers.dart';

/// « Enseigne-moi » : ce que l'enfant a expliqué à Ludi, et la règle appliquée par le moteur.
class ChildTeachScreen extends ConsumerStatefulWidget {
  const ChildTeachScreen({required this.childId, super.key});

  final String childId;

  @override
  ConsumerState<ChildTeachScreen> createState() => _ChildTeachScreenState();
}

class _ChildTeachScreenState extends ConsumerState<ChildTeachScreen> {
  final _items = <TeachSummary>[];
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
          .childTeaching(widget.childId, before: _items.isEmpty ? null : _nextBefore);
      _items.addAll(page.teach);
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
        title: Text(name.isEmpty ? 'Enseigne-moi' : 'Enseigne-moi ${ofName(name)}'),
      ),
      body: CenteredBody(
        top: true,
        children: [
          const Text(
            'Avec « Enseigne-moi », l\'enfant explique une notion de sa leçon à Ludi, un élève '
            'joué par l\'IA, qui lui pose des questions. Expliquer avec ses mots montre une '
            'compréhension profonde : assez de points clés valident le niveau « Expliquer ».',
            style: TextStyle(fontSize: 15, color: Colors.black54),
          ),
          const SizedBox(height: 12),
          if (_items.isEmpty && !_loading && _error == null)
            Text(
              name.isEmpty
                  ? 'Aucune explication pour l\'instant.'
                  : '$name n\'a pas encore utilisé « Enseigne-moi ».',
              style: const TextStyle(fontSize: 17),
            ),
          for (final item in _items) _TeachCard(item, now),
          if (_error != null) ErrorMessage(_error!),
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(12),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (!_complete || _error != null)
            TextButton(
              onPressed: _loadMore,
              child: const Text('Voir les explications plus anciennes'),
            ),
        ],
      ),
    );
  }
}

class _TeachCard extends StatelessWidget {
  const _TeachCard(this.item, this.now);

  final TeachSummary item;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (item) {
      TeachSummary(finished: false) => ('⏸️ Pas terminé', Colors.black54),
      TeachSummary(validated: true) => ('⭐ Niveau « Expliquer » validé', LudiColors.mastered),
      _ => (
        '${item.covered ?? 0} point(s) clé(s) expliqué(s) sur ${item.total}',
        LudiColors.toReview,
      ),
    };
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '🧑‍🏫 ${whenAt(item.createdAt, now)}${item.lessonTitle == null ? '' : ' · ${item.lessonTitle}'}',
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 6),
            Text(item.label, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              label,
              style: TextStyle(fontWeight: FontWeight.w700, color: color),
            ),
            if (item.decision case final decision?)
              Text(decision, style: const TextStyle(fontSize: 14, color: Colors.black54)),
            for (final (question, answer) in item.turns) ...[
              const SizedBox(height: 8),
              Text('🧑‍🎓 $question', style: const TextStyle(fontSize: 14, color: Colors.black54)),
              Text('« $answer »', style: const TextStyle(fontSize: 15)),
            ],
          ],
        ),
      ),
    );
  }
}

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
import 'child_mistakes_screen.dart' show ofName;
import 'parent_providers.dart';

/// Quand l'enfant a touché « ❓ Je n'ai pas compris » : la question, l'heure, les aides vues
/// (indice, rappel de la leçon… jusqu'à la réponse) et s'il a réussi ensuite.
class ChildHelpScreen extends ConsumerStatefulWidget {
  const ChildHelpScreen({required this.childId, super.key});

  final String childId;

  @override
  ConsumerState<ChildHelpScreen> createState() => _ChildHelpScreenState();
}

class _ChildHelpScreenState extends ConsumerState<ChildHelpScreen> {
  final _requests = <HelpRequest>[];
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
          .helpRequests(widget.childId, before: _requests.isEmpty ? null : _nextBefore);
      _requests.addAll(page.requests);
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
        title: Text(name.isEmpty ? 'Aides demandées' : 'Aides demandées ${ofName(name)}'),
      ),
      body: CenteredBody(
        top: true,
        children: [
          const Text(
            'Chaque fois que l\'enfant touche « ❓ Je n\'ai pas compris » : l\'heure, les aides '
            'vues, et s\'il a réussi ensuite. Une réponse trouvée après avoir vu la solution ne '
            'compte pas pour sa progression.',
            style: TextStyle(fontSize: 15, color: Colors.black54),
          ),
          const SizedBox(height: 12),
          if (_requests.isEmpty && !_loading && _error == null)
            Text(
              name.isEmpty
                  ? 'Aucune aide demandée pour l\'instant.'
                  : '$name n\'a pas encore demandé d\'aide.',
              style: const TextStyle(fontSize: 17),
            ),
          for (final request in _requests) _HelpCard(request, now),
          if (_error != null) ErrorMessage(_error!),
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(12),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (!_complete || _error != null)
            TextButton(onPressed: _loadMore, child: const Text('Voir les aides plus anciennes')),
        ],
      ),
    );
  }
}

class _HelpCard extends StatelessWidget {
  const _HelpCard(this.request, this.now);

  final HelpRequest request;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context).textTheme;
    final (label, color) = switch (request.outcome) {
      HelpOutcome.right => ('✅ Réussi ensuite', LudiColors.mastered),
      HelpOutcome.partial => ('🟠 En partie réussi ensuite', LudiColors.toReview),
      HelpOutcome.wrong => ('❌ Raté malgré l\'aide', LudiColors.notMastered),
      HelpOutcome.unanswered => ('⏸️ Pas de réponse (séance arrêtée)', Colors.black54),
    };
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '❓ ${whenAt(request.askedAt, now)}',
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
            ),
            Text(
              '${Subjects.emoji(request.subject)} ${request.lessonTitle ?? 'Leçon'}',
              style: const TextStyle(color: Colors.black54),
            ),
            if (request.question.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(request.question, style: theme.titleMedium),
            ],
            const SizedBox(height: 8),
            for (final step in request.steps)
              Text('${step.title} · ${clockTime(step.at)}', style: const TextStyle(fontSize: 15)),
            const SizedBox(height: 8),
            Text(
              label,
              style: TextStyle(fontWeight: FontWeight.w700, color: color),
            ),
            if (request.notions.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                'Notion : ${request.notions.join(', ')}',
                style: const TextStyle(fontSize: 13, color: Colors.black54),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

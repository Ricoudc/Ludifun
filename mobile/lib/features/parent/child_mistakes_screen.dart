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
import 'parent_providers.dart';

/// « d'Emma », « de Léo » : élision devant une voyelle ou un h.
String ofName(String name) =>
    RegExp(r'^[aeiouyhàâéèêëîïôöûüAEIOUYHÀÂÉÈÊËÎÏÔÖÛÜ]').hasMatch(name) ? "d'$name" : 'de $name';

/// Questions ratées par l'enfant : la question, sa réponse, la bonne réponse.
class ChildMistakesScreen extends ConsumerStatefulWidget {
  const ChildMistakesScreen({required this.childId, super.key});

  final String childId;

  @override
  ConsumerState<ChildMistakesScreen> createState() => _ChildMistakesScreenState();
}

class _ChildMistakesScreenState extends ConsumerState<ChildMistakesScreen> {
  final _mistakes = <Mistake>[];
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
          .mistakes(widget.childId, before: _mistakes.isEmpty ? null : _nextBefore);
      _mistakes.addAll(page.mistakes);
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
        title: Text(name.isEmpty ? 'Erreurs' : 'Erreurs ${ofName(name)}'),
      ),
      body: CenteredBody(
        top: true,
        children: [
          if (_mistakes.isEmpty && !_loading && _error == null)
            Text(
              name.isEmpty
                  ? 'Aucune erreur pour l\'instant.'
                  : '$name n\'a pas encore fait d\'erreur.',
              style: const TextStyle(fontSize: 17),
            ),
          for (final mistake in _mistakes) _MistakeCard(mistake, now),
          if (_error != null) ErrorMessage(_error!),
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(12),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (!_complete || _error != null)
            TextButton(onPressed: _loadMore, child: const Text('Voir les erreurs plus anciennes')),
        ],
      ),
    );
  }
}

class _MistakeCard extends StatelessWidget {
  const _MistakeCard(this.mistake, this.now);

  final Mistake mistake;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context).textTheme;
    final lesson = [
      '${Subjects.emoji(mistake.subject)} ${mistake.lessonTitle ?? 'Leçon'}',
      when(mistake.answeredAt, now),
    ].join(' · ');
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(lesson, style: const TextStyle(color: Colors.black54)),
            if (mistake.question.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(mistake.question, style: theme.titleMedium),
            ],
            const SizedBox(height: 10),
            _Answer(
              mistake.partial ? '🟠 Sa réponse (en partie juste)' : '❌ Sa réponse',
              mistake.given,
              LudiColors.notMastered,
            ),
            const SizedBox(height: 8),
            _Answer('✅ Bonne réponse', mistake.expected, LudiColors.mastered),
            if (mistake.notions.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                'Notion : ${mistake.notions.join(', ')}',
                style: const TextStyle(fontSize: 13, color: Colors.black54),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Answer extends StatelessWidget {
  const _Answer(this.label, this.text, this.color);

  final String label;
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        label,
        style: TextStyle(fontWeight: FontWeight.w700, color: color),
      ),
      Text(text, style: const TextStyle(fontSize: 16)),
    ],
  );
}

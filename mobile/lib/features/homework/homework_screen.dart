import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/homework.dart';
import '../session/activities/common.dart' show ListenButton;

const homeworkPollInterval = Duration(seconds: 2);

/// Mode devoirs (§29, §127) : les étapes une par une, la réponse de l'enfant, puis la
/// correction guidée seulement après plusieurs essais.
class HomeworkScreen extends ConsumerStatefulWidget {
  const HomeworkScreen({required this.homeworkId, super.key});

  final String homeworkId;

  @override
  ConsumerState<HomeworkScreen> createState() => _HomeworkScreenState();
}

class _HomeworkScreenState extends ConsumerState<HomeworkScreen> {
  final _answer = TextEditingController();
  Homework? _homework;
  Timer? _poll;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _answer.addListener(() => setState(() {}));
    _fetch();
  }

  @override
  void dispose() {
    _poll?.cancel();
    _answer.dispose();
    super.dispose();
  }

  Future<void> _fetch() async {
    try {
      final homework = await ref.read(apiProvider).homework(widget.homeworkId);
      if (!mounted) return;
      setState(() => _homework = homework);
      if (homework.status == HomeworkStatus.preparing) {
        _poll ??= Timer.periodic(homeworkPollInterval, (_) => _fetch());
      } else {
        _poll?.cancel();
        _poll = null;
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  Future<void> _act(Future<Homework> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final homework = await action();
      if (!mounted) return;
      setState(() => _homework = homework);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _try() async {
    final text = _answer.text.trim();
    await _act(() => ref.read(apiProvider).homeworkAttempt(widget.homeworkId, text));
    if (_homework?.attempts.lastOrNull?.correct == false) _answer.clear();
  }

  @override
  Widget build(BuildContext context) {
    final homework = _homework;
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.childHome)),
        title: const Text('Aide aux devoirs'),
      ),
      body: CenteredBody(
        top: true,
        children: [
          if (homework == null && _error == null)
            const Center(child: CircularProgressIndicator())
          else if (homework != null)
            ..._content(context, homework),
          if (_error != null) ErrorMessage(_error!),
        ],
      ),
    );
  }

  List<Widget> _content(BuildContext context, Homework homework) {
    final theme = Theme.of(context).textTheme;
    return [
      if (homework.statement case final statement?) ...[
        Card(
          color: LudiColors.primary.withValues(alpha: 0.06),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 8, 16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      '📝 $statement',
                      style: const TextStyle(fontSize: 18, height: 1.35),
                    ),
                  ),
                ),
                ListenButton([statement]),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
      ],
      ...switch (homework.status) {
        HomeworkStatus.preparing => [
          const SizedBox(height: 24),
          const Center(child: CircularProgressIndicator()),
          const SizedBox(height: 16),
          const Text(
            'Je lis ton exercice et je prépare les étapes…',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 17),
          ),
        ],
        HomeworkStatus.failed => [
          Text(
            homework.failureMessage ?? 'Je n\'ai pas pu préparer l\'aide.',
            style: theme.titleMedium,
          ),
          const SizedBox(height: 16),
          OutlinedButton(
            onPressed: () => context.go(Routes.homeworkStart),
            child: const Text('Essayer avec un autre exercice'),
          ),
        ],
        _ => _guide(context, homework),
      },
    ];
  }

  List<Widget> _guide(BuildContext context, Homework homework) {
    final last = homework.attempts.lastOrNull;
    final ready = homework.status == HomeworkStatus.ready;
    return [
      for (final step in homework.steps) _StepCard(step),
      if (ready && homework.stepsLeft > 0)
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: _busy
                ? null
                : () => _act(() => ref.read(apiProvider).homeworkNextStep(widget.homeworkId)),
            icon: const Icon(Icons.lightbulb_outline),
            label: Text(
              homework.steps.length == 1 ? 'Je veux un indice' : 'Encore un coup de pouce',
            ),
          ),
        ),
      const SizedBox(height: 12),
      if (ready) ...[
        if (last != null && last.correct == false)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              homework.stepsLeft > 0
                  ? '🤔 Pas encore ! Relis les étapes, ou demande un coup de pouce.'
                  : '🤔 Pas encore ! Relis la méthode et refais ton calcul.',
              style: const TextStyle(fontSize: 17, color: LudiColors.toReview),
            ),
          ),
        if (last != null && last.correct == null)
          const Padding(
            padding: EdgeInsets.only(bottom: 8),
            child: Text(
              '✍️ Ta réponse est notée. Compare-la avec la correction.',
              style: TextStyle(fontSize: 17),
            ),
          ),
        TextField(
          controller: _answer,
          enabled: !_busy,
          minLines: homework.open ? 2 : 1,
          maxLines: homework.open ? 5 : 1,
          maxLength: 300,
          textInputAction: TextInputAction.done,
          onSubmitted: (_) => _answer.text.trim().isEmpty || _busy ? null : _try(),
          decoration: const InputDecoration(labelText: 'Ma réponse', border: OutlineInputBorder()),
        ),
        const SizedBox(height: 8),
        FilledButton(
          onPressed: _busy || _answer.text.trim().isEmpty ? null : _try,
          child: Text(homework.open ? 'J\'ai fini' : 'Vérifier ma réponse'),
        ),
        if (homework.solutionAvailable) ...[
          const SizedBox(height: 12),
          OutlinedButton(
            onPressed: _busy
                ? null
                : () => _act(() => ref.read(apiProvider).homeworkSolution(widget.homeworkId)),
            child: const Text('Voir la correction guidée'),
          ),
        ],
      ],
      if (homework.status == HomeworkStatus.solved) ...[
        Text(
          '🎉 Bravo, c\'est juste !',
          style: Theme.of(context).textTheme.headlineSmall
              ?.copyWith(color: LudiColors.mastered, fontWeight: FontWeight.w800),
        ),
        if (homework.check case final check?) ...[
          const SizedBox(height: 8),
          Text('✔️ Pour vérifier : $check', style: const TextStyle(fontSize: 17)),
        ],
      ],
      if (homework.status == HomeworkStatus.guided)
        Text('🧭 Correction guidée', style: Theme.of(context).textTheme.titleLarge),
      if (homework.finished && homework.solution != null) ...[
        const SizedBox(height: 8),
        for (final line in homework.solution!)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text('• $line', style: const TextStyle(fontSize: 17)),
          ),
        if (homework.status == HomeworkStatus.guided && homework.answer != null) ...[
          const SizedBox(height: 8),
          Text.rich(
            TextSpan(
              children: [
                const TextSpan(text: 'La réponse : '),
                TextSpan(
                  text: homework.answer,
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
              ],
            ),
            style: const TextStyle(fontSize: 18),
          ),
          const SizedBox(height: 8),
          const Text(
            'Recopie-la avec tes mots, et relis chaque étape pour bien comprendre.',
            style: TextStyle(fontSize: 15, color: Colors.black54),
          ),
        ],
        const SizedBox(height: 16),
        OutlinedButton(
          onPressed: () => context.go(Routes.homeworkStart),
          child: const Text('Un autre exercice'),
        ),
      ],
    ];
  }
}

class _StepCard extends StatelessWidget {
  const _StepCard(this.step);

  final HomeworkStep step;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 10),
    child: Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 8, 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 6),
                Text(step.title, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 4),
                Text(step.text, style: const TextStyle(fontSize: 17, height: 1.35)),
              ],
            ),
          ),
          ListenButton([step.title, step.text]),
        ],
      ),
    ),
  );
}

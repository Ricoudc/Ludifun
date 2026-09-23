import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/format.dart';
import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/lesson.dart';
import '../../models/subject.dart';
import '../home/home_providers.dart';

final lessonProvider = FutureProvider.autoDispose.family<Lesson, String>(
  (ref, id) => ref.watch(apiProvider).lesson(id),
);

/// La séance est créée dès l'ouverture de l'écran : la durée affichée est la vraie.
/// `null` : tout est à jour pour cette leçon.
final lessonSessionProvider = FutureProvider.autoDispose.family<RevisionSession?, String>((
  ref,
  lessonId,
) async {
  try {
    return await ref.watch(apiProvider).startSession(lessonId);
  } on ApiException catch (error) {
    if (error.code == 'nothing_to_review') return null;
    rethrow;
  }
});

/// Écran 4 : résumé de la leçon et notions à retenir.
class LessonScreen extends ConsumerWidget {
  const LessonScreen({required this.lessonId, super.key});

  final String lessonId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lesson = ref.watch(lessonProvider(lessonId));
    return Scaffold(
      appBar: AppBar(leading: BackButton(onPressed: () => context.go(Routes.childHome))),
      body: switch (lesson) {
        AsyncData(:final value) => _Summary(value),
        AsyncError(:final error) => CenteredBody(
          children: [
            ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
            TextButton(
              onPressed: () => ref.invalidate(lessonProvider(lessonId)),
              child: const Text('Réessayer'),
            ),
          ],
        ),
        _ => const Center(child: CircularProgressIndicator()),
      },
    );
  }
}

class _Summary extends ConsumerWidget {
  const _Summary(this.lesson);

  final Lesson lesson;

  Future<void> _changeGrade(BuildContext context, WidgetRef ref) async {
    final grade = await showModalBottomSheet<String>(
      context: context,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('Tu es en quelle classe ?', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 16),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                alignment: WrapAlignment.center,
                children: [
                  for (final g in grades)
                    ChoiceChip(
                      label: Text(g, style: const TextStyle(fontSize: 18)),
                      selected: g == lesson.grade,
                      onSelected: (_) => Navigator.of(context).pop(g),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
    if (grade == null || grade == lesson.grade) return;
    try {
      await ref.read(apiProvider).setGrade(lesson.id, grade);
      ref.invalidate(lessonProvider(lesson.id));
    } on ApiException catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  void _showStatement(BuildContext context, Knowledge knowledge) => showModalBottomSheet<void>(
    context: context,
    builder: (context) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(knowledge.label, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            Text(knowledge.statement, style: const TextStyle(fontSize: 18)),
          ],
        ),
      ),
    ),
  );

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(lessonSessionProvider(lesson.id));
    final theme = Theme.of(context).textTheme;
    final revision = session.value;
    return CenteredBody(
      top: true,
      children: [
        Text(
          '${Subjects.emoji(lesson.subject)} ${Subjects.label(lesson.subject).toUpperCase()}'
          '${lesson.grade == null ? '' : ' · ${lesson.grade}'}',
          style: theme.labelLarge?.copyWith(color: LudiColors.primary, letterSpacing: 1),
        ),
        const SizedBox(height: 6),
        Text(lesson.title ?? 'Ta leçon', style: theme.headlineMedium),
        const SizedBox(height: 16),
        if (revision?.objective ?? lesson.objective case final objective?)
          Text('🎯 Objectif : $objective', style: const TextStyle(fontSize: 17)),
        const SizedBox(height: 6),
        switch (session) {
          AsyncData(value: final s?) => Text(
            '⏱️ Durée estimée : ${s.estimatedMinutes} min${s.express ? ' · ⚡ révision express' : ''}',
            style: const TextStyle(fontSize: 17),
          ),
          AsyncLoading() => const Text('⏱️ …', style: TextStyle(fontSize: 17)),
          _ => const SizedBox(),
        },
        const SizedBox(height: 24),
        Text('À retenir :', style: theme.titleLarge),
        const SizedBox(height: 8),
        for (final knowledge in lesson.knowledge)
          ListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            leading: const Icon(Icons.check_circle, color: LudiColors.mastered),
            title: Text(knowledge.label, style: const TextStyle(fontSize: 18)),
            trailing: const Icon(Icons.info_outline, size: 20),
            onTap: () => _showStatement(context, knowledge),
          ),
        const SizedBox(height: 24),
        ...switch (session) {
          AsyncData(value: final s?) => [
            FilledButton(
              style: FilledButton.styleFrom(backgroundColor: LudiColors.accent),
              onPressed: () => context.go(Routes.session(s.id)),
              child: const Text('Commencer la révision'),
            ),
          ],
          AsyncData(value: null) => [
            Text(
              '🎉 Tout est à jour pour cette leçon !'
              '${lesson.nextReviewAt == null ? '' : ' Reviens ${dayLabel(lesson.nextReviewAt!, ref.watch(nowProvider)())}.'}',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 18),
            ),
          ],
          AsyncError(:final error) => [
            ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
            TextButton(
              onPressed: () => ref.invalidate(lessonSessionProvider(lesson.id)),
              child: const Text('Réessayer'),
            ),
          ],
          _ => [const Center(child: CircularProgressIndicator())],
        },
        const SizedBox(height: 8),
        TextButton(
          onPressed: () => _changeGrade(context, ref),
          child: const Text('Ce n\'est pas le bon niveau ?'),
        ),
      ],
    );
  }
}

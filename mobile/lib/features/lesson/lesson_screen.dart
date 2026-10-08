import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/api_image.dart';
import '../../app/format.dart';
import '../../app/level_stars.dart';
import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/lesson.dart';
import '../../models/session.dart';
import '../../models/subject.dart';
import '../home/home_providers.dart';
import 'resource_screen.dart';

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
    isScrollControlled: knowledge.image != null,
    builder: (context) => SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(knowledge.label, style: Theme.of(context).textTheme.titleLarge),
            if (knowledge.image case final image?) ...[
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: SizedBox(
                  height: 180,
                  width: double.infinity,
                  child: ApiImage(image, semanticLabel: knowledge.label, fit: BoxFit.contain),
                ),
              ),
            ],
            const SizedBox(height: 12),
            Text(knowledge.statement, style: const TextStyle(fontSize: 18)),
            if (knowledge.sourceExcerpt case final excerpt?) ...[
              const SizedBox(height: 20),
              Text(
                knowledge.sourcePage == null
                    ? 'Pourquoi cette notion ? C\'est écrit dans ta leçon :'
                    : 'Pourquoi cette notion ? C\'est écrit dans ta leçon, page ${knowledge.sourcePage} :',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 6),
              Text(
                '« $excerpt »',
                style: const TextStyle(
                  fontSize: 16,
                  fontStyle: FontStyle.italic,
                  color: Colors.black54,
                ),
              ),
            ],
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
        if (lesson.image case final image?) _LessonPicture(image),
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
        if (lesson.skills.isNotEmpty) ...[
          const SizedBox(height: 24),
          Text('Tu vas savoir :', style: theme.titleLarge),
          const SizedBox(height: 8),
          for (final skill in lesson.skills)
            ListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              leading: const Icon(Icons.flag_outlined, color: LudiColors.primary),
              title: Text(skill.label, style: const TextStyle(fontSize: 18)),
              trailing: LevelStars(skill.level),
            ),
        ],
        const SizedBox(height: 24),
        Text('À retenir :', style: theme.titleLarge),
        const SizedBox(height: 8),
        for (final knowledge in lesson.knowledge)
          ListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            leading: switch (knowledge.image) {
              // Image de la notion validée par le parent (étape 28) : on apprend aussi en la voyant.
              final image? => ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: SizedBox.square(dimension: 44, child: ApiImage(image)),
              ),
              null => const Icon(Icons.lightbulb_outline, color: LudiColors.accent),
            },
            title: Text(knowledge.label, style: const TextStyle(fontSize: 18)),
            trailing: LevelStars(knowledge.level),
            onTap: () => _showStatement(context, knowledge),
          ),
        if (lesson.resources.isNotEmpty) ...[
          const SizedBox(height: 24),
          Text('🌐 Pour s\'entraîner autrement :', style: theme.titleLarge),
          const SizedBox(height: 4),
          for (final resource in lesson.resources) _ResourceTile(lesson.id, resource),
        ],
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

/// Image validée par le parent ; absente ou illisible, la leçon s'affiche sans elle.
class _LessonPicture extends ConsumerWidget {
  const _LessonPicture(this.image);

  final LessonIllustration image;

  @override
  Widget build(BuildContext context, WidgetRef ref) =>
      switch (ref.watch(imageBytesProvider(image.url))) {
        AsyncData(:final value) => Padding(
          padding: const EdgeInsets.only(bottom: 16),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 280),
              child: Image.memory(
                value,
                semanticLabel: image.alt,
                fit: BoxFit.contain,
                errorBuilder: (_, _, _) => const SizedBox(),
              ),
            ),
          ),
        ),
        _ => const SizedBox(),
      };
}

/// Exercice, quiz ou vidéo d'un site de confiance (étape 30), ouvert dans l'application.
class _ResourceTile extends ConsumerWidget {
  const _ResourceTile(this.lessonId, this.resource);

  final String lessonId;
  final LessonResource resource;

  @override
  Widget build(BuildContext context, WidgetRef ref) => ListTile(
    contentPadding: EdgeInsets.zero,
    dense: true,
    leading: Text(resource.provider.emoji, style: const TextStyle(fontSize: 26)),
    title: Text(resource.title, style: const TextStyle(fontSize: 18)),
    subtitle: Text(
      '${resource.kind.label} · ${resource.provider.label}'
      '${resource.best == null ? '' : ' · meilleur score ${resource.best}'}',
    ),
    trailing: const Icon(Icons.chevron_right),
    onTap: () async {
      await Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => ResourceScreen(resource: resource, lessonId: lessonId),
        ),
      );
      ref.invalidate(lessonProvider(lessonId)); // meilleur score à jour
    },
  );
}

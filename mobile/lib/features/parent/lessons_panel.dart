import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/format.dart';
import '../../app/router.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/lesson.dart';
import '../../models/subject.dart';
import 'parent_home_screen.dart';
import 'parent_providers.dart';

/// Le parent supprime une leçon de son enfant, après confirmation (l'enfant ne le peut pas).
/// Vrai si la leçon a été supprimée ; les listes de l'espace parent sont alors rechargées.
Future<bool> deleteLessonAsParent(
  BuildContext context,
  WidgetRef ref, {
  required String childId,
  required String lessonId,
  String? title,
}) async {
  final confirmed = await confirmDanger(
    context,
    title: 'Supprimer « ${title ?? 'cette leçon'} » ?',
    message:
        'La leçon, ses jeux et les résultats obtenus dessus seront effacés. '
        'Cette action est définitive.',
    action: 'Supprimer',
  );
  if (!confirmed || !context.mounted) return false;
  try {
    await ref.read(apiProvider).deleteLesson(lessonId, childId: childId);
  } on ApiException catch (error) {
    if (context.mounted) showError(context, error);
    return false;
  }
  ref
    ..invalidate(allLessonsProvider(childId))
    ..invalidate(childLessonsProvider(childId))
    ..invalidate(childSkillsProvider(childId))
    ..invalidate(dashboardProvider(childId));
  return true;
}

/// Les leçons de l'enfant sur son tableau de bord : une leçon prête s'ouvre sur tout ce que
/// l'enfant verra (texte lu, consignes, questions et réponses) ; une leçon en préparation ou
/// en échec, sur l'avancement de l'IA.
class LessonsPanel extends ConsumerWidget {
  const LessonsPanel({required this.childId, super.key});

  final String childId;

  static String status(LessonSummary lesson) => switch (lesson.status) {
    LessonStatus.ready when lesson.awaitingParent =>
      '🔒 À relire et valider avant l\'enfant · touchez pour la relire',
    LessonStatus.ready when lesson.notionsToCheck > 0 =>
      '⚠️ ${lesson.notionsToCheck} notion(s) à vérifier · touchez pour comparer au cahier',
    LessonStatus.ready => '✅ Prête · touchez pour vérifier questions et réponses',
    LessonStatus.failed => '❌ Pas pu être préparée · touchez pour voir pourquoi',
    LessonStatus.needsReview => '✋ Quelques mots à relire · touchez pour les vérifier',
    _ => '⏳ L\'IA la prépare… · touchez pour suivre',
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lessons = ref.watch(allLessonsProvider(childId)).value;
    if (lessons == null || lessons.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Leçons', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 4),
        for (final lesson in lessons)
          Card(
            margin: const EdgeInsets.only(top: 8),
            child: ListTile(
              leading: Text(Subjects.emoji(lesson.subject), style: const TextStyle(fontSize: 26)),
              title: Text(
                lesson.title ?? 'Leçon du ${longDate(lesson.createdAt.toLocal())}',
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
              ),
              subtitle: Text(status(lesson)),
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    icon: const Icon(Icons.delete_outline),
                    tooltip: 'Supprimer la leçon',
                    onPressed: () => deleteLessonAsParent(
                      context,
                      ref,
                      childId: childId,
                      lessonId: lesson.id,
                      title: lesson.title,
                    ),
                  ),
                  const Icon(Icons.chevron_right),
                ],
              ),
              onTap: () => context.go(
                lesson.status == LessonStatus.ready
                    ? Routes.lessonContent(childId, lesson.id)
                    : Routes.analysis(lesson.id, childId: childId),
              ),
            ),
          ),
        const SizedBox(height: 24),
      ],
    );
  }
}

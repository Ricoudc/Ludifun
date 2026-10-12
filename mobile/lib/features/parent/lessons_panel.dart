import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/format.dart';
import '../../app/router.dart';
import '../../models/lesson.dart';
import '../../models/subject.dart';
import 'parent_providers.dart';

/// Les leçons de l'enfant sur son tableau de bord : une leçon prête s'ouvre sur tout ce que
/// l'enfant verra (texte lu, consignes, questions et réponses) ; une leçon en préparation ou
/// en échec, sur l'avancement de l'IA.
class LessonsPanel extends ConsumerWidget {
  const LessonsPanel({required this.childId, super.key});

  final String childId;

  static String status(LessonSummary lesson) => switch (lesson.status) {
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
              trailing: const Icon(Icons.chevron_right),
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

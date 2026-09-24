import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/session.dart';
import '../../models/account.dart';
import '../../models/lesson.dart';
import '../../models/parent.dart';
import '../../models/rewards.dart';

final childrenProvider = FutureProvider.autoDispose<List<Child>>(
  (ref) => ref.watch(apiProvider).children(),
);

/// Le compte du parent : l'adresse est-elle confirmée ? (bandeau de l'accueil parent)
final parentProfileProvider = FutureProvider.autoDispose<ParentProfile>(
  (ref) => ref.watch(apiProvider).parent(),
);

/// Un enfant de la famille (dans la liste déjà chargée).
final childProvider = FutureProvider.autoDispose.family<Child?, String>((ref, id) async {
  final children = await ref.watch(childrenProvider.future);
  return children.where((c) => c.id == id).firstOrNull;
});

final dashboardProvider = FutureProvider.autoDispose.family<Dashboard, String>(
  (ref, childId) => ref.watch(apiProvider).dashboard(childId),
);

/// XP, série et badges de l'enfant (étape 20).
final childProgressProvider = FutureProvider.autoDispose.family<Progress, String>(
  (ref, childId) => ref.watch(apiProvider).progress(childId: childId),
);

final childSkillsProvider = FutureProvider.autoDispose.family<List<LessonProgress>, String>(
  (ref, childId) => ref.watch(apiProvider).childSkills(childId),
);

final examsProvider = FutureProvider.autoDispose.family<List<Exam>, String>(
  (ref, childId) => ref.watch(apiProvider).exams(childId),
);

/// Leçons prêtes d'un enfant, vues par le parent (pour composer un contrôle).
final childLessonsProvider = FutureProvider.autoDispose.family<List<LessonSummary>, String>(
  (ref, childId) async => [
    for (final lesson in await ref.watch(apiProvider).lessons(childId: childId))
      if (lesson.status == LessonStatus.ready) lesson,
  ],
);

final devicesProvider = FutureProvider.autoDispose.family<List<Device>, String>(
  (ref, childId) => ref.watch(apiProvider).devices(childId),
);

/// Libellés des activités pour le parent.
const activityLabels = {
  'MCQ': ('🎮', 'Quiz'),
  'TRUE_FALSE': ('✅', 'Vrai ou faux'),
  'FILL_BLANK': ('✍️', 'Textes à trous'),
  'MATCH': ('🔗', 'Associations'),
  'SPEED_CHALLENGE': ('⚡', 'Défis rapides'),
  'FLASHCARD': ('🃏', 'Cartes'),
};

/// Avatars proposés à la création d'un profil.
const avatars = ['🦊', '🐼', '🦁', '🐸', '🐙', '🦄', '🐯', '🐨', '🐧', '🦉'];

String avatarOf(Child child) => child.avatar ?? child.displayName.characters.first.toUpperCase();

extension on String {
  Iterable<String> get characters => runes.map(String.fromCharCode);
}
